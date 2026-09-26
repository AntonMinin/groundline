from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert

from app.config import settings
from app.db.models import Document, DocumentVersion, QueryCache, QueryLog
from app.db.session import tenant_session


@dataclass
class CachedAnswer:
    question: str
    answer: str
    sources: list[dict]
    tokens_used: int
    similarity: float


async def find_nearest(user_id: UUID, embedding: list[float]) -> CachedAnswer | None:
    distance = QueryCache.question_embedding.cosine_distance(embedding).label("distance")
    async with tenant_session(user_id) as session:
        row = (
            await session.execute(
                select(QueryCache, distance).where(QueryCache.user_id == user_id).order_by(distance).limit(1)
            )
        ).first()
    if row is None:
        return None
    cached = row.QueryCache
    return CachedAnswer(cached.question_text, cached.answer_text, cached.sources, cached.tokens_used, 1 - row.distance)


async def record_query(
    user_id: UUID,
    question: str,
    answer: str,
    sources: list[dict],
    cache_hit: bool,
    tokens_used: int,
    tokens_saved: int,
    cache_embedding: list[float] | None,
    node_metrics: list[dict] | None = None,
    documents_version: int = 0,
) -> tuple[UUID, bool]:
    log = QueryLog(
        id=uuid4(),
        user_id=user_id,
        question=question,
        answer=answer,
        sources=sources,
        cache_hit=cache_hit,
        tokens_used=tokens_used,
        tokens_saved=tokens_saved,
        node_metrics=node_metrics or [],
    )
    async with tenant_session(user_id) as session:
        session.add(log)
        cached = cache_embedding is not None and await _documents_unchanged(session, user_id, documents_version)
        if cached:
            session.add(_cache_row(user_id, question, cache_embedding, answer, sources, tokens_used))
        await session.commit()
    return log.id, cached


async def documents_version(user_id: UUID) -> int:
    async with tenant_session(user_id) as session:
        version = await session.scalar(select(DocumentVersion.version).where(DocumentVersion.user_id == user_id))
    return version or 0


async def bump_documents_version(session, user_id: UUID) -> None:
    await session.execute(
        insert(DocumentVersion)
        .values(user_id=user_id, version=1)
        .on_conflict_do_update(
            index_elements=[DocumentVersion.user_id], set_={"version": DocumentVersion.version + 1}
        )
    )


async def _documents_unchanged(session, user_id: UUID, expected: int) -> bool:
    await session.execute(
        insert(DocumentVersion).values(user_id=user_id, version=0).on_conflict_do_nothing(
            index_elements=[DocumentVersion.user_id]
        )
    )
    current = await session.scalar(
        select(DocumentVersion.version).where(DocumentVersion.user_id == user_id).with_for_update(read=True)
    )
    return (current or 0) == expected


async def append_node_metric(user_id: UUID, log_id: UUID, metric: dict) -> None:
    async with tenant_session(user_id) as session:
        await session.execute(
            update(QueryLog)
            .where(QueryLog.id == log_id, QueryLog.user_id == user_id)
            .values(node_metrics=QueryLog.node_metrics.op("||")(cast([metric], JSONB)))
        )
        await session.commit()


def _cache_row(
    user_id: UUID, question: str, embedding: list[float], answer: str, sources: list[dict], tokens_used: int
) -> QueryCache:
    return QueryCache(
        user_id=user_id,
        question_text=question,
        question_embedding=embedding,
        answer_text=answer,
        sources=sources,
        tokens_used=tokens_used,
    )


async def cache_answer(
    user_id: UUID,
    question: str,
    embedding: list[float],
    answer: str,
    sources: list[dict],
    tokens_used: int,
    documents_version: int,
) -> bool:
    async with tenant_session(user_id) as session:
        if not await _documents_unchanged(session, user_id, documents_version):
            return False
        session.add(_cache_row(user_id, question, embedding, answer, sources, tokens_used))
        await session.commit()
    return True


async def usage(user_id: UUID) -> dict:
    async with tenant_session(user_id) as session:
        documents, storage = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.user_id == user_id)
            )
        ).one()
        queries = await session.scalar(
            select(func.count()).where(
                QueryLog.user_id == user_id,
                QueryLog.cache_hit.is_(False),
                QueryLog.created_at > func.now() - timedelta(days=1),
            )
        )
    return {"documents": documents, "storage_bytes": storage, "queries_last_24h": queries}


async def query_stats(user_id: UUID) -> dict:
    async with tenant_session(user_id) as session:
        total, hits, saved, used = (
            await session.execute(
                select(
                    func.count(),
                    func.count().filter(QueryLog.cache_hit),
                    func.coalesce(func.sum(QueryLog.tokens_saved), 0),
                    func.coalesce(func.sum(QueryLog.tokens_used), 0),
                ).where(QueryLog.user_id == user_id)
            )
        ).one()
    return {
        "total_queries": total,
        "cache_hits": hits,
        "cache_hit_rate": round(hits / total, 4) if total else 0.0,
        "tokens_saved": saved,
        "tokens_used": used,
    }
