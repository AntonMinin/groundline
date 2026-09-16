import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, update

from app.auth import service
from app.db.models import OtpCode
from app.db.session import SessionLocal
from tests.conftest import auth_headers


@pytest.fixture
def sent_codes(monkeypatch):
    codes: dict[str, str] = {}

    async def capture(email, code):
        codes[email] = code

    monkeypatch.setattr(service, "send_otp_email", capture)
    return codes


def _email() -> str:
    return f"Auth-{uuid.uuid4().hex}@Example.com"


async def test_otp_login_flow(client, sent_codes):
    email = _email()
    assert (await client.post("/auth/request-otp", json={"email": email})).status_code == 202
    code = sent_codes[email.lower()]

    response = await client.post("/auth/verify-otp", json={"email": email, "code": code})
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "groundline_session=" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await client.get("/me")
    assert me.status_code == 200 and me.json()["email"] == email.lower()

    assert (await client.post("/auth/logout")).status_code == 204
    assert (await client.get("/me")).status_code == 401

    reused = await client.post("/auth/verify-otp", json={"email": email, "code": code})
    assert reused.status_code == 401


async def test_wrong_code_is_401_and_attempts_are_limited(client, sent_codes):
    email = _email()
    await client.post("/auth/request-otp", json={"email": email})
    code = sent_codes[email.lower()]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert (await client.post("/auth/verify-otp", json={"email": email, "code": wrong})).status_code == 401
    assert (await client.post("/auth/verify-otp", json={"email": email, "code": code})).status_code == 401


async def test_expired_code_is_401(client, sent_codes):
    email = _email()
    await client.post("/auth/request-otp", json={"email": email})
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
    assert (await client.post("/auth/request-otp", json={"email": email})).status_code == 202
    assert (await client.post("/auth/request-otp", json={"email": email})).status_code == 429


async def test_requests_from_one_ip_are_limited(client, sent_codes, monkeypatch):
    from app.config import settings

    async with SessionLocal() as session:
        await session.execute(delete(OtpCode))
        await session.commit()
    monkeypatch.setattr(settings, "otp_max_per_ip_per_hour", 1)
    assert (await client.post("/auth/request-otp", json={"email": _email()})).status_code == 202
    assert (await client.post("/auth/request-otp", json={"email": _email()})).status_code == 429


async def test_protected_routes_require_valid_token(client, make_user):
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Cookie": "groundline_session=garbage"})).status_code == 401
    user = await make_user()
    assert (await client.get("/me", headers=auth_headers(user.id))).status_code == 200
