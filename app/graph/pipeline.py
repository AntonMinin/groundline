import asyncio
import functools
import json
import logging
import operator
import time
from collections.abc import AsyncIterator
from typing import Annotated, TypedDict
from uuid import UUID

from langfuse import get_client, propagate_attributes
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

from app import events, inference, llm
from app.config import settings
from app.embeddings import embed
from app.graph import prompts, store
from app.ingestion import jobs
from app.ingestion.chunking import count_tokens
from app.retrieval.fusion import RetrievedChunk
from app.retrieval.rerank import rerank
from app.retrieval.search import hybrid_search

log = logging.getLogger(__name__)


class QueryState(TypedDict, total=False):
    user_id: UUID
    question: str
    use_cache: bool
    question_embedding: list[float]
    query: str
    missing: str
    attempt: int
    candidates: list[RetrievedChunk]
    chunks: list[RetrievedChunk]
    sufficient: bool
    answer: str
    sources: list[dict]
    cache_hit: bool
    cache_similarity: float | None
    node_metrics: Annotated[list[dict], operator.add]
    tokens_used: int
    tokens_saved: int


def _source(chunk: RetrievedChunk) -> dict:
    return {**chunk.source(), "content": chunk.content, "score": round(chunk.score, 4)}


async def check_cache(state: QueryState, writer: StreamWriter) -> QueryState:
    [embedding] = await embed([state["question"]], name="embed_question")
    nearest = await store.find_nearest(state["user_id"], embedding) if state.get("use_cache", True) else None
    threshold = settings.cache_similarity_threshold
    similarity = nearest.similarity if nearest else None
    cached = nearest if nearest and nearest.similarity >= threshold else None

    log.info(
        "cache lookup user=%s hit=%s similarity=%s threshold=%.4f ingest_pending=%d inference_waiting=%d "
        "question=%r nearest=%r",
        state["user_id"],
        cached is not None,
        f"{similarity:.4f}" if similarity is not None else "no-entries",
        threshold,
        jobs.pending(),
        inference.waiting(),
        state["question"],
        nearest.question if nearest else None,
    )

    langfuse = get_client()
    with langfuse.start_as_current_observation(name="check_cache", input={"question": state["question"]}) as span:
        span.update(
            output={"cache_hit": cached is not None},
            metadata={
                "cache_hit": cached is not None,
                "tokens_saved": cached.tokens_used if cached else 0,
                "similarity": round(similarity, 4) if similarity is not None else None,
                "nearest_question": nearest.question if nearest else None,
                "threshold": threshold,
            },
        )
    if cached is None:
        return {
            "question_embedding": embedding,
            "cache_hit": False,
            "cache_similarity": similarity,
            "attempt": 0,
            "tokens_used": 0,
            "chunks": [],
        }
    langfuse.score_current_trace(name="cache_hit", value=1, data_type="BOOLEAN")
    writer({"type": "token", "text": cached.answer})
    return {
        "cache_hit": True,
        "cache_similarity": similarity,
        "answer": cached.answer,
        "sources": cached.sources,
        "tokens_used": 0,
        "tokens_saved": cached.tokens_used,
    }


async def rewrite_query(state: QueryState) -> QueryState:
    messages = prompts.rewrite_messages(state["question"], state.get("query"), state.get("missing"))
    rewritten = (await llm.complete("rewrite_query", messages)).strip() or state["question"]
    return {
        "query": rewritten,
        "attempt": state["attempt"] + 1,
        "tokens_used": state["tokens_used"] + llm.messages_tokens(messages) + count_tokens(rewritten),
    }


async def retrieve(state: QueryState) -> QueryState:
    query = state["query"]
    if query == state["question"]:
        embedding = state["question_embedding"]
    else:
        [embedding] = await embed([query], name="embed_query")
    found = await hybrid_search(state["user_id"], query, embedding)
    found_ids = {chunk.id for chunk in found}
    previous = [chunk for chunk in state.get("chunks", []) if chunk.id not in found_ids]
    return {"candidates": found + previous}


async def rerank_chunks(state: QueryState) -> QueryState:
    return {"chunks": await rerank(state["question"], state["candidates"])}


async def check_sufficiency(state: QueryState) -> QueryState:
    if not state["chunks"]:
        return {"sufficient": False, "missing": "no relevant fragments found"}
    messages = prompts.sufficiency_messages(state["question"], state["chunks"])
    raw = await llm.complete("check_sufficiency", messages, response_format={"type": "json_object"})
    tokens_used = state["tokens_used"] + llm.messages_tokens(messages) + count_tokens(raw)
    try:
        verdict = json.loads(raw)
        return {
            "sufficient": bool(verdict.get("sufficient")),
            "missing": str(verdict.get("missing") or ""),
            "tokens_used": tokens_used,
        }
    except (json.JSONDecodeError, AttributeError):
        log.warning("Unparseable sufficiency verdict: %r", raw)
        return {"sufficient": True, "missing": "", "tokens_used": tokens_used}


