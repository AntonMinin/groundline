import asyncio
import json
import logging
import re

import httpx

from app import alerts, limits, llm
from app.config import settings

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 24 * 3600
STARTUP_DELAY_SECONDS = 300
PAGE_CHARS = 8000
TOLERANCE = 0.01

EXTRACT_SYSTEM = (
    "You read a pricing or rate-limit page and extract one number: the free-tier limit asked about. "
    'Respond with JSON only: {"limit": <number or null>, "quote": "<the sentence it came from, max 200 chars>"}. '
    "Use null when the page does not state that limit. Return the number without separators or units."
)

_task: asyncio.Task | None = None
_tags = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.DOTALL | re.IGNORECASE)
_spaces = re.compile(r"\s+")


def page_text(html: str) -> str:
    return _spaces.sub(" ", _tags.sub(" ", html)).strip()[:PAGE_CHARS]


async def fetch_page(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "groundline-limit-check"})
            response.raise_for_status()
            return page_text(response.text)
    except httpx.HTTPError:
        log.warning("Could not fetch the pricing page %s", url, exc_info=True)
        return None


def parse_extraction(raw: str) -> tuple[float | None, str]:
    try:
        payload = json.loads(raw)
        value = payload.get("limit")
        return (None if value is None else float(value)), str(payload.get("quote") or "")[:200]
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        log.warning("Unparsable limit extraction: %r", raw)
        return None, ""


async def extract_limit(quota: limits.Quota, text: str) -> tuple[float | None, str]:
    question = (
        f"Service: {quota.service}. Limit to find: {quota.title} on the free plan, "
        f"in {quota.unit} per {quota.period}.\n\nPage:\n{text}"
    )
    raw = await llm.complete(
        "check_limit",
        [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": question}],
        model=settings.limits_check_model,
        response_format={"type": "json_object"},
    )
    return parse_extraction(raw)


async def check_quota(quota: limits.Quota) -> float | None:
    configured = limits.limit_of(quota)
    if configured is None:
        return None
    text = await fetch_page(quota.pricing_url)
    if not text:
        return None
    found, quote = await extract_limit(quota, text)
    if found is None:
        log.info("No limit for %s found on %s", quota.key, quota.pricing_url)
        return None
    if abs(found - configured) <= configured * TOLERANCE:
        limits.mark_outdated(quota.key, None)
        return found
    limits.mark_outdated(quota.key, found, quote)
    await alerts.limit_outdated(quota.key, quota.service, quota.title, configured, found, quota.pricing_url)
    return found


async def check_all(spacing: float | None = None) -> dict[str, float | None]:
    gap = settings.limits_check_spacing_seconds if spacing is None else spacing
    results: dict[str, float | None] = {}
    for quota in limits.QUOTAS:
        if limits.limit_of(quota) is None or not quota.checkable:
            continue
        if results and gap > 0:
            await asyncio.sleep(gap)
        try:
            results[quota.key] = await check_quota(quota)
        except Exception:
            log.warning("Limit check failed for %s", quota.key, exc_info=True)
            results[quota.key] = None
    return results


async def _loop() -> None:
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    while True:
        if await limits.claim_daily_run("limits_check"):
            log.info("Checking provider limit pages with %s", settings.limits_check_model)
            await check_all()
        else:
            log.info("Limit autocheck already ran today, skipping this start")
        await asyncio.sleep(INTERVAL_SECONDS)


async def start() -> None:
    global _task
    if _task is not None:
        return
    if not settings.limits_autocheck_enabled or not settings.groq_api_key:
        log.info("Limit autocheck disabled")
        return
    _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    await asyncio.gather(_task, return_exceptions=True)
    _task = None
