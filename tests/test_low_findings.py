import json
import sys
import types
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.auth import service
from app.config import Settings, settings
from app.db.models import OtpCode, ServiceUsage
from app.db.session import SessionLocal


@pytest.fixture
def resend(monkeypatch):
    sent = []
    state = {"status": 200}
    real = httpx.AsyncClient

    def handler(request):
        sent.append(json.loads(request.content))
        if state["status"] >= 400:
            return httpx.Response(state["status"], json={"message": f"cannot deliver to {sent[-1]['to'][0]}"})
        return httpx.Response(200, json={"id": "email-1"})

    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))

    async def no_counting(*args, **kwargs):
        return None

    monkeypatch.setattr(service.limits, "add", no_counting)
    return sent, state


async def test_the_login_code_is_not_in_the_subject(resend):
    sent, _ = resend
    await service.send_otp_email("jane@example.com", "123456")
    assert "123456" not in sent[0]["subject"]
    assert "123456" in sent[0]["text"]


async def test_a_resend_failure_does_not_carry_the_response_body(resend):
    _, state = resend
    state["status"] = 422
    with pytest.raises(service.EmailDeliveryError) as raised:
        await service.send_otp_email("jane@example.com", "123456")
    assert str(raised.value) == "Resend returned 422"
    assert "jane@example.com" not in str(raised.value)


async def test_old_login_records_are_forgotten(migrated_db):
    now = datetime.now(UTC)
    marker = uuid.uuid4().hex
    old_email, new_email = f"old-{marker}@example.com", f"new-{marker}@example.com"
    async with SessionLocal() as session:
        for email, created in ((old_email, now - timedelta(days=8)), (new_email, now - timedelta(days=1))):
            session.add(OtpCode(email=email, ip="203.0.113.7", code_hash="x", expires_at=created, created_at=created))
        session.add(ServiceUsage(quota_key=f"resend.emails_per_day|{old_email}", period_start=date.today() - timedelta(days=8), used=1))
        session.add(ServiceUsage(quota_key=f"resend.emails_per_day|{new_email}", period_start=date.today(), used=1))
        await session.commit()

        await service.forget_old_login_records(session, now)
        await session.commit()

        codes = await session.scalar(select(func.count()).where(OtpCode.email.in_((old_email, new_email))))
        counters = await session.scalar(select(func.count()).where(ServiceUsage.quota_key.contains(marker)))
    assert codes == 1 and counters == 1


def test_login_codes_can_be_keyed_apart_from_sessions(monkeypatch):
    shared = service.hash_code("jane@example.com", "123456")
    monkeypatch.setattr(settings, "otp_hmac_secret", "a-separate-secret-that-is-long-enough-000")
    assert service.hash_code("jane@example.com", "123456") != shared
    with pytest.raises(ValueError, match="OTP_HMAC_SECRET"):
        Settings(jwt_secret="x" * 40, otp_hmac_secret="short")


def test_local_models_load_a_pinned_revision(monkeypatch):
    from app import embeddings
    from app.retrieval import rerank

    loaded = {}
    fake = types.ModuleType("sentence_transformers")
    fake.SentenceTransformer = lambda name, revision=None: loaded.setdefault("embedding", (name, revision))
    fake.CrossEncoder = lambda name, max_length=None, revision=None: loaded.setdefault("rerank", (name, revision))
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    embeddings.get_model.cache_clear()
    rerank.get_reranker.cache_clear()
    try:
        embeddings.get_model()
        rerank.get_reranker()
    finally:
        embeddings.get_model.cache_clear()
        rerank.get_reranker.cache_clear()
    assert loaded["embedding"] == (settings.embedding_model, settings.embedding_model_revision)
    assert loaded["rerank"] == (settings.reranker_model, settings.reranker_model_revision)
    assert len(settings.embedding_model_revision) == 40 and len(settings.reranker_model_revision) == 40
