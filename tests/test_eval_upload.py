import json

import httpx
import pytest

from app.eval import run_eval

JOB_ID = "11111111-1111-1111-1111-111111111111"
DOCUMENT_ID = "22222222-2222-2222-2222-222222222222"


def job(status: str, error: str | None = None, document_id: str | None = None) -> dict:
    return {"id": JOB_ID, "filename": "handbook.md", "status": status, "error": error, "document_id": document_id}


def client_for(statuses: list[dict], documents: list[dict] | None = None) -> httpx.AsyncClient:
    remaining = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingest":
            return httpx.Response(202, json=remaining.pop(0))
        if request.url.path == f"/jobs/{JOB_ID}":
            return httpx.Response(200, json=remaining.pop(0))
        if request.url.path == "/documents":
            return httpx.Response(200, json=documents or [])
        raise AssertionError(f"unexpected request to {request.url.path}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(run_eval, "POLL_SECONDS", 0)


async def test_upload_waits_for_indexing_to_finish(tmp_path, capsys):
    path = tmp_path / "handbook.md"
    path.write_text("# handbook", encoding="utf-8")
    statuses = [
        job("queued"),
        job("processing"),
        job("done", document_id=DOCUMENT_ID),
    ]
    documents = [{"id": DOCUMENT_ID, "chunk_count": 7}]

    async with client_for(statuses, documents) as client:
        await run_eval.upload(client, path)

    assert "indexed handbook.md: 7 chunks" in capsys.readouterr().out


async def test_upload_raises_when_indexing_fails(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-broken")
    statuses = [job("queued"), job("error", error="Cannot parse PDF")]

    async with client_for(statuses) as client:
        with pytest.raises(RuntimeError, match="Cannot parse PDF"):
            await run_eval.upload(client, path)


async def test_waiting_gives_up_instead_of_polling_forever():
    async with client_for([job("processing")] * 50) as client:
        with pytest.raises(RuntimeError, match="did not finish"):
            await run_eval.wait_for_job(client, job("queued"), timeout=0)


async def test_chunk_count_is_optional(tmp_path, capsys):
    path = tmp_path / "handbook.md"
    path.write_text("# handbook", encoding="utf-8")

    async with client_for([job("done", document_id=DOCUMENT_ID)], documents=[]) as client:
        await run_eval.upload(client, path)

    assert "unknown chunks" in capsys.readouterr().out


def test_the_module_imports_without_the_evaluation_dependencies():
    assert "ragas" not in json.dumps(list(run_eval.__dict__))
