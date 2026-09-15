import asyncio
from functools import lru_cache

from langfuse import get_client
from openai import AsyncOpenAI

from app.config import settings


@lru_cache
def get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


@lru_cache
def _api_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.embedding_api_key or "missing",
        base_url=settings.embedding_api_base_url,
        timeout=settings.llm_timeout,
        max_retries=2,
    )


def _encode_local(texts: list[str]) -> list[list[float]]:
    vectors = get_model().encode(texts, batch_size=settings.embedding_batch_size, normalize_embeddings=True)
    return vectors.tolist()


async def _encode_api(texts: list[str]) -> tuple[list[list[float]], int]:
    vectors: list[list[float]] = []
    tokens = 0
    for start in range(0, len(texts), settings.embedding_batch_size):
        response = await _api_client().embeddings.create(
            model=settings.embedding_model,
            input=texts[start : start + settings.embedding_batch_size],
            encoding_format="float",
        )
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        tokens += response.usage.prompt_tokens if response.usage else 0
    return vectors, tokens


async def embed(texts: list[str], name: str = "embed") -> list[list[float]]:
    with get_client().start_as_current_observation(
        name=name,
        as_type="embedding",
        model=settings.embedding_model,
        input={"count": len(texts)},
        metadata={"provider": settings.embedding_provider},
    ) as observation:
        if settings.embedding_provider == "api":
            vectors, tokens = await _encode_api(texts)
            observation.update(usage_details={"input": tokens})
        else:
            vectors = await asyncio.get_running_loop().run_in_executor(None, _encode_local, texts)
        observation.update(output={"count": len(vectors), "dim": len(vectors[0]) if vectors else 0})
        return vectors
