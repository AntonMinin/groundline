import asyncio
import json
import uuid

import pytest

from app.config import settings
from app.graph import pipeline
from app.graph.store import CachedAnswer
from app.retrieval.fusion import RetrievedChunk

CHUNK = RetrievedChunk(
    id=uuid.uuid4(), document_id=uuid.uuid4(), filename="doc.pdf", chunk_index=3, page=2, content="Paris is the capital."
)


@pytest.fixture
def fakes(monkeypatch):
    calls = {"complete": [], "stream": 0, "recorded": [], "search": 0}
    state = {"verdicts": [True], "cached": None, "documents_version": 7}

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
        return None, kwargs["cache_embedding"] is not None

    async def documents_version(user_id):
        return state["documents_version"]

    monkeypatch.setattr(pipeline, "embed", embed)
    monkeypatch.setattr(pipeline, "hybrid_search", hybrid_search)
    monkeypatch.setattr(pipeline, "rerank", rerank)
    monkeypatch.setattr(pipeline.llm, "complete", complete)
    monkeypatch.setattr(pipeline.llm, "stream", stream)
    monkeypatch.setattr(pipeline.store, "find_nearest", find_nearest)
    monkeypatch.setattr(pipeline.store, "record_query", record_query)
    monkeypatch.setattr(pipeline.store, "documents_version", documents_version)

    async def within_limits(*args, **kwargs):
        return None

    monkeypatch.setattr(pipeline.limits, "ensure", within_limits)
    monkeypatch.setattr(pipeline.limits, "ensure_headroom", within_limits)
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
    assert collected[-1]["cache_threshold"] == settings.cache_similarity_threshold
    assert calls["stream"] == 1
    check_cache = next(e for e in published if e["type"] == "node_finished" and e["node"] == "check_cache")
    assert check_cache["similarity"] == 0.8123 and check_cache["cache_hit"] is False


async def test_a_reader_leaving_during_the_write_does_not_interrupt_it(fakes):
    calls, _ = fakes
    started, finished = asyncio.Event(), asyncio.Event()

    async def slow_record(**kwargs):
        started.set()
        await asyncio.sleep(0.1)
        calls["recorded"].append(kwargs)
        finished.set()
        return None, False

    pipeline.store.record_query = slow_record
    stream = pipeline.run_query(uuid.uuid4(), "What is the capital of France?")

    async def drain():
        async for _ in stream:
            pass

    consumer = asyncio.create_task(drain())
    await asyncio.wait_for(started.wait(), timeout=2)
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)

    await asyncio.wait_for(finished.wait(), timeout=2)
    assert len(calls["recorded"]) == 1


async def test_llm_errors_propagate(fakes, monkeypatch):
    import httpx
    import openai

    async def timeout(name, messages, **kwargs):
        raise openai.APITimeoutError(request=httpx.Request("POST", "http://llm"))

    monkeypatch.setattr(pipeline.llm, "complete", timeout)
    with pytest.raises(openai.APITimeoutError):
        await _collect()


ORIGINAL_NODES = ["check_cache", "rewrite_query", "retrieve", "rerank", "check_sufficiency", "generate_answer", "record"]


def test_jev_disabled_keeps_the_original_graph(monkeypatch):
    monkeypatch.setattr(settings, "jev_enabled", False)
    assert [name for name in pipeline.build_graph().nodes if name != "__start__"] == ORIGINAL_NODES
    assert pipeline.node_names(False) == ORIGINAL_NODES


