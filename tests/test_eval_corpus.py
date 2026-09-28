import hashlib
import json

import httpx
import pytest

from app.eval.corpus import fetch_gitlab

PAGE = b"---\ntitle: Time off\ndescription: x\n---\n\n## Taking time off\n\n{{% note %}}Keep it.{{% /note %}}\n"


def manifest(digest: str) -> dict:
    return {
        "api_base": "https://gitlab.test/api/v4",
        "project": "group/handbook",
        "commit": "abc123",
        "files": [{"path": "content/handbook/time-off.md", "name": "time-off.md", "sha256": digest}],
    }


def client(seen: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=PAGE)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_pins_the_commit_and_strips_only_the_front_matter(tmp_path):
    seen = []
    [path] = fetch_gitlab.fetch(client(seen), manifest(hashlib.sha256(PAGE).hexdigest()), tmp_path)
    assert seen == [
        "https://gitlab.test/api/v4/projects/group%2Fhandbook/repository/files/content%2Fhandbook%2Ftime-off.md/raw?ref=abc123"
    ]
    assert path.read_text(encoding="utf-8") == "## Taking time off\n\n{{% note %}}Keep it.{{% /note %}}\n"


def test_fetch_refuses_a_changed_file(tmp_path):
    with pytest.raises(fetch_gitlab.ChecksumMismatch):
        fetch_gitlab.fetch(client([]), manifest("0" * 64), tmp_path)
    assert not (tmp_path / "time-off.md").exists()


def test_the_manifest_lists_eight_pinned_files():
    import json

    data = json.loads(fetch_gitlab.MANIFEST.read_text(encoding="utf-8"))
    assert len(data["commit"]) == 40 and len(data["files"]) == 8
    assert all(len(item["sha256"]) == 64 for item in data["files"])


def test_stages_follow_the_run_through_answers_repeats_and_pairs(tmp_path):
    from app.eval import stage

    run = {"total_questions": 2}
    path = tmp_path / "run.json"
    assert not stage.reached(path, "answered")
    for rows_done, repeats, pairs, complete, expected in (
        (1, 1, [], False, (False, False)),
        (2, 1, [], True, (True, False)),
        (2, 3, [], False, (True, False)),
        (2, 3, [{}], True, (True, True)),
    ):
        run.update(rows=[{"score_runs": [{}] * repeats}] * rows_done, cache_pairs=pairs, complete=complete)
        path.write_text(json.dumps(run), encoding="utf-8")
        assert (stage.reached(path, "answered"), stage.reached(path, "finished")) == expected


def test_the_results_table_fills_the_jev_first_column_once_its_run_exists(tmp_path):
    from app.eval import report

    def run(tokens: int, jev: bool) -> dict:
        latency = {"calls": 2, "p50_ms": 280, "p95_ms": 360} if jev else {"calls": 0, "p50_ms": None, "p95_ms": None}
        every = {"questions": 2, "faithfulness": 0.9, "answer_correctness": 0.75, "context_precision": 0.8,
                 "context_recall": 0.85, "groq_calls": 2, "groq_tokens": tokens}
        return {"rows": [{}, {}], "total_questions": 2, "jev_cost_usd": 0.0004 if jev else None,
                "summary": {"all": every, "jev_latency": {"critical": latency}}}

    document = tmp_path / "evaluation.md"
    document.write_text(f"intro\n{report.START}\nold\n{report.END}\nafter\n", encoding="utf-8")
    (tmp_path / "eval_gitlab_baseline.json").write_text(json.dumps(run(8000, False)), encoding="utf-8")
    assert report.publish(document, tmp_path)
    assert "| LLM tokens per question | 4,000 | pending | pending |" in document.read_text(encoding="utf-8")
    (tmp_path / "eval_gitlab_jev_first2.json").write_text(json.dumps(run(3000, True)), encoding="utf-8")
    assert report.publish(document, tmp_path)
    text = document.read_text(encoding="utf-8")
    assert "| Jev decisions on the answer path, p50 / p95 | - | pending | 280 / 360 ms |" in text
    assert text.startswith("intro\n") and text.endswith("after\n")
    assert not report.publish(document, tmp_path)
