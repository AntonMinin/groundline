import logging
import time

import httpx

from app.config import settings

log = logging.getLogger(__name__)

DEDUP_SECONDS = 24 * 3600
RED_ZONE = 0.2

_sent: dict[tuple[str, str], float] = {}


def enabled() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def _throttled(key: str, kind: str) -> bool:
    last = _sent.get((key, kind))
    if last is not None and time.monotonic() - last < DEDUP_SECONDS:
        return True
    _sent[(key, kind)] = time.monotonic()
    return False


async def send(text: str) -> None:
    if not enabled():
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.warning("Could not deliver a Telegram alert: Telegram answered %s", exc.response.status_code)
    except httpx.HTTPError as exc:
        log.warning("Could not deliver a Telegram alert: %s", type(exc).__name__)


def _amount(value: float, unit: str) -> str:
    return f"${value:,.2f}" if unit == "usd" else f"{value:,.0f} {unit}"


async def limit_outdated(key: str, service: str, title: str, configured: float, found: float, url: str) -> None:
    message = (
        f"Groundline: limit for {service} ({title}) may be outdated\n"
        f"in config: {configured:,.0f}\n"
        f"on the pricing page: {found:,.0f}\n"
        f"{url}\n"
        f"The application keeps using the configured value, change it by hand if the page is right."
    )
    log.warning(
        "Limit for %s looks outdated: config=%s page=%s (%s)", key, configured, found, url
    )
    if not _throttled(key, "outdated"):
        await send(message)


async def quota_consumed(key: str, service: str, title: str, used: float, limit: float, unit: str, resets: str) -> None:
    if limit <= 0:
        return
    remaining = max(limit - used, 0.0)
    share = remaining / limit
    if share <= 0:
        kind, headline = "exhausted", f"Groundline: {service} exhausted ({title})"
    elif share < RED_ZONE:
        kind, headline = "red", f"Groundline: {service} in the red zone ({title})"
    else:
        return
    if _throttled(key, kind):
        return
    await send(
        f"{headline}\n"
        f"used {_amount(used, unit)} of {_amount(limit, unit)}, left {_amount(remaining, unit)} ({share:.0%})\n"
        f"resets {resets}"
    )
