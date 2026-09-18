import asyncio
import contextlib
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

import httpx
import openai
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select

from app import events, limits, ratelimit
from app.auth import service as auth
from app.auth.deps import CurrentUser, Session, require_csrf
from app.config import settings
from app.db.models import Document, IngestJob, OtpCode, QueryCache, QueryLog, User
from app.db.session import tenant_session
from app.graph import store
from app.graph.pipeline import run_query
from app.ingestion import jobs
from app.ingestion.extract import check_extension
from app.retrieval.search import user_has_chunks

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_csrf)])
UPLOAD_CHUNK_BYTES = 1024 * 1024


class EmailIn(BaseModel):
    email: EmailStr
    turnstile_token: str | None = None


class VerifyIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserOut(BaseModel):
    id: UUID
    email: str
    created_at: datetime


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    chunk_count: int
    size_bytes: int
    created_at: datetime


class JobOut(BaseModel):
    id: UUID
    filename: str
    status: str
    error: str | None = None
    document_id: UUID | None = None
    created_at: datetime


class QueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    use_cache: bool = True


def _cookie_options() -> dict:
    return {"domain": settings.cookie_domain or None, "path": "/", "secure": settings.cookie_secure, "httponly": True, "samesite": "lax"}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
async def public_config() -> dict:
    return {"turnstile_site_key": settings.turnstile_site_key}


