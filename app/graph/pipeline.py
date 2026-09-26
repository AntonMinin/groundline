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

from app import events, guard, inference, jev, limits, llm
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
    jev: dict
    log_id: UUID | None
    documents_version: int


def _source(chunk: RetrievedChunk) -> dict:
    return {**chunk.source(), "content": chunk.content, "score": round(chunk.score, 4)}


async def check_cache(state: QueryState, writer: StreamWriter) -> QueryState:
    [embedding] = await embed([state["question"]], name="embed_question")
    nearest = await store.find_nearest(state["user_id"], embedding) if state.get("use_cache", True) else None
    threshold = settings.cache_similarity_threshold
    similarity = nearest.similarity if nearest else None
    cached = nearest if nearest and nearest.similarity >= threshold else None
    same_question, trace = None, {}
    if nearest and settings.jev_cache_verify_from <= nearest.similarity < settings.jev_cache_verify_below:
        answers, trace = await _ask_jev(
            "jev_same_question",
            {"new_question": state["question"], "stored_question": nearest.question},
            {"same_question": prompts.JEV_SAME_QUESTION},
            settings.jev_timeout_critical_ms,
        )
        if answers is not None:
            same_question = answers["same_question"]["noul"]
            trace["same_question"] = round(same_question, 4)
            cached = nearest if same_question >= settings.jev_same_question_threshold else None

    log.info(
        "cache lookup user=%s hit=%s similarity=%s threshold=%.4f ingest_pending=%d inference_waiting=%d",
        state["user_id"],
        cached is not None,
        f"{similarity:.4f}" if similarity is not None else "no-entries",
        threshold,
        jobs.pending(),
        inference.waiting(),
    )
    log.debug(
        "cache lookup user=%s question=%r nearest=%r",
        state["user_id"],
        guard.redact(state["question"]),
        guard.redact(nearest.question) if nearest else None,
    )

    langfuse = get_client()
    with langfuse.start_as_current_observation(
        name="check_cache", input={"question": guard.redact(state["question"])}
    ) as span:
        span.update(
            output={"cache_hit": cached is not None},
            metadata={
                "cache_hit": cached is not None,
                "tokens_saved": cached.tokens_used if cached else 0,
                "similarity": round(similarity, 4) if similarity is not None else None,
                "nearest_question": guard.redact(nearest.question) if nearest else None,
                "threshold": threshold,
                "jev_same_question": same_question,
            },
        )
    verified = {"jev": trace} if trace else {}
    if cached is None:
        return {
            "question_embedding": embedding,
            "cache_hit": False,
            "cache_similarity": similarity,
            "attempt": 0,
            "tokens_used": 0,
            "chunks": [],
            **verified,
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
        **verified,
    }


def _llm_tokens(before: int, estimate: int) -> int:
    measured = llm.spent() - before
    return measured if measured > 0 else estimate


async def rewrite_query(state: QueryState) -> QueryState:
    await limits.ensure(*limits.QUERY_KEYS)
    if state["attempt"] == 0:
        await limits.ensure_headroom("groq.tokens_per_day", settings.groq_reserve_tokens)
        await limits.ensure_headroom("groq.requests_per_day", settings.groq_reserve_requests)
        await llm.ensure_room_for_question()
    messages = prompts.rewrite_messages(state["question"], state.get("query"), state.get("missing"))
    before = llm.spent()
    rewritten = guard.clamp(await llm.complete("rewrite_query", messages)) or state["question"]
    return {
        "query": rewritten,
        "attempt": state["attempt"] + 1,
        "tokens_used": state["tokens_used"]
        + _llm_tokens(before, llm.messages_tokens(messages) + count_tokens(rewritten)),
    }


async def retrieve(state: QueryState) -> QueryState:
    query = state["query"]
    if query == state["question"]:
        embedding = state["question_embedding"]
    else:
        [embedding] = await embed([query], name="embed_query")
    version = state.get("documents_version")
    if version is None:
        version = await store.documents_version(state["user_id"])
    found = await hybrid_search(state["user_id"], query, embedding)
    found_ids = {chunk.id for chunk in found}
    previous = [chunk for chunk in state.get("chunks", []) if chunk.id not in found_ids]
    return {"candidates": found + previous, "documents_version": version}


