import pytest

from app import ratelimit
from app.config import settings


@pytest.fixture
def upstash(monkeypatch):
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "https://redis.example.com")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "token")
    counters: dict[str, int] = {}

    async def fake_pipeline(commands):
        results = []
        for command, key, *rest in commands:
            if command == "INCR":
                counters[key] = counters.get(key, 0) + 1
            elif command == "DECR":
                counters[key] = counters.get(key, 0) - 1
            elif command == "SET":
                counters[key] = int(rest[0])
            results.append(counters.get(key, 0))
        return results

    monkeypatch.setattr(ratelimit, "_pipeline", fake_pipeline)
    return counters


async def test_disabled_without_configuration(monkeypatch):
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "")
    assert await ratelimit.allow("otp:ip:1.2.3.4", 1, 3600) is None


async def test_allow_counts_until_the_limit(upstash):
    assert await ratelimit.allow("otp:ip:1.2.3.4", 2, 3600) is True
    assert await ratelimit.allow("otp:ip:1.2.3.4", 2, 3600) is True
    assert await ratelimit.allow("otp:ip:1.2.3.4", 2, 3600) is False
    assert await ratelimit.allow("otp:ip:5.6.7.8", 2, 3600) is True


async def test_upstash_failure_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "https://redis.example.com")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "token")

    async def broken(commands):
        return None

    monkeypatch.setattr(ratelimit, "_pipeline", broken)
    assert await ratelimit.allow("otp:ip:1.2.3.4", 1, 3600) is None