@router.post("/auth/request-otp", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(body: EmailIn, request: Request, session: Session) -> dict:
    ip = request.client.host if request.client else None
    try:
        await auth.verify_turnstile(body.turnstile_token, ip)
    except auth.CaptchaError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    try:
        await auth.request_otp(session, body.email, ip)
    except auth.OtpRateLimitError as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except (auth.EmailDeliveryError, httpx.HTTPError):
        log.exception("Failed to send OTP email")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Failed to send login code")
    return {"status": "sent"}


@router.post("/auth/verify-otp")
async def verify_otp(body: VerifyIn, session: Session, response: Response) -> UserOut:
    user = await auth.verify_otp(session, body.email, body.code)
    response.set_cookie(
        settings.cookie_name, auth.create_token(user.id), max_age=settings.jwt_ttl_minutes * 60, **_cookie_options()
    )
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(settings.cookie_name, **_cookie_options())


@router.get("/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user: CurrentUser, session: Session, response: Response) -> None:
    await session.execute(delete(OtpCode).where(OtpCode.email == user.email))
    await session.execute(delete(User).where(User.id == user.id))
    await session.commit()
    response.delete_cookie(settings.cookie_name, **_cookie_options())


@router.get("/stats")
async def stats(user: CurrentUser) -> dict:
    return {
        **await store.query_stats(user.id),
        "usage": await store.usage(user.id),
        "limits": {
            "queries_per_day": settings.queries_per_day,
            "max_documents": settings.max_documents,
            "max_storage_mb": settings.max_storage_mb,
            "max_upload_mb": settings.max_upload_mb,
        },
    }


@router.get("/limits")
async def service_limits(user: CurrentUser) -> dict:
    usage = await store.usage(user.id)
    emails = await limits.used(("resend.emails_per_day",), subject=user.email)
    personal = [
        {
            "title": "Questions today",
            "used": usage["queries_last_24h"],
            "limit": settings.queries_per_day,
            "unit": "queries",
            "period": "day",
        },
        {
            "title": "Login codes today",
            "used": emails["resend.emails_per_day"],
            "limit": settings.resend_per_user_per_day,
            "unit": "emails",
            "period": "day",
        },
        {
            "title": "Documents",
            "used": usage["documents"],
            "limit": settings.max_documents,
            "unit": "documents",
            "period": "total",
        },
        {
            "title": "Storage",
            "used": round(usage["storage_bytes"] / 1024 / 1024, 2),
            "limit": settings.max_storage_mb,
            "unit": "MB",
            "period": "total",
        },
    ]
    return await limits.snapshot(personal)


async def _spool_upload(file: UploadFile, extension: str) -> tuple[str, int]:
    limit = settings.max_upload_mb * 1024 * 1024
    descriptor, path = tempfile.mkstemp(suffix=extension)
    size = 0
    try:
        with os.fdopen(descriptor, "wb") as target:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File exceeds the {settings.max_upload_mb:g} MB limit for a single file",
                    )
                target.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File is empty")
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
    return path, size


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    user: CurrentUser,
    file: Annotated[UploadFile, File()],
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> JobOut:
    extension = check_extension(file.filename or "upload")
    if idempotency_key:
        existing = await jobs.find_by_key(user.id, idempotency_key)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return JobOut.model_validate(existing, from_attributes=True)

    await limits.ensure(*limits.INGEST_KEYS)
    usage = await store.usage(user.id)
    if usage["documents"] >= settings.max_documents:
        kept = settings.max_documents
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Document limit of {kept} reached. "
            f"Delete {'the current document' if kept == 1 else 'one'} to upload another.",
        )

    path, size = await _spool_upload(file, extension)
    if usage["storage_bytes"] + size > settings.max_storage_mb * 1024 * 1024:
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Storage limit of {settings.max_storage_mb} MB reached")

    job, created = await jobs.enqueue(user.id, file.filename or "upload", path, idempotency_key)
    if not created:
        with contextlib.suppress(OSError):
            os.unlink(path)
        response.status_code = status.HTTP_200_OK
    return JobOut.model_validate(job, from_attributes=True)


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, user: CurrentUser) -> JobOut:
    async with tenant_session(user.id) as session:
        job = await session.get(IngestJob, job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        return JobOut.model_validate(job, from_attributes=True)


@router.get("/documents")
async def list_documents(user: CurrentUser) -> list[DocumentOut]:
    async with tenant_session(user.id) as session:
        documents = await session.scalars(
            select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
        )
        return [DocumentOut.model_validate(document, from_attributes=True) for document in documents]


@router.delete("/documents", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_documents(user: CurrentUser) -> None:
    async with tenant_session(user.id) as session:
        await session.execute(delete(Document).where(Document.user_id == user.id))
        await session.execute(delete(QueryCache).where(QueryCache.user_id == user.id))
        await session.commit()


@router.delete("/cache", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cache(user: CurrentUser) -> None:
    async with tenant_session(user.id) as session:
        await session.execute(delete(QueryCache).where(QueryCache.user_id == user.id))
        await session.commit()


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(user: CurrentUser) -> None:
    async with tenant_session(user.id) as session:
        await session.execute(delete(QueryLog).where(QueryLog.user_id == user.id))
        await session.commit()


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, user: CurrentUser) -> None:
    async with tenant_session(user.id) as session:
        result = await session.execute(
            delete(Document).where(Document.id == document_id, Document.user_id == user.id)
        )
        if result.rowcount == 0:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
        await session.execute(delete(QueryCache).where(QueryCache.user_id == user.id))
        await session.commit()


@router.get("/history")
async def history(user: CurrentUser, limit: int = 50) -> list[dict]:
    async with tenant_session(user.id) as session:
        rows = await session.scalars(
            select(QueryLog)
            .where(QueryLog.user_id == user.id)
            .order_by(QueryLog.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        return [
            {
                "id": str(row.id),
                "question": row.question,
                "answer": row.answer,
                "sources": row.sources,
                "cache_hit": row.cache_hit,
                "tokens_used": row.tokens_used,
                "tokens_saved": row.tokens_saved,
                "node_metrics": row.node_metrics,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_error(exc: Exception) -> dict:
    if isinstance(exc, limits.LimitExceeded):
        return {"type": "error", "status": 429, "detail": str(exc)}
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
        return {"type": "error", "status": 504, "detail": "Model provider timed out"}
    if isinstance(exc, (openai.OpenAIError, httpx.HTTPError)):
        return {"type": "error", "status": 502, "detail": "Model provider unavailable"}
    log.exception("Query stream failed", exc_info=exc)
    return {"type": "error", "status": 500, "detail": "Internal error"}


@router.get("/events")
async def events_stream(user: CurrentUser) -> StreamingResponse:
    try:
        queue = events.subscribe(user.id)
    except events.TooManySubscribers as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc

    async def body_stream():
        try:
            yield _sse({"type": "connected"})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=settings.events_heartbeat_seconds)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event)
        finally:
            events.unsubscribe(user.id, queue)

    return StreamingResponse(
        body_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _ensure_question_spacing(user_id: UUID) -> None:
    interval = settings.query_min_interval_seconds
    if interval <= 0:
        return
    allowed = await ratelimit.allow(f"query:user:{user_id}", 1, interval)
    if allowed is None:
        async with tenant_session(user_id) as session:
            recent = await session.scalar(
                select(func.count()).where(
                    QueryLog.user_id == user_id,
                    QueryLog.created_at > func.now() - timedelta(seconds=interval),
                )
            )
        allowed = not recent
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Please wait {interval} seconds between questions.",
        )


@router.post("/query")
async def query(body: QueryIn, user: CurrentUser) -> StreamingResponse:
    async with tenant_session(user.id) as session:
        if not await user_has_chunks(session, user.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "No documents uploaded yet")
    await _ensure_question_spacing(user.id)
    if (await store.usage(user.id))["queries_last_24h"] >= settings.queries_per_day:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Daily limit of {settings.queries_per_day} queries reached")
    stream = run_query(user.id, body.question, use_cache=body.use_cache)
    try:
        first = await anext(stream)
    except BaseException:
        await stream.aclose()
        raise

    async def body_stream():
        try:
            yield _sse(first)
            async for event in stream:
                yield _sse(event)
        except Exception as exc:
            yield _sse(_stream_error(exc))
        finally:
            await stream.aclose()
            await limits.publish_snapshot()

    return StreamingResponse(
        body_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
