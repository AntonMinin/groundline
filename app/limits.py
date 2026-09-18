import calendar
import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app import alerts, events, ratelimit
from app.config import settings
from app.db.models import ServiceUsage
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

DEEPINFRA_BALANCE_URL = "https://api.deepinfra.com/payment/checklist?compute_owed=true"
BALANCE_CACHE_SECONDS = 300


@dataclass(frozen=True)
class Quota:
    key: str
    service: str
    title: str
    limit: float | None
    period: str
    source: str
    unit: str
    pricing_url: str
    paid: bool = False
    enforced: bool = False
    note: str = ""


QUOTAS = (
    Quota(
        key="groq.requests_per_day",
        service="Groq",
        title="Requests",
        limit=1000,
        period="day",
        source="headers",
        unit="requests",
        pricing_url="https://console.groq.com/docs/rate-limits",
        enforced=True,
    ),
    Quota(
        key="groq.tokens_per_day",
        service="Groq",
        title="Tokens",
        limit=200_000,
        period="day",
        source="local",
        unit="tokens",
        pricing_url="https://console.groq.com/docs/rate-limits",
        enforced=True,
        note="Groq headers expose the daily request quota and the per-minute token quota, but not the daily one",
    ),
    Quota(
        key="deepinfra.spend_per_month",
        service="DeepInfra",
        title="Spend",
        limit=None,
        period="month",
        source="local",
        unit="usd",
        pricing_url="https://deepinfra.com/pricing",
        paid=True,
        enforced=True,
        note="Prepaid balance, not a free tier: embedding tokens priced at DEEPINFRA_PRICE_PER_1M",
    ),
    Quota(
        key="pinecone.rerank_units_per_month",
        service="Pinecone",
        title="Rerank units",
        limit=500,
        period="month",
        source="local",
        unit="units",
        pricing_url="https://www.pinecone.io/pricing/",
        enforced=True,
        note="Counted from usage.rerank_units in each response",
    ),
    Quota(
        key="resend.emails_per_day",
        service="Resend",
        title="Emails today",
        limit=100,
        period="day",
        source="headers",
        unit="emails",
        pricing_url="https://resend.com/pricing",
        enforced=True,
    ),
    Quota(
        key="resend.emails_per_month",
        service="Resend",
        title="Emails this month",
        limit=3000,
        period="month",
        source="headers",
        unit="emails",
        pricing_url="https://resend.com/pricing",
        enforced=True,
    ),
    Quota(
        key="langfuse.units_per_month",
        service="LangFuse",
        title="Units",
        limit=50_000,
        period="month",
        source="local",
        unit="units",
        pricing_url="https://langfuse.com/pricing",
        note="Approximate: one unit per traced model call, LangFuse exposes no usage API",
    ),
    Quota(
        key="upstash.commands_per_month",
        service="Upstash",
        title="Commands",
        limit=500_000,
        period="month",
        source="api",
        unit="commands",
        pricing_url="https://upstash.com/pricing",
        note="Counted in Redis itself, so the number is shared by every instance",
    ),
    Quota(
        key="turnstile.siteverify_per_month",
        service="Turnstile",
        title="Verifications",
        limit=None,
        period="month",
        source="local",
        unit="requests",
        pricing_url="https://developers.cloudflare.com/turnstile/plans/",
        note="Free plan has no verification cap, counted for visibility only",
    ),
    Quota(
        key="render.instance_hours_per_month",
        service="Render",
        title="Instance hours",
        limit=750,
        period="month",
        source="dashboard",
        unit="hours",
        pricing_url="https://render.com/docs/free",
        note="Not metered by the application, check the Render dashboard",
    ),
    Quota(
        key="supabase.egress_gb_per_month",
        service="Supabase",
        title="Egress",
        limit=5,
        period="month",
        source="dashboard",
        unit="GB",
        pricing_url="https://supabase.com/pricing",
        note="Not metered by the application, check the Supabase dashboard",
    ),
    Quota(
        key="vercel.bandwidth_gb_per_month",
        service="Vercel",
        title="Fast data transfer",
        limit=100,
        period="month",
        source="dashboard",
        unit="GB",
        pricing_url="https://vercel.com/pricing",
        note="Not metered by the application, check the Vercel dashboard",
    ),
)