async def rerank_chunks(state: QueryState) -> QueryState:
    return {"chunks": await rerank(state["question"], state["candidates"])}


async def _ask_jev(name: str, jev_state, questions: dict, timeout_ms: int) -> tuple[dict | None, dict]:
    if not jev.enabled():
        return None, {}
    started = time.perf_counter()
    answers = await jev.ask(name, jev_state, questions, timeout_ms)
    trace = {"latency_ms": round((time.perf_counter() - started) * 1000)}
    return answers, trace if answers is not None else {**trace, "failed": True}


async def jev_sufficiency(state: QueryState) -> QueryState:
    if not state["chunks"]:
        return {"sufficient": False}
    answers, trace = await _ask_jev(
        "jev_sufficiency",
        {"question": state["question"], "fragments": prompts.jev_fragments(state["chunks"])},
        {"sufficient": prompts.JEV_SUFFICIENT},
        settings.jev_timeout_critical_ms,
    )
    if answers is None:
        return {"sufficient": False, **({"jev": trace} if trace else {})}
    probability = answers["sufficient"]["noul"]
    passed = probability >= settings.jev_sufficient_threshold
    return {"sufficient": passed, "jev": {**trace, "sufficient": round(probability, 4), "passed": passed}}


def route_after_jev_sufficiency(state: QueryState) -> str:
    return "generate_answer" if state["sufficient"] else "check_sufficiency"


