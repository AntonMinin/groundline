import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import delete

from app import limits, llm
from app.config import settings
from app.db.models import ServiceUsage
from app.db.session import SessionLocal
from tests.conftest import auth_headers

MESSAGES = [{"role": "user", "content": "How often are laptops replaced?"}]


async def forget_usage() -> None:
    limits._reported.clear()
    async with SessionLocal() as session:
        await session.execute(delete(ServiceUsage))
        await session.commit()


@pytest.fixture
async def counters(migrated_db):
    await forget_usage()
    yield
    await forget_usage()


@pytest.fixture
def groq(monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        usage = SimpleNamespace(total_tokens=500)
        if kwargs.get("stream"):
            async def chunks():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Every three years."))], usage=None)
                yield SimpleNamespace(choices=[], usage=usage)

            return chunks()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], usage=usage)

    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    return calls


async def spent(key: str, subject: str | None = None) -> float:
    return (await limits.used((key,), subject=subject))[key]


async def test_the_provider_count_is_recorded_for_the_service_and_the_person(counters, groq):
    user = str(uuid.uuid4())
    with llm.caller(uuid.UUID(user)):
        before = llm.spent()
        await llm.complete("rewrite_query", MESSAGES)
        assert llm.spent() - before == 500
    assert await spent("groq.tokens_per_day") == 500
    assert await spent("groq.requests_per_day") == 1
    assert await spent("groq.tokens_per_day", user) == 500
    assert await spent("groq.requests_per_day", user) == 1
    assert groq[0]["max_tokens"] == settings.llm_max_output_tokens


async def test_the_streamed_answer_counts_the_usage_of_its_last_chunk(counters, groq):
    with llm.caller(uuid.uuid4()):
        parts = [part async for part in llm.stream("generate_answer", MESSAGES)]
    assert parts == ["Every three years."]
    assert groq[0]["stream_options"] == {"include_usage": True}
    assert await spent("groq.tokens_per_day") == 500


async def test_a_person_over_budget_is_stopped_before_the_call(counters, groq, monkeypatch):
    monkeypatch.setattr(settings, "user_tokens_per_day", 1000)
    user = uuid.uuid4()
    await limits.add("groq.tokens_per_day", 1000, subject=str(user))
    with llm.caller(user), pytest.raises(limits.LimitExceeded, match="Your groq limit"):
        await llm.complete("rewrite_query", MESSAGES)
    assert groq == []


async def test_a_person_over_the_request_budget_is_stopped(counters, groq, monkeypatch):
    monkeypatch.setattr(settings, "user_requests_per_day", 2)
    user = uuid.uuid4()
    with llm.caller(user):
        await llm.complete("rewrite_query", MESSAGES)
        await llm.complete("rewrite_query", MESSAGES)
        with pytest.raises(limits.LimitExceeded):
            await llm.complete("rewrite_query", MESSAGES)
    assert len(groq) == 2


async def test_evaluation_accounts_are_exempt_but_still_counted(counters, groq, monkeypatch):
    monkeypatch.setattr(settings, "user_tokens_per_day", 100)
    user = uuid.uuid4()
    await limits.add("groq.tokens_per_day", 100, subject=str(user))
    with llm.caller(user, exempt=True):
        await llm.complete("rewrite_query", MESSAGES)
    assert await spent("groq.tokens_per_day", str(user)) == 600


async def test_the_limit_check_model_is_not_counted_against_the_answer_model(counters, groq):
    await llm.complete("check_limit", MESSAGES, model=settings.limits_check_model)
    assert await spent("groq.tokens_per_day") == 0


async def test_new_questions_stop_while_the_shared_reserve_is_needed(counters):
    limit = limits.REGISTRY["groq.tokens_per_day"].limit
    await limits.add("groq.tokens_per_day", limit - 10_000)
    with pytest.raises(limits.LimitExceeded):
        await limits.ensure_headroom("groq.tokens_per_day", 20_000)
    await limits.ensure_headroom("groq.tokens_per_day", 5_000)


def test_one_person_cannot_take_more_than_a_tenth_of_the_free_tier():
    tokens = limits.REGISTRY["groq.tokens_per_day"].limit
    requests = limits.REGISTRY["groq.requests_per_day"].limit
    largest_prompt = settings.rerank_top_k * settings.chunk_size * 1.2 + 1000
    assert settings.user_tokens_per_day + largest_prompt + settings.llm_max_output_tokens <= tokens * 0.1
    assert settings.user_requests_per_day <= requests * 0.1


async def test_uploads_per_day_are_capped(client, make_user, monkeypatch):
    from app.api import routes

    monkeypatch.setattr(settings, "uploads_per_day", 2)
    monkeypatch.setattr(settings, "max_documents", 10)
    monkeypatch.setattr(routes, "_receiving", set())
    user = await make_user()
    upload = {"file": ("notes.txt", b"hello")}
    statuses = []
    for number in range(3):
        headers = {**auth_headers(user.id), "Idempotency-Key": f"u{number}"}
        response = await client.post("/ingest", files=upload, headers=headers)
        statuses.append(response.status_code)
        if response.status_code == 202:
            from sqlalchemy import update

            from app.db.models import IngestJob
            from app.db.session import tenant_session

            async with tenant_session(user.id) as session:
                await session.execute(update(IngestJob).where(IngestJob.id == response.json()["id"]).values(status="done"))
                await session.commit()
    assert statuses == [202, 202, 429]


async def test_a_spent_embedding_budget_stops_paid_embeddings_before_the_call(counters, monkeypatch):
    from app import embeddings

    called = []

    async def encode(texts):
        called.append(texts)
        return [[0.0]], 1

    monkeypatch.setattr(settings, "embedding_provider", "api")
    monkeypatch.setattr(settings, "deepinfra_monthly_budget_usd", 1.0)
    monkeypatch.setattr(embeddings, "_encode_api", encode)
    await limits.add("deepinfra.spend_per_month", 1.0)
    with pytest.raises(limits.LimitExceeded):
        await embeddings.embed(["question"])
    assert called == []
