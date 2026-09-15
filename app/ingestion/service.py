from uuid import UUID

from fastapi.concurrency import run_in_threadpool
from langfuse import get_client, propagate_attributes
from sqlalchemy import delete

from app.db.models import Chunk, Document, QueryCache
from app.db.session import tenant_session
from app.embeddings import embed
from app.ingestion.chunking import chunk_pages
from app.ingestion.extract import InvalidFileError, extract_pages


async def ingest_file(user_id: UUID, filename: str, data: bytes) -> Document:
    with (
        propagate_attributes(user_id=str(user_id), trace_name="ingest"),
        get_client().start_as_current_observation(name="ingest", input={"filename": filename, "bytes": len(data)}),
    ):
        pages = await run_in_threadpool(extract_pages, filename, data)
        chunks = await run_in_threadpool(chunk_pages, pages)
        if not chunks:
            raise InvalidFileError("No extractable text found in file")
        vectors = await embed([chunk.content for chunk in chunks], name="embed_chunks")

        async with tenant_session(user_id) as session:
            document = Document(user_id=user_id, filename=filename, chunk_count=len(chunks), size_bytes=len(data))
            session.add(document)
            await session.flush()
            session.add_all(
                Chunk(
                    user_id=user_id,
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page=chunk.page,
                    content=chunk.content,
                    embedding=vector,
                )
                for chunk, vector in zip(chunks, vectors)
            )
            await session.execute(delete(QueryCache).where(QueryCache.user_id == user_id))
            await session.commit()
            return document
