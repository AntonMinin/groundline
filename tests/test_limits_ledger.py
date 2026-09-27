import pytest
from sqlalchemy import delete, select

from app import limits
from app.db.models import ServiceUsage
from app.db.session import SessionLocal

KEY = "groq.requests_per_day"


@pytest.fixture
async def clean(migrated_db):
    async def wipe():
        async with SessionLocal() as session:
            await session.execute(delete(ServiceUsage).where(ServiceUsage.quota_key.like(f"{KEY}%")))
            await session.commit()

    await wipe()
    yield
    await wipe()


async def stored(name: str) -> float | None:
    async with SessionLocal() as session:
        return await session.scalar(select(ServiceUsage.used).where(ServiceUsage.quota_key == name))


async def test_a_question_writes_its_usage_once_at_the_end_and_sees_it_meanwhile(clean, monkeypatch):
    sessions = []
    real = limits.SessionLocal
    monkeypatch.setattr(limits, "SessionLocal", lambda: sessions.append(1) or real())
    await limits.add(KEY, 5)
    sessions.clear()
    async with limits.batched():
        assert (await limits.used((KEY,)))[KEY] == 5
        await limits.add(KEY, 2)
        await limits.add(KEY, 1, subject="someone")
        assert (await limits.used((KEY,)))[KEY] == 7
        assert (await limits.used((KEY,), subject="someone"))[KEY] == 1
        assert await stored(KEY) == 5
    assert len(sessions) == 3
    assert (await stored(KEY), await stored(f"{KEY}|someone")) == (7, 1)


async def test_usage_is_written_even_when_the_question_fails(clean):
    with pytest.raises(RuntimeError):
        async with limits.batched():
            await limits.add(KEY, 3)
            raise RuntimeError("model down")
    assert await stored(KEY) == 3
