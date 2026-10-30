"""RQ queue names — sync always outranks classify on the worker."""

from __future__ import annotations

from redis import Redis
from rq import Queue

# High priority: source sync / full-sync (user is waiting on the UI).
QUEUE_SYNC = "sync"
# Low priority: Jev classify batches (can run for a long time).
QUEUE_DEFAULT = "default"

# Worker must listen in this order so sync jobs jump ahead of classify.
WORKER_QUEUES = (QUEUE_SYNC, QUEUE_DEFAULT)


def queue(name: str, connection: Redis) -> Queue:
    return Queue(name, connection=connection)


def sync_queue(connection: Redis) -> Queue:
    return queue(QUEUE_SYNC, connection)


def default_queue(connection: Redis) -> Queue:
    return queue(QUEUE_DEFAULT, connection)
