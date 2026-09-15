import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import TypedDict
from uuid import UUID

from langfuse import get_client, propagate_attributes
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

from app import llm
from app.config import settings
from app.embeddings import embed
from app.graph import prompts, store
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
    tokens_used: int
    tokens_saved: int


def _source(chunk: RetrievedChunk) -> dict:
    return {**chunk.source(), "content": chunk.content, "score": round(chunk.score, 4)}


async def check_cache(state: QueryState, writer: StreamWriter) -> QueryState:
    [embedding] = await embed([state["question"]], name="embed_question")
    cached = await store.find_cached(state["user_id"], embedding) if state.get("use_cache", True) else None
    langfuse = get_client()
    with langfuse.start_as_current_observation(name="check_cache", input={"question": state["question"]}) as span:
        span.update(
            output={"cache_hit": cached is not None},
            metadata={
                "cache_hit": cached is not None,
                "tokens_saved": cached.tokens_used if cached else 0,
                "similarity": round(cached.similarity, 4) if cached else None,
                "threshold": settings.cache_similarity_threshold,
            },
        )
    if cached is None:
        return {"question_embedding": embedding, "cache_hit": False, "attempt": 0, "tokens_used": 0, "chunks": []}
    langfuse.score_current_trace(name="cache_hit", value=1, data_type="BOOLEAN")
    writer({"type": "token", "text": cached.answer})
    return {
        "cache_hit": True,
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
    )
    writer(
        {
            "type": "done",
            "sources": state["sources"],
            "cache_hit": state["cache_hit"],
            "tokens_used": state["tokens_used"],
            "tokens_saved": state["tokens_saved"],
        }
    )
    return {}


def build_graph():
    builder = StateGraph(QueryState)
    builder.add_node("check_cache", check_cache)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("retrieve", retrieve)
    builder.add_node("rerank", rerank_chunks)
    builder.add_node("check_sufficiency", check_sufficiency)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("record", record)
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
