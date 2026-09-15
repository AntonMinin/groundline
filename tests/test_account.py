from sqlalchemy import func, select

from app.config import settings
from app.db.models import Chunk, Document
from app.db.session import tenant_session
from app.graph import store
from app.retrieval.rerank import parse_rerank_response
from tests.conftest import auth_headers, fake_embedding, seed_document


async def test_unsafe_requests_require_csrf_header(client, make_user):
    user = await make_user()
    response = await client.delete("/me", headers={**auth_headers(user.id), "X-Requested-With": ""})
    assert response.status_code == 403
    assert (await client.get("/me", headers={**auth_headers(user.id), "X-Requested-With": ""})).status_code == 200


async def test_delete_account_removes_all_user_data(client, make_user):
    user = await make_user()
    await seed_document(user.id, "to be erased", seed=21)
    await store.record_query(
        user_id=user.id,
        question="q",
        answer="a",
        sources=[],
        cache_hit=False,
        tokens_used=1,
        tokens_saved=0,
        cache_embedding=fake_embedding(21),
    )

    assert (await client.delete("/me", headers=auth_headers(user.id))).status_code == 204
    assert (await client.get("/me", headers=auth_headers(user.id))).status_code == 401
    async with tenant_session(user.id) as session:
        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert await session.scalar(select(func.count()).select_from(Chunk)) == 0
    assert (await store.query_stats(user.id))["total_queries"] == 0


async def test_daily_query_limit(client, make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "content", seed=31)
    await store.record_query(
        user_id=user.id, question="q", answer="a", sources=[], cache_hit=False, tokens_used=1, tokens_saved=0, cache_embedding=None
    )
    monkeypatch.setattr(settings, "queries_per_day", 1)
    response = await client.post("/query", json={"question": "again"}, headers=auth_headers(user.id))
    assert response.status_code == 429


async def test_document_and_storage_limits(client, make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "content", seed=41, size_bytes=900_000)
    upload = {"file": ("notes.txt", b"hello world")}

    monkeypatch.setattr(settings, "max_documents", 1)
    assert (await client.post("/ingest", files=upload, headers=auth_headers(user.id))).status_code == 429

    monkeypatch.setattr(settings, "max_documents", 10)
    monkeypatch.setattr(settings, "max_storage_mb", 0)
    assert (await client.post("/ingest", files=upload, headers=auth_headers(user.id))).status_code == 429


async def test_unsupported_upload_is_415(client, make_user):
    user = await make_user()
    response = await client.post("/ingest", files={"file": ("photo.png", b"\x89PNG")}, headers=auth_headers(user.id))
    assert response.status_code == 415


def test_parse_pinecone_rerank_response():
    payload = {"data": [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.1}]}
    assert parse_rerank_response(payload, 3) == [0.1, 0.0, 0.9]
