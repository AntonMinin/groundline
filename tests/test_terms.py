import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from app.api.routes import MAX_EMAIL_CHARS, MAX_FILENAME_CHARS, MAX_IDEMPOTENCY_KEY_CHARS
from app.config import CURRENT_TERMS_VERSION
from app.db.models import OtpCode, User
from app.db.session import SessionLocal
from tests.conftest import auth_headers


def test_the_published_terms_date_and_the_recorded_version_do_not_drift():
    source = Path(__file__).resolve().parent.parent / "landing" / "src" / "legal.js"
    published = re.search(r"export const UPDATED = '([^']+)'", source.read_text(encoding="utf-8")).group(1)
    assert published == CURRENT_TERMS_VERSION


async def _stored(email: str) -> User:
    async with SessionLocal() as session:
        return await session.scalar(select(User).where(User.email == email))


async def _clear_resend_cooldown(email: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            update(OtpCode)
            .where(OtpCode.email == email.lower())
            .values(created_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await session.commit()


async def _register(client, sent_codes, email: str) -> User:
    assert (await client.post("/auth/request-otp", json={"email": email, "accepted_terms": True})).status_code == 202
    response = await client.post("/auth/verify-otp", json={"email": email, "code": sent_codes[email.lower()]})
    assert response.status_code == 200
    return response


async def test_registration_records_when_and_which_terms_were_accepted(client, sent_codes):
    email = f"terms-{uuid.uuid4().hex}@example.com"
    response = await _register(client, sent_codes, email)
    assert response.json()["terms_required"] is False

    user = await _stored(email)
    assert user.terms_version == CURRENT_TERMS_VERSION
    assert user.terms_accepted_at is not None


async def test_signing_in_again_keeps_the_original_acceptance(client, sent_codes):
    email = f"terms-{uuid.uuid4().hex}@example.com"
    await _register(client, sent_codes, email)
    first = await _stored(email)

    await _clear_resend_cooldown(email)
    await _register(client, sent_codes, email)
    again = await _stored(email)
    assert again.terms_accepted_at == first.terms_accepted_at
    assert again.terms_version == first.terms_version


@pytest.mark.parametrize("version", [None, "1900-01-01"])
async def test_a_user_without_the_current_terms_is_blocked_until_they_accept(client, make_user, version):
    user = await make_user(terms_version=version)
    headers = auth_headers(user.id)

    assert (await client.get("/me", headers=headers)).json()["terms_required"] is True
    assert (await client.get("/documents", headers=headers)).status_code == 403
    assert (await client.get("/stats", headers=headers)).status_code == 403

    accepted = await client.post("/me/accept-terms", headers=headers)
    assert accepted.status_code == 200 and accepted.json()["terms_required"] is False
    assert (await client.get("/me", headers=headers)).json()["terms_required"] is False
    assert (await client.get("/documents", headers=headers)).status_code == 200

    stored = await _stored(user.email)
    assert stored.terms_version == CURRENT_TERMS_VERSION and stored.terms_accepted_at is not None


async def test_a_blocked_user_can_still_read_their_account_and_delete_it(client, make_user):
    user = await make_user(terms_version=None)
    headers = auth_headers(user.id)
    assert (await client.get("/me", headers=headers)).status_code == 200
    assert (await client.delete("/me", headers=headers)).status_code == 204


def _email_of_length(length: int) -> str:
    domain = "@example.com"
    return "a" * (length - len(domain)) + domain


@pytest.mark.parametrize(
    "length,expected", [(MAX_EMAIL_CHARS, 202), (MAX_EMAIL_CHARS + 1, 422)]
)
async def test_email_length_is_validated_not_crashed_on(client, sent_codes, length, expected):
    response = await client.post(
        "/auth/request-otp", json={"email": _email_of_length(length), "accepted_terms": True}
    )
    assert response.status_code == expected


@pytest.mark.parametrize("length,expected", [(MAX_FILENAME_CHARS, 202), (MAX_FILENAME_CHARS + 1, 422)])
async def test_file_name_length_is_validated_not_crashed_on(client, make_user, workers, length, expected):
    user = await make_user()
    name = "a" * (length - len(".md")) + ".md"
    response = await client.post(
        "/ingest", headers=auth_headers(user.id), files={"file": (name, b"hello there", "text/markdown")}
    )
    assert response.status_code == expected


@pytest.mark.parametrize(
    "length,expected", [(MAX_IDEMPOTENCY_KEY_CHARS, 202), (MAX_IDEMPOTENCY_KEY_CHARS + 1, 422)]
)
async def test_idempotency_key_length_is_validated_not_crashed_on(client, make_user, workers, length, expected):
    user = await make_user()
    response = await client.post(
        "/ingest",
        headers={**auth_headers(user.id), "Idempotency-Key": "k" * length},
        files={"file": ("doc.md", b"hello there", "text/markdown")},
    )
    assert response.status_code == expected
