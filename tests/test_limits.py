from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from app import limits
from app.config import settings
from app.db.models import ServiceUsage
from app.db.session import SessionLocal
from tests.conftest import auth_headers


@pytest.fixture
async def clean_counters(migrated_db):
    limits._reported.clear()
    limits._degraded = False
    async with SessionLocal() as session:
        await session.execute(delete(ServiceUsage))
        await session.commit()
    yield
    limits._reported.clear()
    limits._degraded = False


async def test_counters_accumulate_within_the_period(clean_counters):
    await limits.add("groq.tokens_per_day", 120)
    await limits.add("groq.tokens_per_day", 80)
    assert (await limits.used(("groq.tokens_per_day",)))["groq.tokens_per_day"] == 200


async def test_ensure_raises_once_the_limit_is_reached(clean_counters):
    await limits.add("groq.requests_per_day", limits.REGISTRY["groq.requests_per_day"].limit)
    with pytest.raises(limits.LimitExceeded) as exc:
        await limits.ensure("groq.requests_per_day")
    assert "Groq" in str(exc.value) and "resets" in str(exc.value)
    assert exc.value.resets > datetime.now(UTC)


async def test_personal_limits_are_counted_per_subject(clean_counters, monkeypatch):
    monkeypatch.setattr(settings, "resend_per_user_per_day", 2)
    for _ in range(2):
        await limits.add("resend.emails_per_day", subject="a@example.com")
    with pytest.raises(limits.LimitExceeded):
        await limits.ensure_personal("resend.emails_per_day", "a@example.com", 2)
    await limits.ensure_personal("resend.emails_per_day", "b@example.com", 2)


async def test_provider_headers_win_over_local_counters(clean_counters):
    await limits.add("groq.requests_per_day", 5)
    limits.report_groq_headers({"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "940"})
    assert (await limits.used(("groq.requests_per_day",)))["groq.requests_per_day"] == 60


def test_resend_headers_are_parsed():
    limits.report_resend_headers({"x-resend-daily-quota": "12", "x-resend-monthly-quota": "340"})
    assert limits._reported["resend.emails_per_day"] == 12
    assert limits._reported["resend.emails_per_month"] == 340
    limits._reported.clear()


def test_monthly_daily_budget_and_reset():
    moment = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
    assert limits.days_left("month", moment) == 13
    assert limits.resets_at("month", moment) == datetime(2026, 10, 1, tzinfo=UTC)
    assert limits.resets_at("day", moment) == datetime(2026, 9, 19, tzinfo=UTC)
    assert limits.period_start("month", moment).day == 1


def test_deepinfra_budget_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "deepinfra_monthly_budget_usd", 7.5)
    assert limits.limit_of(limits.REGISTRY["deepinfra.spend_per_month"]) == 7.5
    assert limits.REGISTRY["deepinfra.spend_per_month"].paid is True
    monkeypatch.setattr(settings, "deepinfra_price_per_1m", 0.01)
    assert limits.spend_for(2_000_000) == pytest.approx(0.02)


def test_langfuse_keys_from_the_env_file_reach_the_sdk_environment(monkeypatch):
    from app import config

    monkeypatch.setattr(settings, "langfuse_public_key", "pk-from-dotenv")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-from-dotenv")
    monkeypatch.setattr(settings, "langfuse_host", "https://langfuse.example.com")

    environment = {}
    config.export_sdk_env(environment)
    assert environment["LANGFUSE_PUBLIC_KEY"] == "pk-from-dotenv"
    assert environment["LANGFUSE_SECRET_KEY"] == "sk-from-dotenv"
    assert environment["LANGFUSE_HOST"] == "https://langfuse.example.com"
    assert limits.applies(limits.REGISTRY["langfuse.units_per_month"]) is True

    preset = {"LANGFUSE_PUBLIC_KEY": "pk-from-real-env"}
    config.export_sdk_env(preset)
    assert preset["LANGFUSE_PUBLIC_KEY"] == "pk-from-real-env"


def test_inactive_providers_are_not_enforced(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    monkeypatch.setattr(settings, "rerank_provider", "local")
    assert limits.applies(limits.REGISTRY["deepinfra.spend_per_month"]) is False
    assert limits.applies(limits.REGISTRY["pinecone.rerank_units_per_month"]) is False
    assert limits.applies(limits.REGISTRY["groq.requests_per_day"]) is True


async def test_local_providers_never_block_a_query(clean_counters, monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "local")
    monkeypatch.setattr(settings, "rerank_provider", "local")
    await limits.add("pinecone.rerank_units_per_month", 5000)
    await limits.ensure(*limits.QUERY_KEYS)


def _break_counters(monkeypatch):
    class Broken:
        def __call__(self, *args, **kwargs):
            raise RuntimeError('relation "service_usage" does not exist')

    monkeypatch.setattr("app.limits.SessionLocal", Broken())


async def test_unreadable_counters_do_not_break_the_request(clean_counters, monkeypatch):
    _break_counters(monkeypatch)
    assert await limits.used(("groq.requests_per_day",)) == {"groq.requests_per_day": 0.0}
    await limits.ensure("groq.requests_per_day")
    assert limits.degraded() is True


async def test_degraded_counters_are_reported_as_unknown_not_as_zero(client, make_user, clean_counters, monkeypatch, caplog):
    user = await make_user()
    _break_counters(monkeypatch)
    with caplog.at_level("WARNING"):
        body = (await client.get("/limits", headers=auth_headers(user.id))).json()

    assert body["degraded"] is True
    groq = next(item for item in body["services"] if item["key"] == "groq.tokens_per_day")
    assert groq["used"] is None and groq["remaining"] is None and groq["daily_budget"] is None
    assert groq["source"] == "degraded"
    assert groq["limit"] == 200_000
    assert "limits check degraded" in caplog.text


async def test_the_degraded_flag_clears_on_the_next_successful_read(clean_counters, monkeypatch):
    _break_counters(monkeypatch)
    await limits.used(("groq.requests_per_day",))
    assert limits.degraded() is True
    monkeypatch.undo()
    await limits.used(("groq.requests_per_day",))
    assert limits.degraded() is False


async def test_limits_endpoint_reports_services_and_personal_limits(client, make_user, clean_counters):
    user = await make_user()
    await limits.add("groq.tokens_per_day", 50_000)
    response = await client.get("/limits", headers=auth_headers(user.id))
    assert response.status_code == 200
    body = response.json()

    groq = next(item for item in body["services"] if item["key"] == "groq.tokens_per_day")
    assert groq["used"] == 50_000
    assert groq["remaining"] == 150_000
    assert groq["period"] == "day"
    assert groq["source"] == "local"
    assert groq["provider_reported"] is False
    assert groq["pricing_url"].startswith("https://")

    render = next(item for item in body["services"] if item["service"] == "Render")
    assert render["used"] is None and render["source"] == "dashboard"

    assert [item["title"] for item in body["personal"]][:2] == ["Questions today", "Login codes today"]


async def test_ingest_is_blocked_when_the_deepinfra_budget_is_spent(client, make_user, clean_counters, monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "api")
    monkeypatch.setattr(settings, "deepinfra_monthly_budget_usd", 1.0)
    await limits.add("deepinfra.spend_per_month", 1.0)
    user = await make_user()
    response = await client.post(
        "/ingest", headers=auth_headers(user.id), files={"file": ("notes.md", b"hello", "text/markdown")}
    )
    assert response.status_code == 429
    assert "DeepInfra" in response.json()["detail"]
