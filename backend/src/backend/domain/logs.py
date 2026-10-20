from __future__ import annotations

import asyncio
from typing import Any


class LogHub:
    """Fan-out job log lines from worker threads to SSE subscribers."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: dict[int, list[asyncio.Queue]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, job_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._queues.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: int, queue: asyncio.Queue) -> None:
        listeners = self._queues.get(job_id) or []
        if queue in listeners:
            listeners.remove(queue)
        if not listeners:
            self._queues.pop(job_id, None)

    def publish(self, job_id: int, event: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None:
            return

        def _put() -> None:
            for queue in list(self._queues.get(job_id) or []):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

        loop.call_soon_threadsafe(_put)


log_hub = LogHub()
