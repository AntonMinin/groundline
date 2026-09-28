from collections.abc import AsyncIterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

import httpx
from langfuse.openai import AsyncOpenAI

from app import limits
from app.config import settings
from app.ingestion.chunking import count_tokens

_spent: ContextVar[int] = ContextVar("llm_tokens_spent", default=0)
_caller: ContextVar[tuple[UUID, bool] | None] = ContextVar("llm_caller", default=None)


async def _capture_limits(response: httpx.Response) -> None:
    limits.report_groq_headers(response.headers)


client = AsyncOpenAI(
    api_key=settings.groq_api_key or "missing",
    base_url=settings.llm_base_url,
    timeout=settings.llm_timeout,
    max_retries=1,
    http_client=httpx.AsyncClient(timeout=settings.llm_timeout, event_hooks={"response": [_capture_limits]}),
)


@contextmanager
def caller(user_id: UUID, exempt: bool = False):
    token = _caller.set((user_id, exempt))
    try:
        yield
    finally:
        _caller.reset(token)


def spent() -> int:
    return _spent.get()


def messages_tokens(messages: list[dict]) -> int:
    return sum(count_tokens(message["content"]) for message in messages)


async def _admit(model: str) -> None:
    if model != settings.llm_model:
        return
    await limits.ensure(*limits.GROQ_KEYS)
    current = _caller.get()
    if current is None or current[1]:
        return
    subject = str(current[0])
    await limits.ensure_personal("groq.tokens_per_day", subject, settings.user_tokens_per_day)
    await limits.ensure_personal("groq.requests_per_day", subject, settings.user_requests_per_day)


async def ensure_room_for_question() -> None:
    current = _caller.get()
    budget = settings.user_tokens_per_day
    if current is None or current[1] or budget <= 0:
        return
    await limits.ensure_personal(
        "groq.tokens_per_day", str(current[0]), max(budget - settings.question_token_estimate, 1)
    )


async def _record(model: str, usage, messages: list[dict], completion: str) -> None:
    tokens = usage.total_tokens if usage and usage.total_tokens else messages_tokens(messages) + count_tokens(completion)
    _spent.set(_spent.get() + tokens)
    if model == settings.llm_model:
        current = _caller.get()
        await limits.add("groq.requests_per_day")
        await limits.add("groq.tokens_per_day", tokens)
        if current:
            await limits.add("groq.requests_per_day", subject=str(current[0]))
            await limits.add("groq.tokens_per_day", tokens, subject=str(current[0]))
    await limits.add("langfuse.units_per_month")


async def complete(name: str, messages: list[dict], model: str | None = None, **kwargs) -> str:
    model = model or settings.llm_model
    await _admit(model)
    response = await client.chat.completions.create(
        name=name,
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=settings.llm_max_output_tokens,
        **kwargs,
    )
    text = response.choices[0].message.content or ""
    await _record(model, response.usage, messages, text)
    return text


async def stream(name: str, messages: list[dict]) -> AsyncIterator[str]:
    model = settings.llm_model
    await _admit(model)
    response = await client.chat.completions.create(
        name=name,
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=settings.llm_max_output_tokens,
        stream=True,
        stream_options={"include_usage": True},
    )
    parts: list[str] = []
    usage = None
    async for chunk in response:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
            yield chunk.choices[0].delta.content
    await _record(model, usage, messages, "".join(parts))
