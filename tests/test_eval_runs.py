import hashlib

import pytest
from sqlalchemy import delete

from app.config import settings
from app.db.models import EvalRun
from app.db.session import SessionLocal

TOKEN = "eval-token-for-tests"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Requested-With": "groundline"}


@pytest.fixture(autouse=True)
async def eval_token(monkeypatch, migrated_db):
    monkeypatch.setattr(settings, "eval_write_token_sha256", hashlib.sha256(TOKEN.encode()).hexdigest())
    yield
    async with SessionLocal() as session:
        await session.execute(delete(EvalRun))
        await session.commit()


def run(done: int) -> dict:
    rows = [
        {
            "question": f"q{number}",
            "kind": "unanswerable" if number % 2 else "single",
            "answer": "secret answer",
            "sources": [{"content": "chunk"}],
            "scores": {"answer_correctness": None if number == 1 else 0.5},
        }
        for number in range(done)
    ]
    return {
        "label": "baseline",
        "jev": False,
        "complete": False,
        "total_questions": 29,
        "summary": {"all": {"faithfulness": 0.9}, "kind": {}, "node_latency": {}, "judge_spread": {}},
        "cache_pairs": [{"correct": True, "cache_hit": True}, {"correct": False, "cache_hit": True}, {"correct": False}],
        "rows": rows,
    }


async def test_progress_round_trips_and_is_overwritten(client):
    assert (await client.put("/eval/runs/eval_gitlab_baseline", json=run(21), headers=HEADERS)).status_code == 204
    assert (await client.put("/eval/runs/eval_gitlab_baseline", json=run(22), headers=HEADERS)).status_code == 204
    stored = await client.get("/eval/runs/eval_gitlab_baseline", headers=HEADERS)
    assert len(stored.json()["rows"]) == 22


async def test_writes_and_full_reads_need_the_token(client):
    wrong = {**HEADERS, "Authorization": "Bearer guess"}
    assert (await client.put("/eval/runs/x", json=run(1), headers=wrong)).status_code == 404
    assert (await client.put("/eval/runs/x", json=run(1), headers={"X-Requested-With": "groundline"})).status_code == 404
    await client.put("/eval/runs/x", json=run(1), headers=HEADERS)
    assert (await client.get("/eval/runs/x", headers=wrong)).status_code == 404


async def test_writes_are_refused_when_no_token_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "eval_write_token_sha256", "")
    assert (await client.put("/eval/runs/x", json=run(1), headers=HEADERS)).status_code == 404


async def test_public_status_shows_progress_without_answers(client):
    await client.put("/eval/runs/eval_gitlab_baseline", json=run(22), headers=HEADERS)
    status = await client.get("/eval/status")
    assert status.headers["access-control-allow-origin"] == "*"
    [entry] = status.json()["runs"]
    assert (entry["done"], entry["total"], entry["unanswerable_scored"]) == (22, 29, 10)
    assert entry["cache_pairs"] == {"total": 3, "correct": 1, "wrong_hits": 1}
    assert "secret answer" not in status.text and "judge_spread" not in entry["summary"]


async def test_oversized_or_malformed_runs_are_refused(client):
    huge = b'{"rows": "' + b"x" * (5 * 1024 * 1024) + b'"}'
    assert (await client.put("/eval/runs/x", content=huge, headers=HEADERS)).status_code == 413
    assert (await client.put("/eval/runs/x", content=b"[1]", headers=HEADERS)).status_code == 422
