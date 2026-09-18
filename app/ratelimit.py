import logging
from datetime import UTC, date, datetime

import httpx

from app.config import settings

log = logging.getLogger(__name__)

SLOT_TTL_SECONDS = 6 * 3600


def enabled() -> bool:
    return bool(settings.upstash_redis_rest_url and settings.upstash_redis_rest_token)


def commands_key(today: date | None = None) -> str:
    return f"limits:upstash:commands:{(today or datetime.now(UTC).date()):%Y-%m}"


async def _pipeline(commands: list[list[str]]) -> list | None:
    metered = [*commands, ["INCRBY", commands_key(), str(len(commands) + 1)]]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                f"{settings.upstash_redis_rest_url.rstrip('/')}/pipeline",
                headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
                json=metered,
            )
            response.raise_for_status()
            return [item["result"] for item in response.json()][: len(commands)]
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        log.warning("Upstash unavailable, falling back to per-process limits", exc_info=True)
        return None


async def allow(key: str, limit: int, window_seconds: int) -> bool | None:
    if not enabled():
        return None
    results = await _pipeline([["INCR", key], ["EXPIRE", key, str(window_seconds), "NX"]])
    return None if results is None else results[0] <= limit


async def acquire_slot(key: str, limit: int) -> bool | None:
    if not enabled():
        return None
    results = await _pipeline([["INCR", key], ["EXPIRE", key, str(SLOT_TTL_SECONDS), "NX"]])
    if results is None:
        return None
    if results[0] > limit:
        await _pipeline([["DECR", key]])
        return False
    return True


async def commands_used() -> float | None:
    if not enabled():
        return None
    results = await _pipeline([["GET", commands_key()]])
    if not results or results[0] is None:
        return None
    return float(results[0])


async def release_slot(key: str) -> None:
    # ponytail: a stream killed with the process leaks its slot until SLOT_TTL_SECONDS expires;
    # refresh the TTL per heartbeat if that ever matters, at the cost of ~4 Upstash commands/minute/stream.
    if not enabled():
        return
    results = await _pipeline([["DECR", key]])
    if results is not None and results[0] < 0:
        await _pipeline([["SET", key, "0"]])
