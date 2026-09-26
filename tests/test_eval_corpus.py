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
