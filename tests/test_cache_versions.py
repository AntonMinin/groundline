from sqlalchemy import func, select

from app.db.models import QueryCache
from app.db.session import tenant_session
from app.graph import store
from tests.conftest import fake_embedding, seed_document


async def cached_count(user_id) -> int:
    async with tenant_session(user_id) as session:
        return await session.scalar(select(func.count()).select_from(QueryCache).where(QueryCache.user_id == user_id))


async def upload(user_id, monkeypatch) -> None:
    from app.ingestion import service

    async def fake_embed(texts, name="embed"):
        return [fake_embedding(index + 1) for index, _ in enumerate(texts)]

    monkeypatch.setattr(service, "embed", fake_embed)
    await service.ingest_file(user_id, "new.md", b"# New policy\n\nRemote work is allowed five days a week.")


def answer(version: int) -> dict:
    return {
        "question": "How many remote days?",
        "embedding": fake_embedding(9),
        "answer": "Three [1]",
        "sources": [],
        "tokens_used": 10,
        "documents_version": version,
    }


async def test_an_upload_between_done_and_the_cache_write_keeps_the_answer_out(make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "Remote work is allowed three days a week.", seed=1)
    seen_by_retrieval = await store.documents_version(user.id)

    await upload(user.id, monkeypatch)

    assert await store.cache_answer(user.id, **answer(seen_by_retrieval)) is False
    assert await cached_count(user.id) == 0
    assert await store.cache_answer(user.id, **answer(await store.documents_version(user.id))) is True
    assert await cached_count(user.id) == 1


async def test_the_record_step_also_skips_a_stale_cache_write_but_keeps_the_log(make_user, monkeypatch):
    user = await make_user()
    seen_by_retrieval = await store.documents_version(user.id)
    await upload(user.id, monkeypatch)

    log_id, cached = await store.record_query(
        user_id=user.id,
        question="q",
        answer="a",
        sources=[],
        cache_hit=False,
        tokens_used=1,
        tokens_saved=0,
        cache_embedding=fake_embedding(4),
        documents_version=seen_by_retrieval,
    )
    assert log_id is not None and cached is False
    assert await cached_count(user.id) == 0


async def test_deleting_documents_moves_the_version(client, make_user):
    from tests.conftest import auth_headers

    user = await make_user()
    document = await seed_document(user.id, "text", seed=2)
    before = await store.documents_version(user.id)
    response = await client.delete(f"/documents/{document.id}", headers=auth_headers(user.id))
    assert response.status_code == 204
    after_one = await store.documents_version(user.id)
    assert (await client.delete("/documents", headers=auth_headers(user.id))).status_code == 204
    assert before < after_one < await store.documents_version(user.id)


async def test_a_version_is_invisible_to_other_users(make_user, monkeypatch):
    owner, stranger = await make_user(), await make_user()
    await upload(owner.id, monkeypatch)
    assert await store.documents_version(owner.id) >= 1
    async with tenant_session(stranger.id) as session:
        from app.db.models import DocumentVersion

        rows = await session.scalar(select(func.count()).select_from(DocumentVersion))
    assert rows == 0


async def version_rows(user_id) -> int:
    from app.db.models import DocumentVersion

    async with tenant_session(user_id) as session:
        return await session.scalar(
            select(func.count()).select_from(DocumentVersion).where(DocumentVersion.user_id == user_id)
        )


async def test_a_user_without_a_version_row_still_gets_a_guarded_cache(make_user, monkeypatch):
    user = await make_user()
    assert await version_rows(user.id) == 0
    assert await store.documents_version(user.id) == 0

    await upload(user.id, monkeypatch)
    assert await version_rows(user.id) == 1
    assert await store.cache_answer(user.id, **answer(0)) is False
    assert await store.cache_answer(user.id, **answer(await store.documents_version(user.id))) is True
    assert await cached_count(user.id) == 1


async def test_the_cache_write_creates_the_missing_row_it_locks(make_user):
    user = await make_user()
    assert await store.cache_answer(user.id, **answer(0)) is True
    assert await version_rows(user.id) == 1
    assert await store.documents_version(user.id) == 0