@pytest.fixture
def with_jev(fakes, monkeypatch):
    calls, state = fakes
    calls["jev"], calls["cached"], calls["appended"] = [], [], []
    log_id = uuid.uuid4()
    state["jev"] = {
        "jev_sufficiency": {"sufficient": {"noul": 0.95}},
        "check_grounding": {
            "grounding": {
                "choice": "supported",
                "probabilities": {"supported": 0.9, "unsupported": 0.1},
                "confidence": 0.8,
            }
        },
        "jev_same_question": {"same_question": {"noul": 0.9}},
    }

    async def ask(name, jev_state, questions, timeout_ms):
        calls["jev"].append((name, timeout_ms))
        return state["jev"].get(name)

    async def record_query(**kwargs):
        calls["recorded"].append(kwargs)
        return log_id, kwargs["cache_embedding"] is not None

    async def append_node_metric(user_id, appended_to, metric):
        assert appended_to == log_id
        calls["appended"].append(metric)

    async def cache_answer(**kwargs):
        calls["cached"].append(kwargs)
        return state.get("cache_accepts", True)

    async def ensure(*keys):
        return None

    monkeypatch.setattr(pipeline.jev, "ask", ask)
    monkeypatch.setattr(pipeline.jev, "enabled", lambda: True)
    monkeypatch.setattr(pipeline.store, "record_query", record_query)
    monkeypatch.setattr(pipeline.store, "append_node_metric", append_node_metric)
    monkeypatch.setattr(pipeline.store, "cache_answer", cache_answer)
    monkeypatch.setattr(pipeline.limits, "ensure", ensure)
    monkeypatch.setattr(pipeline, "graph", pipeline.build_graph(with_jev=True))
    return calls, state


async def test_jev_sufficient_skips_the_llm_check_and_grounding_follows_done(with_jev):
    calls, _ = with_jev
    events = await _collect()
    assert calls["complete"] == ["rewrite_query"]
    assert calls["jev"] == [
        ("jev_sufficiency", settings.jev_timeout_critical_ms),
        ("check_grounding", settings.jev_timeout_ms),
    ]
    assert [event["type"] for event in events[-2:]] == ["done", "grounding"]
    assert events[-1] == {"type": "grounding", "verdict": "supported", "supported": 0.9, "confidence": 0.8}
    assert calls["recorded"][0]["cache_embedding"] is None
    assert len(calls["cached"]) == 1 and calls["cached"][0]["answer"] == "Paris [1]"
    metrics = {metric["node"]: metric for metric in calls["recorded"][0]["node_metrics"]}
    assert metrics["jev_sufficiency"]["jev"]["sufficient"] == 0.95 and metrics["jev_sufficiency"]["jev"]["passed"]
    assert metrics["jev_sufficiency"]["jev"]["latency_ms"] >= 0
    assert metrics["jev_sufficiency"]["tokens"] == 0
    [grounding] = calls["appended"]
    assert grounding["node"] == "check_grounding" and grounding["jev"]["verdict"] == "supported"


async def test_jev_unsure_falls_through_to_the_llm_check(with_jev):
    calls, state = with_jev
    state["jev"]["jev_sufficiency"] = {"sufficient": {"noul": 0.6}}
    state["verdicts"] = [False, True]
    await _collect()
    assert calls["complete"] == ["rewrite_query", "check_sufficiency", "rewrite_query", "check_sufficiency"]


async def test_jev_failing_everywhere_keeps_the_original_behaviour(with_jev):
    calls, state = with_jev
    state["jev"] = {}
    events = await _collect()
    assert calls["complete"] == ["rewrite_query", "check_sufficiency"]
    assert events[-1]["type"] == "done"
    assert len(calls["cached"]) == 1
    assert calls["appended"][0]["jev"]["failed"] is True


async def test_unsupported_answer_is_not_cached(with_jev):
    calls, state = with_jev
    state["jev"]["check_grounding"] = {
        "grounding": {"choice": "unsupported", "probabilities": {"supported": 0.1, "unsupported": 0.9}, "confidence": 0.7}
    }
    events = await _collect()
    assert events[-1]["verdict"] == "unsupported"
    assert calls["cached"] == []


async def test_insufficient_answer_is_graded_but_not_cached(with_jev):
    calls, state = with_jev
    state["jev"]["jev_sufficiency"] = {"sufficient": {"noul": 0.1}}
    state["verdicts"] = [False, False, False]
    events = await _collect()
    assert events[-1]["type"] == "grounding"
    assert calls["cached"] == []


