from datetime import UTC, datetime, timedelta

from app.db.models import QueryMetric
from app.graph import store
from tests.conftest import auth_headers


def metric(jev: bool, cache_hit: bool, tokens: int, nodes: list[dict], minutes_ago: int = 0) -> QueryMetric:
    return QueryMetric(
        jev=jev,
        cache_hit=cache_hit,
        tokens_used=tokens,
        tokens_saved=0,
        node_metrics=nodes,
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


BASELINE = [
    {"node": "check_cache", "duration_ms": 100},
    {"node": "rewrite_query", "duration_ms": 600},
    {"node": "check_sufficiency", "duration_ms": 900},
    {"node": "generate_answer", "duration_ms": 1000},
]
WITH_JEV = [
    {"node": "check_cache", "duration_ms": 100},
    {"node": "jev_sufficiency", "duration_ms": 300, "jev": {"latency_ms": 280, "passed": True}},
    {"node": "generate_answer", "duration_ms": 800},
    {"node": "check_grounding", "duration_ms": 250, "jev": {"latency_ms": 240, "verdict": "supported"}},
]


def test_averages_skip_cache_hits_for_time_and_the_last_question_comes_first():
    rows = [
        metric(True, False, 3000, WITH_JEV),
        metric(True, True, 0, [{"node": "check_cache", "duration_ms": 90}], minutes_ago=1),
    ]
    summary = store.summarize_live(rows, 0.0002)
    assert summary["questions"] == 2
    assert summary["average"]["answer_ms"] == 1200
    assert summary["average"]["llm_calls"] == 0.5 and summary["average"]["cache_hit"] == 0.5
    assert summary["average"]["jev_ms"] == 520 and summary["average"]["supported"] == 1.0
    assert summary["average"]["node_ms"]["generate_answer"] == 800 and summary["average"]["node_ms"]["check_cache"] == 100
    assert summary["last"]["llm_calls"] == 1 and summary["last"]["grounding"] == "supported"
    assert store.summarize_live([], None) == {"questions": 0, "average": None, "last": None}


def test_baseline_counts_every_llm_call():
    facts = store.question_facts(metric(False, False, 8000, BASELINE))
    assert (facts["answer_ms"], facts["llm_calls"], facts["jev_calls"]) == (2600, 3, 0)


async def test_live_metrics_are_public_and_split_by_mode(client, make_user, monkeypatch):
    monkeypatch.setattr(store, "JEV_FIRST_SINCE", datetime(2000, 1, 1, tzinfo=UTC))
    user = await make_user()
    await store.record_query(
        user_id=user.id, question="secret question", answer="secret answer", sources=[], cache_hit=False,
        tokens_used=8000, tokens_saved=0, cache_embedding=None, node_metrics=BASELINE,
    )
    log_id, _ = await store.record_query(
        user_id=user.id, question="secret question", answer="secret answer", sources=[], cache_hit=False,
        tokens_used=3000, tokens_saved=0, cache_embedding=None, node_metrics=WITH_JEV[:3], with_jev=True,
    )
    await store.append_node_metric(user.id, log_id, WITH_JEV[3])
    response = await client.get("/metrics/live")
    assert response.headers["access-control-allow-origin"] == "*"
    body = response.json()
    assert body["baseline"]["last"]["llm_calls"] == 3
    assert body["jev"]["last"]["grounding"] == "supported"
    assert "secret" not in response.text
    await client.delete("/history", headers=auth_headers(user.id))
    after = (await client.get("/metrics/live")).json()
    assert after["jev"]["questions"] < body["jev"]["questions"]
