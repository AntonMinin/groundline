from sqlalchemy import func, select

from app.config import settings
from app import limits
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


async def test_unauthenticated_unsafe_requests_require_csrf_header(client):
    assert (await client.post("/auth/logout", headers={"X-Requested-With": ""})).status_code == 403
    response = await client.post(
        "/auth/request-otp", json={"email": "csrf@example.com", "accepted_terms": True}, headers={"X-Requested-With": ""}
    )
    assert response.status_code == 403


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


async def test_delete_account_removes_the_personal_counters_keyed_by_email(client, make_user):
    user = await make_user()
    await limits.add("resend.emails_per_day", subject=user.email)
    assert (await limits.used(("resend.emails_per_day",), subject=user.email))["resend.emails_per_day"] == 1

    assert (await client.delete("/me", headers=auth_headers(user.id))).status_code == 204
    assert (await limits.used(("resend.emails_per_day",), subject=user.email))["resend.emails_per_day"] == 0


async def _record(user_id, cache_embedding=None):
    await store.record_query(
        user_id=user_id,
        question="q",
        answer="a",
        sources=[],
        cache_hit=False,
        tokens_used=100,
        tokens_saved=0,
        cache_embedding=cache_embedding,
    )


async def test_clear_cache_keeps_documents_and_history(client, make_user):
    user = await make_user()
    await seed_document(user.id, "kept", seed=51)
    await _record(user.id, cache_embedding=fake_embedding(51))

    assert (await client.delete("/cache", headers=auth_headers(user.id))).status_code == 204
    assert await store.find_nearest(user.id, fake_embedding(51)) is None
    assert len((await client.get("/documents", headers=auth_headers(user.id))).json()) == 1
    assert len((await client.get("/history", headers=auth_headers(user.id))).json()) == 1


async def test_history_carries_tokens_and_node_metrics(client, make_user):
    user = await make_user()
    metrics = [
        {"node": "check_cache", "duration_ms": 110, "tokens": 0, "tokens_saved": 0, "cache_hit": False, "similarity": 0.81},
        {"node": "rerank", "duration_ms": 780, "tokens": 0, "tokens_saved": 0, "cache_hit": False, "similarity": None},
    ]
    await store.record_query(
        user_id=user.id,
        question="q",
        answer="a",
        sources=[],
        cache_hit=False,
        tokens_used=807,
        tokens_saved=0,
        cache_embedding=None,
        node_metrics=metrics,
    )

    [row] = (await client.get("/history", headers=auth_headers(user.id))).json()
    assert row["tokens_used"] == 807
    assert row["node_metrics"] == metrics


async def test_clear_history_keeps_cache(client, make_user):
    user = await make_user()
    await _record(user.id, cache_embedding=fake_embedding(52))

    assert (await client.delete("/history", headers=auth_headers(user.id))).status_code == 204
    assert (await client.get("/history", headers=auth_headers(user.id))).json() == []
    assert (await store.find_nearest(user.id, fake_embedding(52))).answer == "a"


async def test_delete_all_documents_also_invalidates_cache(client, make_user):
    user, other = await make_user(), await make_user()
    await seed_document(user.id, "mine", seed=53)
    await seed_document(other.id, "theirs", seed=54)
    await _record(user.id, cache_embedding=fake_embedding(53))

    assert (await client.delete("/documents", headers=auth_headers(user.id))).status_code == 204
    assert (await client.get("/documents", headers=auth_headers(user.id))).json() == []
    assert await store.find_nearest(user.id, fake_embedding(53)) is None
    assert len((await client.get("/documents", headers=auth_headers(other.id))).json()) == 1


async def test_daily_query_limit(client, make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "content", seed=31)
    await store.record_query(
        user_id=user.id, question="q", answer="a", sources=[], cache_hit=False, tokens_used=1, tokens_saved=0, cache_embedding=None
    )
    monkeypatch.setattr(settings, "queries_per_day", 1)
    monkeypatch.setattr(settings, "query_min_interval_seconds", 0)
    response = await client.post("/query", json={"question": "again"}, headers=auth_headers(user.id))
    assert response.status_code == 429
    assert "Daily limit" in response.json()["detail"]


async def test_questions_are_spaced_apart(client, make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "content", seed=32)
    await store.record_query(
        user_id=user.id, question="q", answer="a", sources=[], cache_hit=True, tokens_used=0, tokens_saved=7, cache_embedding=None
    )
    monkeypatch.setattr(settings, "query_min_interval_seconds", 3600)
    response = await client.post("/query", json={"question": "again"}, headers=auth_headers(user.id))
    assert response.status_code == 429
    assert response.json()["detail"] == "Please wait 3600 seconds between questions."


async def test_document_and_storage_limits(client, make_user, monkeypatch):
    user = await make_user()
    await seed_document(user.id, "content", seed=41, size_bytes=900_000)
    upload = {"file": ("notes.txt", b"hello world")}

    monkeypatch.setattr(settings, "max_documents", 1)
    response = await client.post("/ingest", files=upload, headers=auth_headers(user.id))
    assert response.status_code == 429
    assert response.json()["detail"] == "Document limit of 1 reached. Delete the current document to upload another."

    monkeypatch.setattr(settings, "max_documents", 10)
    monkeypatch.setattr(settings, "max_storage_mb", 0)
    assert (await client.post("/ingest", files=upload, headers=auth_headers(user.id))).status_code == 429


async def test_unsupported_upload_is_415(client, make_user):
    user = await make_user()
    response = await client.post("/ingest", files={"file": ("photo.png", b"\x89PNG")}, headers=auth_headers(user.id))
    assert response.status_code == 415


async def test_database_outage_is_503_not_500(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.auth import service as auth

    async def unavailable(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(auth, "request_otp", unavailable)
    response = await client.post("/auth/request-otp", json={"email": "outage@example.com", "accepted_terms": True})
    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


def test_parse_pinecone_rerank_response():
    payload = {"data": [{"index": 2, "score": 0.9}, {"index": 0, "score": 0.1}]}
    assert parse_rerank_response(payload, 3) == [0.1, 0.0, 0.9]