def route_after_sufficiency(state: QueryState) -> str:
    if state["sufficient"] or state["attempt"] > settings.max_rewrites:
        return "generate_answer"
    return "rewrite_query"


def route_after_cache(state: QueryState) -> str:
    return "record" if state["cache_hit"] else "rewrite_query"


async def generate_answer(state: QueryState, writer: StreamWriter) -> QueryState:
    messages = prompts.answer_messages(state["question"], state["chunks"])
    parts: list[str] = []
    async for token in llm.stream("generate_answer", messages):
        parts.append(token)
        writer({"type": "token", "text": token})
    answer = "".join(parts)
    return {
        "answer": answer,
        "sources": [_source(chunk) for chunk in state["chunks"]],
        "tokens_used": state["tokens_used"] + llm.messages_tokens(messages) + count_tokens(answer),
        "tokens_saved": 0,
    }


async def record(state: QueryState, writer: StreamWriter) -> QueryState:
    cacheable = not state["cache_hit"] and state.get("sufficient", False)
    await store.record_query(
        user_id=state["user_id"],
        question=state["question"],
        answer=state["answer"],
        sources=state["sources"],
        cache_hit=state["cache_hit"],
        tokens_used=state["tokens_used"],
        tokens_saved=state["tokens_saved"],
        cache_embedding=state["question_embedding"] if cacheable else None,
        node_metrics=state.get("node_metrics", []),
    )
    writer(
        {
            "type": "done",
            "sources": state["sources"],
            "cache_hit": state["cache_hit"],
            "cache_similarity": state.get("cache_similarity"),
            "cache_threshold": settings.cache_similarity_threshold,
            "tokens_used": state["tokens_used"],
            "tokens_saved": state["tokens_saved"],
        }
    )
    return {}


def _instrumented(name: str, node):
    @functools.wraps(node)
    async def wrapper(state: QueryState, **kwargs) -> QueryState:
        user_id = state["user_id"]
        events.publish(user_id, {"type": "node_started", "node": name})
        before = state.get("tokens_used", 0)
        started = time.perf_counter()
        result = await node(state, **kwargs)
        cache_hit = result.get("cache_hit", state.get("cache_hit", False))
        metric = {
            "node": name,
            "cache_hit": bool(cache_hit),
            "tokens": max(result.get("tokens_used", before) - before, 0),
            "tokens_saved": result.get("tokens_saved", 0) if name == "check_cache" else 0,
            "similarity": result.get("cache_similarity") if name == "check_cache" else None,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
        events.publish(user_id, {"type": "node_finished", **metric})
        return {**result, "node_metrics": [metric]}

    return wrapper


NODES = (
    ("check_cache", check_cache),
    ("rewrite_query", rewrite_query),
    ("retrieve", retrieve),
    ("rerank", rerank_chunks),
    ("check_sufficiency", check_sufficiency),
    ("generate_answer", generate_answer),
    ("record", record),
)


def build_graph():
    builder = StateGraph(QueryState)
    for name, node in NODES:
        builder.add_node(name, _instrumented(name, node))
    builder.add_edge(START, "check_cache")
    builder.add_conditional_edges("check_cache", route_after_cache, ["record", "rewrite_query"])
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_edge("rerank", "check_sufficiency")
    builder.add_conditional_edges("check_sufficiency", route_after_sufficiency, ["generate_answer", "rewrite_query"])
    builder.add_edge("generate_answer", "record")
    builder.add_edge("record", END)
    return builder.compile()


graph = build_graph()

_END = object()


async def run_query(user_id: UUID, question: str, use_cache: bool = True) -> AsyncIterator[dict]:
    queue: asyncio.Queue = asyncio.Queue()

    async def worker() -> None:
        try:
            with (
                propagate_attributes(user_id=str(user_id), trace_name="query"),
                get_client().start_as_current_observation(
                    name="query", as_type="chain", input={"question": question}
                ) as root,
            ):
                answer = ""
                async for event in graph.astream(
                    {"user_id": user_id, "question": question, "use_cache": use_cache}, stream_mode="custom"
                ):
                    if event["type"] == "token":
                        answer += event["text"]
                    elif event["type"] == "done":
                        root.update(
                            output={"answer": answer},
                            metadata={"cache_hit": event["cache_hit"], "tokens_saved": event["tokens_saved"]},
                        )
                    await queue.put(event)
            await queue.put(_END)
        except Exception as exc:
            await queue.put(exc)

    task = asyncio.create_task(worker())
    try:
        while True:
            item = await queue.get()
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        task.cancel()