async def check_sufficiency(state: QueryState) -> QueryState:
    if not state["chunks"]:
        return {"sufficient": False, "missing": "no relevant fragments found"}
    messages = prompts.sufficiency_messages(state["question"], state["chunks"])
    before = llm.spent()
    raw = await llm.complete("check_sufficiency", messages, response_format={"type": "json_object"})
    tokens_used = state["tokens_used"] + _llm_tokens(before, llm.messages_tokens(messages) + count_tokens(raw))
    try:
        verdict = json.loads(raw)
        return {
            "sufficient": bool(verdict.get("sufficient")),
            "missing": guard.clamp(str(verdict.get("missing") or ""), guard.MAX_MISSING_CHARS),
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
    before = llm.spent()
    async for token in llm.stream("generate_answer", messages):
        parts.append(token)
        writer({"type": "token", "text": token})
    answer = "".join(parts)
    return {
        "answer": answer,
        "sources": [_source(chunk) for chunk in state["chunks"]],
        "tokens_used": state["tokens_used"] + _llm_tokens(before, llm.messages_tokens(messages) + count_tokens(answer)),
        "tokens_saved": 0,
    }


def _cache_write_skipped(state: QueryState) -> None:
    log.info(
        "cache write skipped user=%s: documents changed since retrieval (version %s)",
        state["user_id"],
        state.get("documents_version"),
    )
    get_client().create_event(
        name="cache_write_skipped",
        metadata={"reason": "documents changed since retrieval", "documents_version": state.get("documents_version")},
    )


def _cacheable(state: QueryState) -> bool:
    return not state["cache_hit"] and state.get("sufficient", False)


async def record(state: QueryState, writer: StreamWriter, defer_cache: bool = False) -> QueryState:
    cacheable = _cacheable(state) and not defer_cache
    log_id, cached = await asyncio.shield(
        store.record_query(
            user_id=state["user_id"],
            question=state["question"],
            answer=state["answer"],
            sources=state["sources"],
            cache_hit=state["cache_hit"],
            tokens_used=state["tokens_used"],
            tokens_saved=state["tokens_saved"],
            cache_embedding=state["question_embedding"] if cacheable else None,
            node_metrics=state.get("node_metrics", []),
            documents_version=state.get("documents_version", 0),
        )
    )
    if cacheable and not cached:
        _cache_write_skipped(state)
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
    return {"log_id": log_id}


def route_after_record(state: QueryState) -> str:
    return END if state["cache_hit"] else "check_grounding"


async def check_grounding(state: QueryState, writer: StreamWriter) -> QueryState:
    answers, trace = None, {}
    if state["chunks"]:
        answers, trace = await _ask_jev(
            "check_grounding",
            {
                "question": state["question"],
                "fragments": prompts.jev_fragments(state["chunks"]),
                "answer": state["answer"],
            },
            {"grounding": prompts.JEV_GROUNDING},
            settings.jev_timeout_ms,
        )
    verdict = answers["grounding"] if answers else None
    supported = verdict["probabilities"].get("supported", 0.0) if verdict else None
    if _cacheable(state) and (supported is None or supported >= settings.jev_grounded_threshold):
        cached = await asyncio.shield(
            store.cache_answer(
                user_id=state["user_id"],
                question=state["question"],
                embedding=state["question_embedding"],
                answer=state["answer"],
                sources=state["sources"],
                tokens_used=state["tokens_used"],
                documents_version=state.get("documents_version", 0),
            )
        )
        if not cached:
            _cache_write_skipped(state)
    if verdict is None:
        return {"jev": trace} if trace else {}
    grounding = {
        "verdict": verdict["choice"],
        "supported": round(supported, 4),
        "confidence": round(verdict["confidence"], 4),
    }
    get_client().score_current_trace(name="jev_supported", value=supported, data_type="NUMERIC")
    writer({"type": "grounding", **grounding})
    return {"jev": {**trace, **grounding}}


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
        if "jev" in result:
            metric["jev"] = result["jev"]
        if state.get("log_id"):
            await asyncio.shield(store.append_node_metric(user_id, state["log_id"], metric))
        events.publish(user_id, {"type": "node_finished", **metric})
        return {**result, "node_metrics": [metric]}

    return wrapper


NODES = (
    ("check_cache", check_cache),
    ("rewrite_query", rewrite_query),
    ("retrieve", retrieve),
    ("rerank", rerank_chunks),
    ("jev_sufficiency", jev_sufficiency),
    ("check_sufficiency", check_sufficiency),
    ("generate_answer", generate_answer),
    ("record", record),
    ("check_grounding", check_grounding),
)
JEV_NODES = ("jev_sufficiency", "check_grounding")


def node_names(with_jev: bool) -> list[str]:
    return [name for name, _ in NODES if with_jev or name not in JEV_NODES]


def build_graph(with_jev: bool | None = None):
    with_jev = jev.enabled() if with_jev is None else with_jev
    builder = StateGraph(QueryState)
    for name, node in NODES:
        if name in JEV_NODES and not with_jev:
            continue
        if name == "record" and with_jev:
            node = functools.partial(record, defer_cache=True)
        builder.add_node(name, _instrumented(name, node))
    builder.add_edge(START, "check_cache")
    builder.add_conditional_edges("check_cache", route_after_cache, ["record", "rewrite_query"])
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("retrieve", "rerank")
    builder.add_conditional_edges("check_sufficiency", route_after_sufficiency, ["generate_answer", "rewrite_query"])
    builder.add_edge("generate_answer", "record")
    if with_jev:
        builder.add_edge("rerank", "jev_sufficiency")
        builder.add_conditional_edges(
            "jev_sufficiency", route_after_jev_sufficiency, ["generate_answer", "check_sufficiency"]
        )
        builder.add_conditional_edges("record", route_after_record, ["check_grounding", END])
        builder.add_edge("check_grounding", END)
    else:
        builder.add_edge("rerank", "check_sufficiency")
        builder.add_edge("record", END)
    return builder.compile()


graph = build_graph()

_END = object()


async def run_query(
    user_id: UUID, question: str, use_cache: bool = True, exempt: bool = False
) -> AsyncIterator[dict]:
    queue: asyncio.Queue = asyncio.Queue()

    async def worker() -> None:
        try:
            with (
                llm.caller(user_id, exempt),
                propagate_attributes(user_id=str(user_id), trace_name="query"),
                get_client().start_as_current_observation(
                    name="query", as_type="chain", input={"question": guard.redact(question)}
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
                            output={"answer": guard.redact(answer)},
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
        await asyncio.gather(task, return_exceptions=True)
