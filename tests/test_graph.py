import json
import uuid

import pytest

from app.graph import pipeline
from app.graph.store import CachedAnswer
from app.retrieval.fusion import RetrievedChunk

CHUNK = RetrievedChunk(
    id=uuid.uuid4(), document_id=uuid.uuid4(), filename="doc.pdf", chunk_index=3, page=2, content="Paris is the capital."
)


@pytest.fixture
def fakes(monkeypatch):
    calls = {"complete": [], "stream": 0, "recorded": [], "search": 0}
    state = {"verdicts": [True], "cached": None}

    async def embed(texts, name="embed"):
        return [[0.1] * 1024 for _ in texts]

    async def hybrid_search(user_id, query, embedding):
        calls["search"] += 1
        return [CHUNK]

    async def rerank(query, chunks):
        return chunks

    async def complete(name, messages, **kwargs):
        calls["complete"].append(name)
        if name == "check_sufficiency":
            verdict = state["verdicts"].pop(0) if state["verdicts"] else False
            return json.dumps({"sufficient": verdict, "missing": "" if verdict else "details"})
        return "capital of France"

    async def stream(name, messages):
        calls["stream"] += 1
        for token in ["Paris ", "[1]"]:
            yield token

    async def find_nearest(user_id, embedding):
        return state["cached"]

    async def record_query(**kwargs):
        calls["recorded"].append(kwargs)

    monkeypatch.setattr(pipeline, "embed", embed)
    monkeypatch.setattr(pipeline, "hybrid_search", hybrid_search)
    monkeypatch.setattr(pipeline, "rerank", rerank)
    monkeypatch.setattr(pipeline.llm, "complete", complete)
    monkeypatch.setattr(pipeline.llm, "stream", stream)
    monkeypatch.setattr(pipeline.store, "find_nearest", find_nearest)
    monkeypatch.setattr(pipeline.store, "record_query", record_query)
    return calls, state


async def _collect(**kwargs):
    return [event async for event in pipeline.run_query(uuid.uuid4(), "What is the capital of France?", **kwargs)]


async def test_happy_path_streams_tokens_and_caches(fakes):
    calls, _ = fakes
    events = await _collect()
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Paris [1]"
    done = events[-1]
    assert done["type"] == "done" and done["cache_hit"] is False
    assert done["sources"][0]["filename"] == "doc.pdf" and done["sources"][0]["chunk_index"] == 3
    assert calls["complete"] == ["rewrite_query", "check_sufficiency"]
    assert calls["recorded"][0]["cache_embedding"] is not None
    assert calls["recorded"][0]["tokens_used"] > 0

    metrics = calls["recorded"][0]["node_metrics"]
    assert [metric["node"] for metric in metrics] == [
        "check_cache",
        "rewrite_query",
        "retrieve",
        "rerank",
        "check_sufficiency",
        "generate_answer",
    ]
    assert all(metric["duration_ms"] >= 0 for metric in metrics)
    assert next(metric for metric in metrics if metric["node"] == "generate_answer")["tokens"] > 0


async def test_insufficient_context_retries_at_most_twice(fakes):
    calls, state = fakes
    state["verdicts"] = [False, False, False, False]
    events = await _collect()
    assert calls["complete"].count("rewrite_query") == 3
    assert calls["search"] == 3
    assert calls["stream"] == 1
    assert events[-1]["type"] == "done"
    assert calls["recorded"][0]["cache_embedding"] is None


async def test_recovers_after_one_retry(fakes):
    calls, state = fakes
    state["verdicts"] = [False, True]
    await _collect()
    assert calls["complete"].count("rewrite_query") == 2


async def test_cache_hit_skips_llm_entirely(fakes):
    calls, state = fakes
    state["cached"] = CachedAnswer("q", "cached answer", [{"filename": "doc.pdf", "chunk_index": 1}], 1234, 0.99)
    events = await _collect()
    assert calls["complete"] == [] and calls["stream"] == 0 and calls["search"] == 0
    assert events[0] == {"type": "token", "text": "cached answer"}
    assert events[-1]["cache_hit"] is True and events[-1]["tokens_saved"] == 1234
    recorded = calls["recorded"][0]
    assert recorded["cache_hit"] is True and recorded["tokens_saved"] == 1234 and recorded["cache_embedding"] is None


async def test_use_cache_false_bypasses_lookup(fakes):
    calls, state = fakes
    state["cached"] = CachedAnswer("q", "cached answer", [], 10, 0.99)
    events = await _collect(use_cache=False)
    assert events[-1]["cache_hit"] is False
    assert calls["stream"] == 1


async def test_pipeline_publishes_node_events(fakes):
    from app import events

    user_id = uuid.uuid4()
    queue = events.subscribe(user_id)
    try:
        async for _ in pipeline.run_query(user_id, "What is the capital of France?"):
            pass
        published = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        events.unsubscribe(user_id, queue)

    started = [event["node"] for event in published if event["type"] == "node_started"]
    finished = {event["node"]: event for event in published if event["type"] == "node_finished"}
    assert started == ["check_cache", "rewrite_query", "retrieve", "rerank", "check_sufficiency", "generate_answer", "record"]
    assert finished["generate_answer"]["tokens"] > 0
    assert finished["retrieve"]["tokens"] == 0
    assert all("timestamp" in event for event in published)
    assert all(event["duration_ms"] >= 0 for event in finished.values())


async def test_cache_hit_publishes_saved_tokens(fakes):
    from app import events

    calls, state = fakes
    state["cached"] = CachedAnswer("q", "cached", [], 1234, 0.99)
    user_id = uuid.uuid4()
    queue = events.subscribe(user_id)
    try:
        async for _ in pipeline.run_query(user_id, "What is the capital of France?"):
            pass
        published = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        events.unsubscribe(user_id, queue)

    check_cache = next(e for e in published if e["type"] == "node_finished" and e["node"] == "check_cache")
    assert check_cache["cache_hit"] is True and check_cache["tokens_saved"] == 1234
    assert [e["node"] for e in published if e["type"] == "node_started"] == ["check_cache", "record"]


async def test_similarity_below_threshold_is_a_miss_but_is_still_reported(fakes):
    from app import events

    calls, state = fakes
    state["cached"] = CachedAnswer("q", "cached", [], 1234, 0.8123)
    user_id = uuid.uuid4()
    queue = events.subscribe(user_id)
    try:
        collected = [event async for event in pipeline.run_query(user_id, "What is the capital of France?")]
        published = [queue.get_nowait() for _ in range(queue.qsize())]
    finally:
        events.unsubscribe(user_id, queue)

    assert collected[-1]["cache_hit"] is False
    assert collected[-1]["cache_similarity"] == 0.8123
    assert collected[-1]["cache_threshold"] == 0.95
    assert calls["stream"] == 1
    check_cache = next(e for e in published if e["type"] == "node_finished" and e["node"] == "check_cache")
    assert check_cache["similarity"] == 0.8123 and check_cache["cache_hit"] is False


async def test_llm_errors_propagate(fakes, monkeypatch):
    import httpx
    import openai

    async def timeout(name, messages, **kwargs):
        raise openai.APITimeoutError(request=httpx.Request("POST", "http://llm"))

    monkeypatch.setattr(pipeline.llm, "complete", timeout)
    with pytest.raises(openai.APITimeoutError):
        await _collect()
