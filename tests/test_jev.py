import json
import logging

import httpx
import pytest

from app import jev, limits
from app.config import settings

NOUL = {"is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}}
CHOICE = {"team": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": None, "technical": None}}}


@pytest.fixture
def jev_env(monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "jev_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "or-key")
    monkeypatch.setattr(settings, "typesafe_api_key", "")
    monkeypatch.setattr(jev, "_warned", set())
    spent: list[tuple[str, float]] = []

    async def ensure(*keys):
        return None

    async def add(key, amount=1.0, subject=None):
        spent.append((key, amount))

    monkeypatch.setattr(jev.limits, "ensure", ensure)
    monkeypatch.setattr(jev.limits, "add", add)
    return spent


@pytest.fixture
def transport(monkeypatch):
    seen: list[httpx.Request] = []
    state = {"handler": None}
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return state["handler"](request)

    monkeypatch.setattr(jev.httpx, "AsyncClient", lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs))
    return seen, state


def answer(payload: dict, usage: dict):
    return lambda request: httpx.Response(200, json={"model": "jev-1.13.0", "answers": payload, "usage": usage})


async def test_openrouter_request_and_reported_cost(jev_env, transport):
    seen, state = transport
    state["handler"] = answer(
        {"is_urgent": {"type": "noul", "noul": 0.95}}, {"input_tokens": 296, "output_tokens": 20, "cost": 0.00003}
    )
    answers = await jev.ask("test", "Payouts failing for 3 days", NOUL, 2000)
    assert answers == {"is_urgent": {"noul": 0.95}}
    request = seen[0]
    assert str(request.url) == "https://openrouter.ai/api/v1/systemone"
    assert request.headers["Authorization"] == "Bearer or-key"
    body = json.loads(request.content)
    assert body == {"model": settings.jev_model, "state": "Payouts failing for 3 days", "questions": NOUL}
    assert ("jev.spend_per_month", 0.00003) in jev_env


async def test_typesafe_request_and_priced_cost(jev_env, transport, monkeypatch):
    monkeypatch.setattr(settings, "jev_provider", "typesafe")
    monkeypatch.setattr(settings, "typesafe_api_key", "ts-key")
    seen, state = transport
    state["handler"] = answer(
        {"team": {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.9, "technical": 0.1}, "confidence": 0.8}},
        {"input_tokens": 1_000_000, "output_tokens": 30},
    )
    answers = await jev.ask("test", {"ticket": "charged twice"}, CHOICE, 2000)
    assert answers["team"] == {"choice": "billing", "probabilities": {"billing": 0.9, "technical": 0.1}, "confidence": 0.8}
    assert str(seen[0].url) == "https://api.typesafe.ai/v1/systemone"
    assert seen[0].headers["Authorization"] == "Bearer ts-key"
    assert ("jev.spend_per_month", pytest.approx(settings.jev_price_per_1m)) in jev_env


async def test_typesafe_without_key_falls_back_to_openrouter(jev_env, transport, monkeypatch, caplog):
    monkeypatch.setattr(settings, "jev_provider", "typesafe")
    seen, state = transport
    state["handler"] = answer({"is_urgent": {"type": "noul", "noul": 0.2}}, {"input_tokens": 10, "output_tokens": 1})
    with caplog.at_level(logging.WARNING, logger="app.jev"):
        assert await jev.ask("test", "hello", NOUL, 2000) == {"is_urgent": {"noul": 0.2}}
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/systemone"
    assert seen[0].headers["Authorization"] == "Bearer or-key"
    assert "using openrouter instead" in caplog.text


async def test_disabled_makes_no_request(jev_env, transport, monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", False)
    seen, _ = transport
    assert jev.enabled() is False
    assert await jev.ask("test", "hello", NOUL, 2000) is None
    assert seen == [] and jev_env == []


async def test_enabled_without_any_key_stays_off(jev_env, transport, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    seen, _ = transport
    assert jev.enabled() is False
    assert await jev.ask("test", "hello", NOUL, 2000) is None
    assert seen == []


def _timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(529, json={"detail": "overloaded"}),
        lambda request: httpx.Response(401, json={"detail": "bad key"}),
        _timeout,
        lambda request: httpx.Response(200, text="not json"),
        answer({}, {"input_tokens": 1}),
        answer({"is_urgent": {"type": "noul"}}, {"input_tokens": 1}),
    ],
    ids=["overloaded", "unauthorized", "timeout", "not-json", "missing-answer", "malformed-answer"],
)
async def test_failures_are_fail_open(jev_env, transport, handler):
    _, state = transport
    state["handler"] = handler
    assert await jev.ask("test", "hello", NOUL, 2000) is None
    assert jev_env == []


async def test_spent_budget_skips_jev(jev_env, transport, monkeypatch):
    async def exhausted(*keys):
        quota = limits.REGISTRY["jev.spend_per_month"]
        raise limits.LimitExceeded(quota, limits.resets_at(quota.period))

    monkeypatch.setattr(jev.limits, "ensure", exhausted)
    seen, _ = transport
    assert await jev.ask("test", "hello", NOUL, 2000) is None
    assert seen == []


def test_jev_quota_follows_the_switch(monkeypatch):
    quota = limits.REGISTRY["jev.spend_per_month"]
    monkeypatch.setattr(settings, "jev_enabled", False)
    assert limits.applies(quota) is False
    monkeypatch.setattr(settings, "jev_enabled", True)
    monkeypatch.setattr(settings, "jev_monthly_budget_usd", 2.5)
    assert limits.applies(quota) is True and limits.limit_of(quota) == 2.5
    assert quota.checkable is False


async def test_grounding_metric_is_appended_to_the_logged_query(make_user):
    from sqlalchemy import select

    from app.db.models import QueryLog
    from app.db.session import tenant_session
    from app.graph import store

    owner, stranger = await make_user(), await make_user()
    log_id, _ = await store.record_query(
        user_id=owner.id,
        question="q",
        answer="a",
        sources=[],
        cache_hit=False,
        tokens_used=1,
        tokens_saved=0,
        cache_embedding=None,
        node_metrics=[{"node": "generate_answer"}],
    )
    await store.append_node_metric(owner.id, log_id, {"node": "check_grounding", "jev": {"verdict": "supported"}})
    await store.append_node_metric(stranger.id, log_id, {"node": "intruder"})

    async with tenant_session(owner.id) as session:
        metrics = await session.scalar(select(QueryLog.node_metrics).where(QueryLog.id == log_id))
    assert [metric["node"] for metric in metrics] == ["generate_answer", "check_grounding"]
    assert metrics[1]["jev"] == {"verdict": "supported"}