REGISTRY = {quota.key: quota for quota in QUOTAS}
QUERY_KEYS = ("groq.requests_per_day", "groq.tokens_per_day", "pinecone.rerank_units_per_month")
INGEST_KEYS = ("deepinfra.spend_per_month",)
EMAIL_KEYS = ("resend.emails_per_day", "resend.emails_per_month")

_reported: dict[str, float] = {}
_findings: dict[str, dict] = {}
_balance: tuple[float, float] | None = None
_degraded = False


def degraded() -> bool:
    return _degraded


class LimitExceeded(Exception):
    def __init__(self, quota: Quota, resets: datetime):
        self.quota = quota
        self.resets = resets
        amount = f"${limit_of(quota):.2f}" if quota.unit == "usd" else f"{limit_of(quota):,.0f} {quota.unit}"
        super().__init__(
            f"{quota.service} limit reached ({quota.title.lower()}: {amount} per {quota.period}), "
            f"resets {resets:%Y-%m-%d %H:%M} UTC"
        )


def applies(quota: Quota) -> bool:
    if quota.key.startswith("deepinfra."):
        return settings.embedding_provider == "api"
    if quota.key.startswith("pinecone."):
        return settings.rerank_provider == "api"
    if quota.key.startswith("upstash."):
        return ratelimit.enabled()
    if quota.key.startswith("turnstile."):
        return bool(settings.turnstile_secret_key)
    if quota.key.startswith("langfuse."):
        return bool(settings.langfuse_public_key and settings.langfuse_secret_key)
    return True


def limit_of(quota: Quota) -> float | None:
    if quota.key == "deepinfra.spend_per_month":
        return settings.deepinfra_monthly_budget_usd
    return quota.limit


def period_start(period: str, now: datetime | None = None) -> date:
    today = (now or datetime.now(UTC)).date()
    return today.replace(day=1) if period == "month" else today