async def test_jev_rejects_a_near_hit_that_asks_something_else(with_jev):
    calls, state = with_jev
    state["cached"] = CachedAnswer("How many sick days?", "cached answer", [], 1234, 0.93)
    state["jev"]["jev_same_question"] = {"same_question": {"noul": 0.1}}
    events = await _collect()
    assert calls["jev"][0] == ("jev_same_question", settings.jev_timeout_critical_ms)
    assert events[-2]["cache_hit"] is False and calls["stream"] == 1
    check_cache = calls["recorded"][0]["node_metrics"][0]
    assert check_cache["jev"]["same_question"] == 0.1


async def test_jev_confirms_a_near_hit(with_jev):
    calls, state = with_jev
    state["cached"] = CachedAnswer("q", "cached answer", [], 1234, 0.93)
    events = await _collect()
    assert events[-1]["cache_hit"] is True and calls["stream"] == 0
    assert [name for name, _ in calls["jev"]] == ["jev_same_question"]
    assert calls["appended"] == []


@pytest.mark.parametrize("similarity, answers", [(0.99, {"same_question": {"noul": 0.0}}), (0.93, None)])
async def test_clear_hits_and_jev_failures_keep_the_hit(with_jev, similarity, answers):
    calls, state = with_jev
    state["cached"] = CachedAnswer("q", "cached answer", [], 1234, similarity)
    state["jev"]["jev_same_question"] = answers
    events = await _collect()
    assert events[-1]["cache_hit"] is True and calls["stream"] == 0


async def test_jev_nodes_reach_the_flowchart(with_jev):
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
    assert started == ["check_cache", "rewrite_query", "retrieve", "rerank", "jev_sufficiency", "generate_answer", "record", "check_grounding"]
    grounding = next(e for e in published if e["type"] == "node_finished" and e["node"] == "check_grounding")
    assert grounding["jev"]["verdict"] == "supported"


@pytest.mark.parametrize(
    "similarity, answers, hit, asked",
    [
        (0.87, {"same_question": {"noul": 0.9}}, True, True),
        (0.87, None, False, True),
        (0.80, {"same_question": {"noul": 0.9}}, False, False),
    ],
)
async def test_jev_can_accept_a_paraphrase_below_the_cache_threshold(with_jev, similarity, answers, hit, asked):
    calls, state = with_jev
    state["cached"] = CachedAnswer("q", "cached answer", [], 1234, similarity)
    state["jev"]["jev_same_question"] = answers
    events = await _collect()
    done = next(event for event in events if event["type"] == "done")
    assert done["cache_hit"] is hit
    assert (calls["jev"][:1] == [("jev_same_question", settings.jev_timeout_critical_ms)]) is asked


async def test_below_threshold_candidates_stay_misses_without_jev(fakes, monkeypatch):
    calls, state = fakes
    monkeypatch.setattr(settings, "jev_enabled", False)
    state["cached"] = CachedAnswer("q", "cached answer", [], 1234, 0.87)
    events = await _collect()
    assert events[-1]["cache_hit"] is False and calls["stream"] == 1


async def test_the_document_version_seen_by_retrieval_guards_the_cache_write(fakes):
    calls, state = fakes
    state["documents_version"] = 41
    await _collect()
    assert calls["recorded"][0]["documents_version"] == 41


async def test_retries_keep_the_version_of_the_first_search(fakes, monkeypatch):
    calls, state = fakes
    state["verdicts"] = [False, True]
    versions = iter([3, 4, 5])

    async def changing(user_id):
        return next(versions)

    monkeypatch.setattr(pipeline.store, "documents_version", changing)
    await _collect()
    assert calls["recorded"][0]["documents_version"] == 3


async def test_a_skipped_cache_write_is_reported(with_jev, monkeypatch):
    calls, state = with_jev
    state["cache_accepts"] = False
    skipped = []
    monkeypatch.setattr(pipeline, "_cache_write_skipped", lambda graph_state: skipped.append(graph_state["documents_version"]))
    await _collect()
    assert calls["cached"][0]["documents_version"] == 7
    assert skipped == [7]
