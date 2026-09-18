import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.config import settings

log = logging.getLogger(__name__)

_subscribers: dict[UUID, set[asyncio.Queue]] = defaultdict(set)


class TooManySubscribers(Exception):
    pass


def subscribe(user_id: UUID) -> asyncio.Queue:
    queues = _subscribers[user_id]
    if len(queues) >= settings.events_max_subscribers:
        raise TooManySubscribers(f"At most {settings.events_max_subscribers} event streams per user")
    queue: asyncio.Queue = asyncio.Queue(maxsize=settings.events_queue_size)
    queues.add(queue)
    return queue


def unsubscribe(user_id: UUID, queue: asyncio.Queue) -> None:
    queues = _subscribers.get(user_id)
    if queues is None:
        return
    queues.discard(queue)
    if not queues:
        _subscribers.pop(user_id, None)


def subscriber_count(user_id: UUID) -> int:
    return len(_subscribers.get(user_id, ()))


def broadcast(event: dict) -> None:
    for user_id in list(_subscribers):
        publish(user_id, event)


def publish(user_id: UUID, event: dict) -> None:
    queues = _subscribers.get(user_id)
    if not queues:
        return
    payload = {**event, "timestamp": datetime.now(UTC).isoformat()}
    for queue in list(queues):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            log.debug("Dropping event for slow subscriber of user %s", user_id)
