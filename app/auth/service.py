import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import OtpCode, User

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


class OtpRateLimitError(Exception):
    pass


def hash_code(email: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


class EmailDeliveryError(Exception):
    pass


async def send_otp_email(email: str, code: str) -> None:
    if not settings.resend_api_key:
        if not settings.dev_mode:
            raise EmailDeliveryError("RESEND_API_KEY is not configured")
        log.warning("DEV_MODE: OTP for %s: %s", email, code)
        return
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_from,
                "to": [email],
                "subject": f"Groundline login code: {code}",
                "text": f"Your Groundline login code is {code}. It expires in {settings.otp_ttl_minutes} minutes.",
            },
        )
        if response.is_error:
            raise EmailDeliveryError(f"Resend returned {response.status_code}: {response.text}")


async def request_otp(session: AsyncSession, email: str, ip: str | None) -> None:
    email = normalize_email(email)
    now = datetime.now(UTC)
    recent = await session.scalar(
        select(OtpCode.id).where(
            OtpCode.email == email,
            OtpCode.created_at > now - timedelta(seconds=settings.otp_resend_cooldown_seconds),
        )
    )
    if recent:
        raise OtpRateLimitError("Code was sent recently, try again later")
    if ip:
        sent_from_ip = await session.scalar(
            select(func.count()).where(OtpCode.ip == ip, OtpCode.created_at > now - timedelta(hours=1))
        )
        if sent_from_ip >= settings.otp_max_per_ip_per_hour:
            raise OtpRateLimitError("Too many code requests, try again later")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await session.execute(update(OtpCode).where(OtpCode.email == email, OtpCode.used.is_(False)).values(used=True))
    session.add(
        OtpCode(
            email=email,
            ip=ip,
            code_hash=hash_code(email, code),
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
            created_at=now,
        )
    )
    await session.commit()
    await send_otp_email(email, code)


async def verify_otp(session: AsyncSession, email: str, code: str) -> User:
    email = normalize_email(email)
    otp = await session.scalar(
        select(OtpCode)
        .where(OtpCode.email == email, OtpCode.used.is_(False))
        .order_by(OtpCode.created_at.desc())
        .with_for_update()
    )
    if otp is None or otp.expires_at < datetime.now(UTC) or otp.attempts >= settings.otp_max_attempts:
        raise AuthError("Invalid or expired code")
    if not hmac.compare_digest(otp.code_hash, hash_code(email, code.strip())):
        otp.attempts += 1
        await session.commit()
        raise AuthError("Invalid or expired code")
    otp.used = True
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        session.add(user)
    await session.commit()
    return user


def create_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.jwt_ttl_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Invalid token") from exc
