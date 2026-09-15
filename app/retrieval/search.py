import asyncio
from uuid import UUID

from sqlalchemy import Select, Text, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Chunk, Document
from app.db.session import tenant_session
from app.retrieval.fusion import RetrievedChunk, reciprocal_rank_fusion


def _base_query(user_id: UUID) -> Select:
    return (
        select(Chunk.id, Chunk.document_id, Document.filename, Chunk.chunk_index, Chunk.page, Chunk.content)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.user_id == user_id, Document.user_id == user_id)
    )


def _to_chunks(rows) -> list[RetrievedChunk]:
    return [RetrievedChunk(*row) for row in rows]


async def vector_search(user_id: UUID, embedding: list[float], limit: int) -> list[RetrievedChunk]:
    async with tenant_session(user_id) as session:
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        query = _base_query(user_id).order_by(Chunk.embedding.cosine_distance(embedding)).limit(limit)
        return _to_chunks((await session.execute(query)).all())


async def fulltext_search(user_id: UUID, query_text: str, limit: int) -> list[RetrievedChunk]:
    tsquery = func.to_tsquery(
        "simple", func.replace(func.cast(func.plainto_tsquery("simple", query_text), Text), "&", "|")
    )
    query = (
        _base_query(user_id)
        .where(Chunk.tsv.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(Chunk.tsv, tsquery).desc())
        .limit(limit)
    )
    async with tenant_session(user_id) as session:
        return _to_chunks((await session.execute(query)).all())


async def hybrid_search(
    user_id: UUID, query_text: str, embedding: list[float], limit: int = settings.retrieval_candidates
) -> list[RetrievedChunk]:
    vector_results, fulltext_results = await asyncio.gather(
        vector_search(user_id, embedding, limit), fulltext_search(user_id, query_text, limit)
    )
    return reciprocal_rank_fusion([vector_results, fulltext_results])[:limit]


async def user_has_chunks(session: AsyncSession, user_id: UUID) -> bool:
    return bool(await session.scalar(select(exists().where(Chunk.user_id == user_id))))
