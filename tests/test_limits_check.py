import json

import pytest
from sqlalchemy import delete

from app import alerts, limits, limits_check
from app.config import settings
from app.db.models import ServiceUsage
from app.db.session import SessionLocal
from tests.conftest import auth_headers


@pytest.fixture
def telegram(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "token")
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    alerts._sent.clear()
    limits._findings.clear()
    sent: list[str] = []

    async def capture(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(alerts, "send", capture)
    yield sent
    alerts._sent.clear()
    limits._findings.clear()


@pytest.fixture
async def clean_service_usage(migrated_db):
    async with SessionLocal() as session:
        await session.execute(delete(ServiceUsage))
        await session.commit()


@pytest.fixture
def pricing_page(monkeypatch):
    def serve(limit_on_page, quote="free plan includes it"):
        async def fetch(url):
            return "pricing page text"

        async def complete(name, messages, **kwargs):
            return json.dumps({"limit": limit_on_page, "quote": quote})

        monkeypatch.setattr(limits_check, "fetch_page", fetch)
        monkeypatch.setattr(limits_check.llm, "complete", complete)

    return serve


def test_page_text_strips_markup_and_scripts():
    html = "<html><head><style>.a{color:red}</style><script>var x = 1;</script></head><body><p>100 emails  a day</p></body></html>"
    assert limits_check.page_text(html) == "100 emails a day"


def test_parse_extraction_handles_nulls_and_garbage():
    assert limits_check.parse_extraction('{"limit": 3000, "quote": "3,000 per month"}') == (3000.0, "3,000 per month")
    assert limits_check.parse_extraction('{"limit": null}') == (None, "")
    assert limits_check.parse_extraction("not json") == (None, "")


async def test_matching_limit_leaves_no_finding(telegram, pricing_page):
    quota = limits.REGISTRY["resend.emails_per_day"]
    pricing_page(100)
    assert await limits_check.check_quota(quota) == 100
    assert limits.findings() == {}
    assert telegram == []


async def test_changed_limit_is_flagged_and_alerted_but_not_applied(telegram, pricing_page):
    quota = limits.REGISTRY["resend.emails_per_day"]
    pricing_page(50, quote="50 emails a day on the free plan")
    assert await limits_check.check_quota(quota) == 50

    assert limits.limit_of(quota) == 100
    finding = limits.findings()["resend.emails_per_day"]
    assert finding["found"] == 50 and "50 emails" in finding["quote"]
    assert len(telegram) == 1
    assert "Resend" in telegram[0] and "100" in telegram[0] and "50" in telegram[0]
    assert quota.pricing_url in telegram[0]


async def test_outdated_alert_is_not_repeated_within_a_day(telegram, pricing_page):
    quota = limits.REGISTRY["resend.emails_per_day"]
    pricing_page(50)
    await limits_check.check_quota(quota)
    await limits_check.check_quota(quota)
    assert len(telegram) == 1


async def test_unreadable_page_changes_nothing(telegram, monkeypatch):
    async def no_page(url):
        return None

    monkeypatch.setattr(limits_check, "fetch_page", no_page)
    assert await limits_check.check_quota(limits.REGISTRY["groq.requests_per_day"]) is None
    assert limits.findings() == {} and telegram == []


async def test_flag_reaches_the_limits_endpoint(client, make_user, telegram, pricing_page, migrated_db):
    pricing_page(50)
    await limits_check.check_quota(limits.REGISTRY["resend.emails_per_day"])
    user = await make_user()
    body = (await client.get("/limits", headers=auth_headers(user.id))).json()
    quota = next(item for item in body["services"] if item["key"] == "resend.emails_per_day")
    assert quota["limit_outdated"] is True
    assert quota["limit"] == 100
    assert quota["limit_found_on_page"] == 50


async def test_the_extractor_runs_on_its_own_model(telegram, monkeypatch):
    monkeypatch.setattr(settings, "limits_check_model", "openai/gpt-oss-20b")
    seen = {}

    async def fetch(url):
        return "pricing page text"

    async def complete(name, messages, **kwargs):
        seen.update(kwargs)
        return json.dumps({"limit": 100, "quote": ""})

    monkeypatch.setattr(limits_check, "fetch_page", fetch)
    monkeypatch.setattr(limits_check.llm, "complete", complete)
    await limits_check.check_quota(limits.REGISTRY["resend.emails_per_day"])

    assert seen["model"] == "openai/gpt-oss-20b"
    assert seen["model"] != settings.llm_model


async def test_checks_are_spaced_out_instead_of_running_as_one_burst(telegram, monkeypatch, pricing_page):
    pricing_page(100)
    pauses = []

    async def fake_sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(limits_check.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(settings, "limits_check_spacing_seconds", 60)
    results = await limits_check.check_all()

    assert len(results) > 1
    assert pauses == [60] * (len(results) - 1)


async def test_the_daily_run_is_claimed_once_a_day(clean_service_usage):
    assert await limits.claim_daily_run("limits_check") is True
    assert await limits.claim_daily_run("limits_check") is False
    assert await limits.claim_daily_run("something_else") is True


async def test_autocheck_does_not_start_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "limits_autocheck_enabled", False)
    await limits_check.start()
    assert limits_check._task is None


async def test_red_zone_and_exhaustion_alert_once_each(telegram, migrated_db, monkeypatch):
    async with SessionLocal() as session:
        await session.execute(delete(ServiceUsage))
        await session.commit()
    monkeypatch.setattr(settings, "embedding_provider", "api")
    monkeypatch.setattr(settings, "deepinfra_monthly_budget_usd", 1.0)

    await limits.add("deepinfra.spend_per_month", 0.5)
    assert telegram == []

    await limits.add("deepinfra.spend_per_month", 0.35)
    assert len(telegram) == 1 and "red zone" in telegram[0]

    await limits.add("deepinfra.spend_per_month", 0.05)
    assert len(telegram) == 1

    await limits.add("deepinfra.spend_per_month", 0.2)
    assert len(telegram) == 2 and "exhausted" in telegram[1]


async def test_alerts_are_silent_without_telegram_configuration(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    assert alerts.enabled() is False
    await alerts.send("nothing happens")
