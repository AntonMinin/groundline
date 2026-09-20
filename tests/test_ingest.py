import asyncio

import pytest

from app.config import settings
from app.ingestion import jobs, service
from tests.conftest import auth_headers

HANDBOOK = b"# Handbook\n\nRemote work is allowed up to three days per week.\n"


async def wait_for_job(client, user_id, job_id, expected: str) -> dict:
    for _ in range(100):
        job = (await client.get(f"/jobs/{job_id}", headers=auth_headers(user_id))).json()
        if job["status"] == expected:
            return job
        await asyncio.sleep(0.1)
    raise AssertionError(f"job stayed in status {job['status']}, expected {expected}")


async def test_upload_is_accepted_and_processed_in_background(client, make_user, workers):
    user = await make_user()
    response = await client.post(
        "/ingest", files={"file": ("handbook.md", HANDBOOK)}, headers=auth_headers(user.id)
    )
    assert response.status_code == 202
    assert response.json()["status"] in ("queued", "processing")

    job = await wait_for_job(client, user.id, response.json()["id"], "done")
    documents = (await client.get("/documents", headers=auth_headers(user.id))).json()
    assert documents[0]["id"] == job["document_id"]
    assert documents[0]["chunk_count"] == 1
    assert documents[0]["size_bytes"] == len(HANDBOOK)


async def test_idempotency_key_replays_the_same_job(client, make_user, workers):
    user = await make_user()
    headers = {**auth_headers(user.id), "Idempotency-Key": "upload-42"}

    first = await client.post("/ingest", files={"file": ("handbook.md", HANDBOOK)}, headers=headers)
    assert first.status_code == 202
    await wait_for_job(client, user.id, first.json()["id"], "done")

    second = await client.post("/ingest", files={"file": ("handbook.md", HANDBOOK)}, headers=headers)
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["status"] == "done"
    assert len((await client.get("/documents", headers=auth_headers(user.id))).json()) == 1


async def test_broken_pdf_fails_the_job_with_a_message(client, make_user, workers):
    user = await make_user()
    response = await client.post(
        "/ingest", files={"file": ("broken.pdf", b"not really a pdf")}, headers=auth_headers(user.id)
    )
    assert response.status_code == 202

    job = await wait_for_job(client, user.id, response.json()["id"], "error")
    assert "PDF" in job["error"]
    assert (await client.get("/documents", headers=auth_headers(user.id))).json() == []


async def test_upload_validates_before_accepting(client, make_user, workers, monkeypatch):
    user = await make_user()
    headers = auth_headers(user.id)
    assert (await client.post("/ingest", files={"file": ("x.png", b"data")}, headers=headers)).status_code == 415
    assert (await client.post("/ingest", files={"file": ("x.md", b"")}, headers=headers)).status_code == 422

    monkeypatch.setattr(settings, "max_upload_mb", 0)
    assert (await client.post("/ingest", files={"file": ("x.md", HANDBOOK)}, headers=headers)).status_code == 413


async def test_jobs_are_not_visible_to_other_users(client, make_user, workers):
    user, stranger = await make_user(), await make_user()
    response = await client.post(
        "/ingest", files={"file": ("handbook.md", HANDBOOK)}, headers=auth_headers(user.id)
    )
    job_id = response.json()["id"]
    assert (await client.get(f"/jobs/{job_id}", headers=auth_headers(stranger.id))).status_code == 404
