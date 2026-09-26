import json
import logging
import time

import httpx
from langfuse import get_client

from app import guard, limits
from app.config import settings

log = logging.getLogger(__name__)

ENDPOINTS = {
    "openrouter": "https://openrouter.ai/api/v1/systemone",
    "typesafe": "https://api.typesafe.ai/v1/systemone",
}

_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        log.warning(message)


def provider() -> str:
    if settings.jev_provider == "typesafe" and not settings.typesafe_api_key:
        _warn_once("fallback", "JEV_PROVIDER=typesafe but TYPESAFE_API_KEY is empty, using openrouter instead")
        return "openrouter"
    return settings.jev_provider


def _api_key(name: str) -> str:
    return settings.typesafe_api_key if name == "typesafe" else settings.openrouter_api_key


def enabled() -> bool:
    if not settings.jev_enabled:
        return False
    if not _api_key(provider()):
        _warn_once("no-key", "JEV_ENABLED=true but no API key for Jev is set, Jev stays off")
        return False
    return True


def cost_of(payload: dict) -> float:
    usage = payload.get("usage") or {}
    if usage.get("cost") is not None:
        return float(usage["cost"])
    return float(usage.get("input_tokens", 0)) / 1_000_000 * settings.jev_price_per_1m


def _parse(payload: dict, questions: dict) -> dict:
    answers = {}
    for key, question in questions.items():
        answer = payload["answers"][key]
        if question["type"] == "noul":
            answers[key] = {"noul": float(answer["noul"])}
        else:
            answers[key] = {
                question["type"]: answer[question["type"]],
                "probabilities": {option: float(value) for option, value in answer["probabilities"].items()},
                "confidence": float(answer["confidence"]),
            }
    return answers


async def ask(name: str, state, questions: dict, timeout_ms: int) -> dict | None:
    if not enabled():
        return None
    try:
        await limits.ensure("jev.spend_per_month")
    except limits.LimitExceeded as exc:
        _warn_once("budget", f"Jev skipped: {exc}")
        return None
    current = provider()
    started = time.perf_counter()
    with get_client().start_as_current_observation(
        name=name,
        as_type="generation",
        model=settings.jev_model,
        input={"state": guard.redact(json.dumps(state, ensure_ascii=False)), "questions": questions},
        metadata={"provider": current, "timeout_ms": timeout_ms},
    ) as generation:
        try:
            async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
                response = await client.post(
                    ENDPOINTS[current],
                    headers={"Authorization": f"Bearer {_api_key(current)}"},
                    json={"model": settings.jev_model, "state": state, "questions": questions},
                )
                response.raise_for_status()
            payload = response.json()
            answers = _parse(payload, questions)
            cost = cost_of(payload)
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000)
            log.warning("Jev %s via %s failed after %d ms, continuing without it: %r", name, current, latency_ms, exc)
            generation.update(
                level="ERROR",
                status_message=repr(exc)[:500],
                metadata={"provider": current, "latency_ms": latency_ms},
            )
            return None
        latency_ms = round((time.perf_counter() - started) * 1000)
        usage = payload.get("usage") or {}
        generation.update(
            model=payload.get("model") or settings.jev_model,
            output=answers,
            usage_details={"input": int(usage.get("input_tokens", 0)), "output": int(usage.get("output_tokens", 0))},
            cost_details={"total": cost},
            metadata={"provider": current, "latency_ms": latency_ms},
        )
    await limits.add("jev.spend_per_month", cost)
    await limits.add("langfuse.units_per_month")
    return answers
