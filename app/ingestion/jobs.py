import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import events
from app.config import settings
from app.db.models import IngestJob
from app.db.session import tenant_session
from app.ingestion.extract import InvalidFileError, UnsupportedFileError
from app.ingestion.service import ingest_from_path

log = logging.getLogger(__name__)


@dataclass
class IngestTask:
    job_id: UUID
    user_id: UUID
    filename: str
    path: str


_queue: asyncio.Queue[IngestTask] = asyncio.Queue(maxsize=settings.ingest_queue_size)
_workers: list[asyncio.Task] = []
_running = 0


def pending() -> int:
    return _queue.qsize() + _running


async def _update(job_id: UUID, user_id: UUID, **values) -> None:
    async with tenant_session(user_id) as session:
        job = await session.get(IngestJob, job_id)
        if job is None:
            return
        for field, value in values.items():
            setattr(job, field, value)
        await session.commit()
        events.publish(
            user_id,
            {
                "type": "ingest",
                "job_id": str(job_id),
                "filename": job.filename,
                "status": job.status,
                "error": job.error,
                "document_id": str(job.document_id) if job.document_id else None,
            },
        )


async def _process(task: IngestTask) -> None:
    global _running
    _running += 1
    await _update(task.job_id, task.user_id, status="processing")
    try:
        document = await ingest_from_path(task.user_id, task.filename, task.path)
        await _update(
            task.job_id,
            task.user_id,
            status="done",
            document_id=document.id,
            finished_at=datetime.now(UTC),
        )
    except (UnsupportedFileError, InvalidFileError) as exc:
        await _update(task.job_id, task.user_id, status="error", error=str(exc), finished_at=datetime.now(UTC))
    except Exception:
        log.exception("Ingest job %s failed", task.job_id)
        await _update(
            task.job_id, task.user_id, status="error", error="Internal error", finished_at=datetime.now(UTC)
        )
    finally:
        _running -= 1
        with contextlib.suppress(OSError):
            os.unlink(task.path)


async def _worker() -> None:
    while True:
        task = await _queue.get()
        try:
            await _process(task)
        finally:
            _queue.task_done()


async def start_workers() -> None:
    if _workers:
        return
    _workers.extend(asyncio.create_task(_worker()) for _ in range(settings.ingest_workers))
    log.info("Started %d ingest workers", len(_workers))


async def stop_workers() -> None:
    for worker in _workers:
        worker.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()


async def find_by_key(user_id: UUID, idempotency_key: str) -> IngestJob | None:
    async with tenant_session(user_id) as session:
        return await session.scalar(
            select(IngestJob).where(IngestJob.user_id == user_id, IngestJob.idempotency_key == idempotency_key)
        )


async def enqueue(user_id: UUID, filename: str, path: str, idempotency_key: str | None) -> tuple[IngestJob, bool]:
    job = IngestJob(id=uuid4(), user_id=user_id, filename=filename, status="queued", idempotency_key=idempotency_key)
    async with tenant_session(user_id) as session:
        session.add(job)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await find_by_key(user_id, idempotency_key)
            if existing is None:
                raise
            return existing, False
    events.publish(
        user_id,
        {
            "type": "ingest",
            "job_id": str(job.id),
            "filename": filename,
            "status": "queued",
            "error": None,
            "document_id": None,
        },
    )
    await _queue.put(IngestTask(job_id=job.id, user_id=user_id, filename=filename, path=path))
    return job, True
