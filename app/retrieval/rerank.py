from dataclasses import replace
from functools import lru_cache

import httpx
from langfuse import get_client

from app import guard, limits
from app.config import settings
from app.inference import run_inference
from app.retrieval.fusion import RetrievedChunk

PINECONE_API_VERSION = "2025-04"


@lru_cache
def get_reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.reranker_model, max_length=1024)


def _score_local(query: str, chunks: list[RetrievedChunk]) -> list[float]:
    return get_reranker().predict([(query, chunk.content) for chunk in chunks]).tolist()


def parse_rerank_response(payload: dict, count: int) -> list[float]:
    scores = [0.0] * count
    for item in payload["data"]:
        scores[item["index"]] = float(item["score"])
    return scores


def rerank_units(payload: dict) -> float:
    usage = payload.get("usage") or {}
    return float(usage.get("rerank_units", 1))


async def _score_api(query: str, chunks: list[RetrievedChunk]) -> list[float]:
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        response = await client.post(
            settings.rerank_api_url,
            headers={"Api-Key": settings.rerank_api_key, "X-Pinecone-API-Version": PINECONE_API_VERSION},
            json={
                "model": settings.rerank_api_model,
                "query": query,
                "documents": [{"text": chunk.content} for chunk in chunks],
                "top_n": len(chunks),
                "return_documents": False,
                "parameters": {"truncate": "END"},
            },
        )
        response.raise_for_status()
    payload = response.json()
    await limits.add("pinecone.rerank_units_per_month", rerank_units(payload))
    await limits.add("langfuse.units_per_month")
    return parse_rerank_response(payload, len(chunks))


async def rerank(query: str, chunks: list[RetrievedChunk], top_k: int = settings.rerank_top_k) -> list[RetrievedChunk]:
    if not chunks:
        return []
    with get_client().start_as_current_observation(
        name="rerank",
        as_type="retriever",
        input={"query": guard.redact(query), "candidates": len(chunks)},
        metadata={"provider": settings.rerank_provider},
    ) as observation:
        if settings.rerank_provider == "api":
            scores = await _score_api(query, chunks)
        else:
            scores, waited_ms = await run_inference(_score_local, query, chunks)
            observation.update(metadata={"provider": "local", "lock_wait_ms": round(waited_ms)})
        ranked = sorted(
            (replace(chunk, score=score) for chunk, score in zip(chunks, scores)), key=lambda c: c.score, reverse=True
        )[:top_k]
        observation.update(output=[{**chunk.source(), "score": round(chunk.score, 4)} for chunk in ranked])
        return ranked
