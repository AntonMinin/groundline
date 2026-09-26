import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.db.models import Chunk, Document, User
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
    assert (await store.find_nearest(owner.id, fake_embedding(3))).answer == "owner answer"
    assert await store.find_nearest(stranger.id, fake_embedding(3)) is None
    assert (await store.query_stats(stranger.id))["total_queries"] == 0


TENANT_TABLES = {"documents", "chunks", "query_cache", "query_log", "ingest_jobs", "document_versions"}
NON_TENANT_TABLES = {"users", "otp_codes", "service_usage", "alembic_version"}


async def test_every_table_is_either_tenant_isolated_or_rls_free(migrated_db):
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, count(p.polname) AS policies
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_policy p ON p.polrelid = c.oid
                    WHERE n.nspname = 'public' AND c.relkind = 'r'
                    GROUP BY c.relname, c.relrowsecurity
                    """
                )
            )
        ).all()

    state = {name: (rls, policies) for name, rls, policies in rows}
    assert TENANT_TABLES <= set(state), f"missing tenant tables: {TENANT_TABLES - set(state)}"

    for name, (rls, policies) in state.items():
        if name in TENANT_TABLES:
            assert rls and policies, f"{name} must keep row-level security with a policy"
        else:
            assert not rls or policies, (
                f"{name} has row-level security enabled with no policy: the application role would see "
                "no rows at all. Tenant tables need a policy, other tables need RLS disabled."
            )


async def test_the_application_role_can_read_non_tenant_tables(make_user):
    from app.db.session import SessionLocal

    user = await make_user()
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(User).where(User.id == user.id)) == 1
        assert await session.scalar(text("SELECT count(*) FROM otp_codes")) is not None
        assert await session.scalar(text("SELECT count(*) FROM service_usage")) is not None


async def test_api_does_not_expose_other_users_data(client, make_user):
    owner, stranger = await make_user(), await make_user()
    document = await seed_document(owner.id, "private", seed=5)

    assert len((await client.get("/documents", headers=auth_headers(owner.id))).json()) == 1
    assert (await client.get("/documents", headers=auth_headers(stranger.id))).json() == []
    response = await client.post("/query", json={"question": "private?"}, headers=auth_headers(stranger.id))
    assert response.status_code == 409
    deleted = await client.delete(f"/documents/{document.id}", headers=auth_headers(stranger.id))
    assert deleted.status_code == 404
