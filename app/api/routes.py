import json
import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

import httpx
import openai
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select

from app.auth import service as auth
from app.auth.deps import CurrentUser, Session
from app.config import settings
from app.db.models import Document, OtpCode, QueryCache, QueryLog, User
from app.db.session import tenant_session
from app.graph import store
from app.graph.pipeline import run_query
from app.ingestion.service import ingest_file
from app.retrieval.search import user_has_chunks

log = logging.getLogger(__name__)
router = APIRouter()


class EmailIn(BaseModel):
    email: EmailStr


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


class QueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    use_cache: bool = True


def _cookie_options() -> dict:
    return {"domain": settings.cookie_domain or None, "path": "/", "secure": settings.cookie_secure, "httponly": True, "samesite": "lax"}


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/auth/request-otp", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(body: EmailIn, request: Request, session: Session) -> dict:
    try:
        await auth.request_otp(session, body.email, request.client.host if request.client else None)
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
        },
    }


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest(user: CurrentUser, file: Annotated[UploadFile, File()]) -> DocumentOut:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_mb} MB")
    usage = await store.usage(user.id)
    if usage["documents"] >= settings.max_documents:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Document limit of {settings.max_documents} reached")
    if usage["storage_bytes"] + len(data) > settings.max_storage_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Storage limit of {settings.max_storage_mb} MB reached")
    document = await ingest_file(user.id, file.filename or "upload", data)
    return DocumentOut.model_validate(document, from_attributes=True)


@router.get("/documents")
async def list_documents(user: CurrentUser) -> list[DocumentOut]:
    async with tenant_session(user.id) as session:
        documents = await session.scalars(
            select(Document).where(Document.user_id == user.id).order_by(Document.created_at.desc())
        )
        return [DocumentOut.model_validate(document, from_attributes=True) for document in documents]


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
                "tokens_saved": row.tokens_saved,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream_error(exc: Exception) -> dict:
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
        return {"type": "error", "status": 504, "detail": "Model provider timed out"}
    if isinstance(exc, (openai.OpenAIError, httpx.HTTPError)):
        return {"type": "error", "status": 502, "detail": "Model provider unavailable"}
    log.exception("Query stream failed", exc_info=exc)
    return {"type": "error", "status": 500, "detail": "Internal error"}


@router.post("/query")
async def query(body: QueryIn, user: CurrentUser) -> StreamingResponse:
    async with tenant_session(user.id) as session:
        if not await user_has_chunks(session, user.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "No documents uploaded yet")
    if (await store.usage(user.id))["queries_last_24h"] >= settings.queries_per_day:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Daily limit of {settings.queries_per_day} queries reached")
    events = run_query(user.id, body.question, use_cache=body.use_cache)
    try:
        first = await anext(events)
    except BaseException:
        await events.aclose()
        raise

    async def body_stream():
        try:
            yield _sse(first)
            async for event in events:
                yield _sse(event)
        except Exception as exc:
            yield _sse(_stream_error(exc))
        finally:
            await events.aclose()

    return StreamingResponse(
        body_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
