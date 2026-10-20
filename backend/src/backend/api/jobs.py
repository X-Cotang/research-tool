from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.domain.jobs import get_job_snapshot
from backend.domain.logs import log_hub

router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict:
    snapshot = get_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int) -> StreamingResponse:
    queue = log_hub.subscribe(job_id)

    async def events():
        try:
            snapshot = get_job_snapshot(job_id)
            if not snapshot:
                yield _sse({"type": "error", "detail": "Job not found"})
                return
            yield _sse({"type": "snapshot", **snapshot})
            if snapshot["job"]["status"] in {"done", "error"}:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield _sse(event)
                if event.get("type") == "done":
                    return
        finally:
            log_hub.unsubscribe(job_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
