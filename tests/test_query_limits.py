import asyncio

import pytest
from sqlalchemy import update

from app.api import routes
from app.config import settings
from app.db.models import User
from app.db.session import SessionLocal
from app.graph import store
from tests.conftest import auth_headers, seed_document


@pytest.fixture
def pipeline(monkeypatch):
    calls = {"use_cache": [], "release": asyncio.Event()}

    async def run_query(user_id, question, use_cache=True):
        calls["use_cache"].append(use_cache)
        yield {"type": "token", "text": "answer"}
        await calls["release"].wait()
        yield {"type": "done", "sources": [], "cache_hit": False}

    monkeypatch.setattr(routes, "run_query", run_query)
    monkeypatch.setattr(settings, "query_min_interval_seconds", 0)
    monkeypatch.setattr(routes, "_answering", {})
    return calls


async def user_with_document(make_user, role: str = "user", seed: int = 60):
    user = await make_user()
    if role != "user":
        async with SessionLocal() as session:
            await session.execute(update(User).where(User.id == user.id).values(role=role))
            await session.commit()
    await seed_document(user.id, "content", seed=seed)
    return user


async def spend(user_id, tokens: int) -> None:
    await store.record_query(
        user_id=user_id, question="q", answer="a", sources=[], cache_hit=False, tokens_used=tokens, tokens_saved=0,
        cache_embedding=None,
    )


async def test_a_regular_account_cannot_bypass_the_cache(client, make_user, pipeline):
    user = await user_with_document(make_user, seed=61)
    response = await client.post("/query", json={"question": "q", "use_cache": False}, headers=auth_headers(user.id))
    assert response.status_code == 403
    assert pipeline["use_cache"] == []


async def test_the_daily_token_budget_stops_a_regular_account(client, make_user, pipeline, monkeypatch):
    monkeypatch.setattr(settings, "user_tokens_per_day", 1000)
    user = await user_with_document(make_user, seed=62)
    await spend(user.id, 1000)
    response = await client.post("/query", json={"question": "q"}, headers=auth_headers(user.id))
    assert response.status_code == 429
    assert "1,000 language-model tokens" in response.json()["detail"]


@pytest.mark.parametrize("role", ["eval", "admin"])
async def test_evaluation_accounts_bypass_the_cache_and_the_token_budget(client, make_user, pipeline, monkeypatch, role):
    monkeypatch.setattr(settings, "user_tokens_per_day", 1000)
    user = await user_with_document(make_user, role=role, seed=63)
    await spend(user.id, 5000)
    pipeline["release"].set()
    response = await client.post("/query", json={"question": "q", "use_cache": False}, headers=auth_headers(user.id))
    assert response.status_code == 200
    assert pipeline["use_cache"] == [False]


async def test_parallel_questions_from_one_account_are_refused(client, make_user, pipeline):
    user = await user_with_document(make_user, seed=64)
    headers = auth_headers(user.id)
    first = asyncio.create_task(client.post("/query", json={"question": "first"}, headers=headers))
    for _ in range(100):
        if user.id in routes._answering:
            break
        await asyncio.sleep(0.01)

    burst = await asyncio.gather(*(client.post("/query", json={"question": "more"}, headers=headers) for _ in range(5)))
    assert [response.status_code for response in burst] == [429] * 5
    assert "already being answered" in burst[0].json()["detail"]

    pipeline["release"].set()
    assert (await first).status_code == 200
    assert user.id not in routes._answering
    assert (await client.post("/query", json={"question": "next"}, headers=headers)).status_code == 200


async def test_a_refused_question_does_not_block_the_next_one(client, make_user, pipeline, monkeypatch):
    user = await user_with_document(make_user, seed=65)
    monkeypatch.setattr(settings, "queries_per_day", 0)
    assert (await client.post("/query", json={"question": "q"}, headers=auth_headers(user.id))).status_code == 429
    assert user.id not in routes._answering


def test_a_stale_claim_expires(monkeypatch):
    monkeypatch.setattr(routes, "_answering", {"u": 0.0})
    monkeypatch.setattr(routes.time, "monotonic", lambda: routes.ANSWERING_STALE_SECONDS + 1)
    routes._claim_answering("u")
    assert routes._answering["u"] == routes.ANSWERING_STALE_SECONDS + 1