def resets_at(period: str, now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    if period == "month":
        _, days = calendar.monthrange(moment.year, moment.month)
        return datetime(moment.year, moment.month, days, tzinfo=UTC) + timedelta(days=1)
    return datetime(moment.year, moment.month, moment.day, tzinfo=UTC) + timedelta(days=1)


def days_left(period: str, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    if period != "month":
        return 1
    _, days = calendar.monthrange(moment.year, moment.month)
    return days - moment.day + 1


def report(key: str, used: float) -> None:
    _reported[key] = used


def report_groq_headers(headers) -> None:
    limit, remaining = headers.get("x-ratelimit-limit-requests"), headers.get("x-ratelimit-remaining-requests")
    if limit is None or remaining is None:
        return
    try:
        report("groq.requests_per_day", float(limit) - float(remaining))
    except ValueError:
        log.debug("Unparsable Groq rate limit headers: %s / %s", limit, remaining)


def report_resend_headers(headers) -> None:
    for key, header in (("resend.emails_per_day", "x-resend-daily-quota"), ("resend.emails_per_month", "x-resend-monthly-quota")):
        value = headers.get(header)
        if value is None:
            continue
        try:
            report(key, float(value))
        except ValueError:
            log.debug("Unparsable Resend quota header %s: %s", header, value)


def _key_with_subject(key: str, subject: str | None) -> str:
    return f"{key}|{subject}" if subject else key


async def add(key: str, amount: float = 1.0, subject: str | None = None) -> None:
    if amount <= 0:
        return
    quota = REGISTRY[key]
    row = insert(ServiceUsage).values(
        quota_key=_key_with_subject(key, subject), period_start=period_start(quota.period), used=amount
    )
    statement = row.on_conflict_do_update(
        index_elements=[ServiceUsage.quota_key, ServiceUsage.period_start],
        set_={"used": ServiceUsage.used + amount, "updated_at": datetime.now(UTC)},
    ).returning(ServiceUsage.used)
    try:
        async with SessionLocal() as session:
            total = await session.scalar(statement)
            await session.commit()
    except Exception:
        log.warning("Could not record usage for %s", key, exc_info=True)
        return
    limit = limit_of(quota)
    if subject is None and limit and total is not None:
        await alerts.quota_consumed(
            key, quota.service, quota.title, total, limit, quota.unit, resets_at(quota.period).strftime("%Y-%m-%d %H:%M UTC")
        )


async def used(keys: tuple[str, ...], subject: str | None = None) -> dict[str, float]:
    if not keys:
        return {}
    global _degraded
    stored = {_key_with_subject(key, subject): key for key in keys}
    try:
        async with SessionLocal() as session:
            rows = (await session.execute(select(ServiceUsage).where(ServiceUsage.quota_key.in_(stored)))).scalars()
            counters = {
                stored[row.quota_key]: row.used
                for row in rows
                if row.period_start == period_start(REGISTRY[stored[row.quota_key]].period)
            }
        _degraded = False
    except Exception:
        # ponytail: counters unreadable means limits stop being enforced, not that the app stops working.
        _degraded = True
        log.warning(
            "limits check degraded: usage counters unreadable, quotas are not enforced and reported as unknown",
            exc_info=True,
        )
        counters = {}
    if subject is None:
        counters.update({key: value for key, value in _reported.items() if key in stored})
    return {key: counters.get(key, 0.0) for key in keys}


async def ensure(*keys: str) -> None:
    enforced = tuple(
        key
        for key in keys
        if REGISTRY[key].enforced and limit_of(REGISTRY[key]) is not None and applies(REGISTRY[key])
    )
    counters = await used(enforced)
    for key in enforced:
        quota = REGISTRY[key]
        if counters[key] >= limit_of(quota):
            raise LimitExceeded(quota, resets_at(quota.period))


async def ensure_personal(key: str, subject: str, limit: int) -> None:
    if limit <= 0:
        return
    counters = await used((key,), subject=subject)
    if counters[key] >= limit:
        quota = REGISTRY[key]
        raise LimitExceeded(replace(quota, limit=limit, service=f"Your {quota.service.lower()}"), resets_at(quota.period))


async def deepinfra_balance() -> float | None:
    global _balance
    if not settings.embedding_api_key or settings.embedding_provider != "api":
        return None
    if _balance and time.monotonic() - _balance[0] < BALANCE_CACHE_SECONDS:
        return _balance[1]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                DEEPINFRA_BALANCE_URL, headers={"Authorization": f"Bearer {settings.embedding_api_key}"}
            )
            response.raise_for_status()
            balance = float(response.json()["stripe_balance"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        log.debug("DeepInfra balance endpoint unavailable", exc_info=True)
        return None
    _balance = (time.monotonic(), balance)
    return balance


def spend_for(tokens: int) -> float:
    return tokens / 1_000_000 * settings.deepinfra_price_per_1m


async def publish_snapshot() -> None:
    try:
        current = await snapshot()
        events.broadcast({"type": "limits", "services": current["services"], "degraded": current["degraded"]})
    except Exception:
        log.debug("Could not publish the limits snapshot", exc_info=True)


def mark_outdated(key: str, found: float | None, quote: str = "") -> None:
    if found is None:
        _findings.pop(key, None)
        return
    _findings[key] = {"found": found, "quote": quote, "checked_at": datetime.now(UTC).isoformat()}


def findings() -> dict[str, dict]:
    return dict(_findings)


async def snapshot(user_usage: dict | None = None) -> dict:
    keys = tuple(key for key, quota in REGISTRY.items() if applies(quota))
    counters = await used(keys)
    balance = await deepinfra_balance()
    upstash_commands = await ratelimit.commands_used()
    if upstash_commands is not None:
        counters["upstash.commands_per_month"] = upstash_commands
    services = []
    for key in keys:
        quota = REGISTRY[key]
        limit = limit_of(quota)
        consumed = None if quota.source == "dashboard" or _degraded else counters[key]
        remaining = None if limit is None or consumed is None else max(limit - consumed, 0.0)
        services.append(
            {
                "key": key,
                "service": quota.service,
                "title": quota.title,
                "limit": limit,
                "used": consumed,
                "remaining": remaining,
                "period": quota.period,
                "source": "degraded" if _degraded and quota.source != "dashboard" else quota.source,
                "provider_reported": key in _reported or (key == "upstash.commands_per_month" and upstash_commands is not None),
                "unit": quota.unit,
                "paid": quota.paid,
                "enforced": quota.enforced,
                "pricing_url": quota.pricing_url,
                "note": quota.note,
                "limit_outdated": key in _findings,
                "limit_found_on_page": _findings.get(key, {}).get("found"),
                "resets_at": resets_at(quota.period).isoformat(),
                "daily_budget": None if remaining is None else round(remaining / days_left(quota.period), 2),
                "provider_balance_usd": balance if key == "deepinfra.spend_per_month" else None,
            }
        )
    return {
        "services": services,
        "personal": user_usage or [],
        "degraded": _degraded,
        "checked_at": datetime.now(UTC).isoformat(),
    }
