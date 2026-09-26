import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.api import routes
from app.config import settings
from app.db.models import IngestJob
from app.db.session import tenant_session
from app.ingestion import jobs
from tests.conftest import auth_headers

UPLOAD = {"file": ("notes.txt", b"hello world")}


@pytest.fixture(autouse=True)
def roomy_limits(monkeypatch):
    monkeypatch.setattr(settings, "max_documents", 5)
    monkeypatch.setattr(routes, "_receiving", set())


async def test_a_second_upload_waits_for_the_first_to_be_indexed(client, make_user):
    user = await make_user()
    first = await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))
    assert first.status_code == 202 and first.json()["status"] == "queued"

    second = await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))
    assert second.status_code == 429
    assert second.json()["detail"] == routes.UPLOAD_BUSY


async def test_a_queued_job_counts_against_the_document_limit(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "max_documents", 1)
    user = await make_user()
    assert (await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))).status_code == 202
    assert await jobs.unfinished(user.id) == 1
    assert (await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))).status_code == 429


async def test_parallel_uploads_from_one_account_accept_only_one(client, make_user):
    user = await make_user()
    responses = await asyncio.gather(
        *(client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id)) for _ in range(4))
    )
    assert sorted(response.status_code for response in responses) == [202, 429, 429, 429]
    assert user.id not in routes._receiving


async def test_an_abandoned_job_does_not_block_the_account(client, make_user):
    user = await make_user()
    job = (await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))).json()
    async with tenant_session(user.id) as session:
        await session.execute(
            update(IngestJob)
            .where(IngestJob.id == job["id"])
            .values(created_at=datetime.now(UTC) - timedelta(seconds=jobs.ABANDONED_AFTER_SECONDS + 60))
        )
        await session.commit()
    assert await jobs.unfinished(user.id) == 0
    assert (await client.post("/ingest", files=UPLOAD, headers=auth_headers(user.id))).status_code == 202


async def test_a_retried_upload_with_the_same_key_still_returns_its_job(client, make_user):
    user = await make_user()
    headers = {**auth_headers(user.id), "Idempotency-Key": "upload-1"}
    first = await client.post("/ingest", files=UPLOAD, headers=headers)
    again = await client.post("/ingest", files=UPLOAD, headers=headers)
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
