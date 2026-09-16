import asyncio
import json
import uuid

import pytest

from app import events
from app.api import routes
from app.config import settings
from tests.conftest import auth_headers


def test_publish_reaches_every_subscriber_of_that_user():
    alice, bob = uuid.uuid4(), uuid.uuid4()
    first, second, other = events.subscribe(alice), events.subscribe(alice), events.subscribe(bob)
    try:
        events.publish(alice, {"type": "node_started", "node": "retrieve"})
        assert first.get_nowait()["node"] == "retrieve"
        assert second.get_nowait()["node"] == "retrieve"
        assert other.empty()
    finally:
        events.unsubscribe(alice, first)
        events.unsubscribe(alice, second)
        events.unsubscribe(bob, other)
    assert events.subscriber_count(alice) == 0


def test_slow_subscriber_is_dropped_not_blocking(monkeypatch):
    monkeypatch.setattr(settings, "events_queue_size", 2)
    user = uuid.uuid4()
    queue = events.subscribe(user)
    try:
        for index in range(5):
            events.publish(user, {"type": "node_started", "node": str(index)})
        assert queue.qsize() == 2
    finally:
        events.unsubscribe(user, queue)


def test_subscriber_limit(monkeypatch):
    monkeypatch.setattr(settings, "events_max_subscribers", 1)
    user = uuid.uuid4()
    queue = events.subscribe(user)
    try:
        with pytest.raises(events.TooManySubscribers):
            events.subscribe(user)
    finally:
        events.unsubscribe(user, queue)


async def _next_chunk(iterator) -> str:
    return await asyncio.wait_for(iterator.__anext__(), timeout=5)


async def test_events_endpoint_streams_events_and_heartbeats(make_user, monkeypatch):
    monkeypatch.setattr(settings, "events_heartbeat_seconds", 0.05)
    user = await make_user()
    response = await routes.events_stream(user)
    assert response.media_type == "text/event-stream"
    iterator = response.body_iterator
    try:
        assert json.loads((await _next_chunk(iterator)).split("data: ")[1])["type"] == "connected"
        assert (await _next_chunk(iterator)).startswith(": ping")

        events.publish(user.id, {"type": "node_started", "node": "check_cache"})
        while (chunk := await _next_chunk(iterator)).startswith(": ping"):
            pass
        event = json.loads(chunk.split("data: ")[1])
        assert event["node"] == "check_cache" and event["type"] == "node_started" and "timestamp" in event
        assert chunk.startswith("event: node_started")
    finally:
        await iterator.aclose()
    assert events.subscriber_count(user.id) == 0


async def test_events_endpoint_enforces_subscriber_limit(make_user, monkeypatch):
    monkeypatch.setattr(settings, "events_max_subscribers", 1)
    user = await make_user()
    first = await routes.events_stream(user)
    iterator = first.body_iterator
    try:
        await _next_chunk(iterator)
        with pytest.raises(Exception, match="event streams"):
            await routes.events_stream(user)
    finally:
        await iterator.aclose()


async def test_events_endpoint_requires_authentication(client):
    assert (await client.get("/events")).status_code == 401
