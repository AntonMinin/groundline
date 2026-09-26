import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from app.auth import service
from app.db.models import OtpCode
from app.db.session import SessionLocal
from tests.conftest import auth_headers


def _email() -> str:
    return f"Auth-{uuid.uuid4().hex}@Example.com"


async def test_otp_login_flow(client, sent_codes):
    email = _email()
    assert (await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})).status_code == 202
    code = sent_codes[email.lower()]

    response = await client.post("/auth/verify-otp", json={"email": email, "code": code, "terms_accepted": True})
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "groundline_session=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await client.get("/me")
    assert me.status_code == 200 and me.json()["email"] == email.lower()

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/me")).status_code == 401

    reused = await client.post("/auth/verify-otp", json={"email": email, "code": code, "terms_accepted": True})
    assert reused.status_code == 401


async def test_wrong_code_is_401_and_attempts_are_limited(client, sent_codes):
    email = _email()
    await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})
    code = sent_codes[email.lower()]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (await client.post("/auth/verify-otp", json={"email": email, "code": wrong})).status_code == 401
    assert (await client.post("/auth/verify-otp", json={"email": email, "code": code})).status_code == 401


async def test_expired_code_is_401(client, sent_codes):
    email = _email()
    await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})
    async with SessionLocal() as session:
        await session.execute(
            update(OtpCode)
            .where(OtpCode.email == email.lower())
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
        await session.commit()
    response = await client.post("/auth/verify-otp", json={"email": email, "code": sent_codes[email.lower()]})
    assert response.status_code == 401


async def test_resend_cooldown_is_429(client, sent_codes):
    email = _email()
    assert (await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})).status_code == 202
    assert (await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})).status_code == 429


async def test_requests_from_one_ip_are_limited(client, sent_codes, monkeypatch):
    from app.config import settings

    async with SessionLocal() as session:
        await session.execute(delete(OtpCode))
        await session.commit()
    monkeypatch.setattr(settings, "otp_max_per_ip_per_hour", 1)
    assert (await client.post("/auth/request-otp", json={"email": _email(), "accepted_terms": True})).status_code == 202
    assert (await client.post("/auth/request-otp", json={"email": _email(), "accepted_terms": True})).status_code == 429


async def test_turnstile_rejects_a_request_without_a_token(client, sent_codes, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "turnstile_secret_key", "secret")
    response = await client.post("/auth/request-otp", json={"email": _email(), "accepted_terms": True})
    assert response.status_code == 403
    assert not sent_codes


async def test_turnstile_rejects_a_token_cloudflare_refuses(client, sent_codes, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "turnstile_secret_key", "secret")

    async def refuse(payload):
        return {"success": False, "error-codes": ["invalid-input-response"]}

    monkeypatch.setattr(service, "_siteverify", refuse)
    response = await client.post("/auth/request-otp", json={"email": _email(), "turnstile_token": "bad", "accepted_terms": True})
    assert response.status_code == 403
    assert not sent_codes


async def test_turnstile_accepts_a_valid_token(client, sent_codes, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "turnstile_secret_key", "secret")
    seen = {}

    async def accept(payload):
        seen.update(payload)
        return {"success": True}

    monkeypatch.setattr(service, "_siteverify", accept)
    email = _email()
    response = await client.post("/auth/request-otp", json={"email": email, "turnstile_token": "good", "accepted_terms": True})
    assert response.status_code == 202
    assert seen["secret"] == "secret" and seen["response"] == "good"
    assert email.lower() in sent_codes


async def test_turnstile_is_skipped_without_a_secret(client, sent_codes):
    assert (await client.get("/config")).json()["turnstile_site_key"] == ""
    assert (await client.post("/auth/request-otp", json={"email": _email(), "accepted_terms": True})).status_code == 202


async def test_protected_routes_require_valid_token(client, make_user):
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Cookie": "groundline_session=garbage"})).status_code == 401
    user = await make_user()
    assert (await client.get("/me", headers=auth_headers(user.id))).status_code == 200


async def test_login_code_is_refused_without_accepting_the_terms(client, sent_codes):
    email = _email()
    response = await client.post("/auth/request-otp", json={"email": email})
    assert response.status_code == 422
    assert email.lower() not in sent_codes
