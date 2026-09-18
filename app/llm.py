from collections.abc import AsyncIterator

import httpx
from langfuse.openai import AsyncOpenAI

from app import limits
from app.config import settings
from app.ingestion.chunking import count_tokens


async def _capture_limits(response: httpx.Response) -> None:
    limits.report_groq_headers(response.headers)


client = AsyncOpenAI(
    api_key=settings.groq_api_key or "missing",
    base_url=settings.llm_base_url,
    timeout=settings.llm_timeout,
    max_retries=1,
    http_client=httpx.AsyncClient(timeout=settings.llm_timeout, event_hooks={"response": [_capture_limits]}),
)


async def _record(prompt_tokens: int, completion: str) -> None:
    await limits.add("groq.requests_per_day")
    await limits.add("groq.tokens_per_day", prompt_tokens + count_tokens(completion))
    await limits.add("langfuse.units_per_month")


def messages_tokens(messages: list[dict]) -> int:
    return sum(count_tokens(message["content"]) for message in messages)


async def complete(name: str, messages: list[dict], **kwargs) -> str:
    response = await client.chat.completions.create(
        name=name, model=settings.llm_model, messages=messages, temperature=0, **kwargs
    )
    text = response.choices[0].message.content or ""
    await _record(messages_tokens(messages), text)
    return text


async def stream(name: str, messages: list[dict]) -> AsyncIterator[str]:
    response = await client.chat.completions.create(
        name=name, model=settings.llm_model, messages=messages, temperature=0.2, stream=True
    )
    parts: list[str] = []
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            parts.append(chunk.choices[0].delta.content)
            yield chunk.choices[0].delta.content
    await _record(messages_tokens(messages), "".join(parts))
