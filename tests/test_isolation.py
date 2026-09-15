import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.db.models import Chunk, Document
from app.db.session import tenant_session
from app.graph import store
from app.retrieval.search import fulltext_search, hybrid_search, vector_search
from tests.conftest import auth_headers, fake_embedding, seed_document


async def test_search_never_returns_other_users_documents(make_user):
    owner, stranger = await make_user(), await make_user()
    await seed_document(owner.id, "confidential merger plan codename falcon", seed=7)

    assert [c.content for c in await vector_search(owner.id, fake_embedding(7), 10)]
    assert [c.content for c in await fulltext_search(owner.id, "falcon merger", 10)]
    assert await vector_search(stranger.id, fake_embedding(7), 10) == []
    assert await fulltext_search(stranger.id, "falcon merger", 10) == []
    assert await hybrid_search(stranger.id, "falcon merger", fake_embedding(7)) == []


async def test_row_level_security_blocks_unfiltered_access(make_user):
    owner, stranger = await make_user(), await make_user()
    await seed_document(owner.id, "owner only text", seed=11)

    async with tenant_session(stranger.id) as session:
        assert await session.scalar(select(func.count()).select_from(Chunk)) == 0
        assert await session.scalar(select(func.count()).select_from(Document)) == 0

    with pytest.raises(DBAPIError):
        async with tenant_session(stranger.id) as session:
            session.add(Document(user_id=owner.id, filename="injected.md", chunk_count=0, size_bytes=0))
            await session.commit()


async def test_query_cache_is_per_user(make_user):
    owner, stranger = await make_user(), await make_user()
    await store.record_query(
        user_id=owner.id,
        question="q",
        answer="owner answer",
        sources=[],
        cache_hit=False,
        tokens_used=100,
        tokens_saved=0,
        cache_embedding=fake_embedding(3),
    )
    assert (await store.find_cached(owner.id, fake_embedding(3))).answer == "owner answer"
    assert await store.find_cached(stranger.id, fake_embedding(3)) is None
    assert (await store.query_stats(stranger.id))["total_queries"] == 0


async def test_api_does_not_expose_other_users_data(client, make_user):
    owner, stranger = await make_user(), await make_user()
    document = await seed_document(owner.id, "private", seed=5)

    assert len((await client.get("/documents", headers=auth_headers(owner.id))).json()) == 1
    assert (await client.get("/documents", headers=auth_headers(stranger.id))).json() == []
    response = await client.post("/query", json={"question": "private?"}, headers=auth_headers(stranger.id))
    assert response.status_code == 409
    deleted = await client.delete(f"/documents/{document.id}", headers=auth_headers(stranger.id))
    assert deleted.status_code == 404
