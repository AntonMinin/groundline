from collections.abc import AsyncIterator

from langfuse.openai import AsyncOpenAI

from app.config import settings
from app.ingestion.chunking import count_tokens

client = AsyncOpenAI(
    api_key=settings.groq_api_key or "missing",
    base_url=settings.llm_base_url,
    timeout=settings.llm_timeout,
    max_retries=1,
)


def messages_tokens(messages: list[dict]) -> int:
    return sum(count_tokens(message["content"]) for message in messages)


async def complete(name: str, messages: list[dict], **kwargs) -> str:
    response = await client.chat.completions.create(
        name=name, model=settings.llm_model, messages=messages, temperature=0, **kwargs
    )
    return response.choices[0].message.content or ""


async def stream(name: str, messages: list[dict]) -> AsyncIterator[str]:
    response = await client.chat.completions.create(
        name=name, model=settings.llm_model, messages=messages, temperature=0.2, stream=True
    )
    async for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
