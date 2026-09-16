from functools import lru_cache

from langfuse import get_client
from openai import AsyncOpenAI

from app.config import settings
from app.inference import run_inference


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
    return get_model().encode(texts, batch_size=settings.embedding_batch_size, normalize_embeddings=True).tolist()


async def _encode_local_batched(texts: list[str]) -> tuple[list[list[float]], float]:
    vectors: list[list[float]] = []
    waited_ms = 0.0
    for start in range(0, len(texts), settings.embedding_batch_size):
        batch, waited = await run_inference(_encode_local, texts[start : start + settings.embedding_batch_size])
        vectors.extend(batch)
        waited_ms = max(waited_ms, waited)
    return vectors, waited_ms


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
            vectors, waited_ms = await _encode_local_batched(texts)
            observation.update(metadata={"provider": "local", "lock_wait_ms": round(waited_ms)})
        observation.update(output={"count": len(vectors), "dim": len(vectors[0]) if vectors else 0})
        return vectors
