from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from app.config import settings
from app.db.models import Document, QueryCache, QueryLog
from app.db.session import tenant_session


@dataclass
class CachedAnswer:
    question: str
    answer: str
    sources: list[dict]
    tokens_used: int
    similarity: float


async def find_cached(user_id: UUID, embedding: list[float]) -> CachedAnswer | None:
    distance = QueryCache.question_embedding.cosine_distance(embedding).label("distance")
    async with tenant_session(user_id) as session:
        row = (
            await session.execute(
                select(QueryCache, distance).where(QueryCache.user_id == user_id).order_by(distance).limit(1)
            )
        ).first()
    if row is None:
        return None
    similarity = 1 - row.distance
    if similarity < settings.cache_similarity_threshold:
        return None
    cached = row.QueryCache
    return CachedAnswer(cached.question_text, cached.answer_text, cached.sources, cached.tokens_used, similarity)


async def record_query(
    user_id: UUID,
    question: str,
    answer: str,
    sources: list[dict],
    cache_hit: bool,
    tokens_used: int,
    tokens_saved: int,
    cache_embedding: list[float] | None,
) -> None:
    async with tenant_session(user_id) as session:
        session.add(
            QueryLog(
                user_id=user_id,
                question=question,
                answer=answer,
                sources=sources,
                cache_hit=cache_hit,
                tokens_used=tokens_used,
                tokens_saved=tokens_saved,
            )
        )
        if cache_embedding is not None:
            session.add(
                QueryCache(
                    user_id=user_id,
                    question_text=question,
                    question_embedding=cache_embedding,
                    answer_text=answer,
                    sources=sources,
                    tokens_used=tokens_used,
                )
            )
        await session.commit()


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
