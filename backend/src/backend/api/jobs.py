from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.db import db, row_to_dict
from backend.domain.jobs import get_job_snapshot
from backend.domain.logs import log_hub
from backend.domain.supervisor import queue_followup

router = APIRouter()


class FollowUpRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/jobs/live")
def live_jobs() -> dict:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT j.id, j.project_id, j.status, j.run_id, j.cli_activity, j.cli_session_id,
                   j.error_step, j.created_at, p.full_name
            FROM jobs j
            JOIN projects p ON p.id = j.project_id
            WHERE j.status IN ('queued', 'running')
            ORDER BY j.id
            """
        ).fetchall()
    return {"jobs": [row_to_dict(row) for row in rows]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int) -> dict:
    snapshot = get_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot


@router.post("/jobs/{job_id}/follow-up")
def follow_up(job_id: int, body: FollowUpRequest) -> dict:
    try:
        return queue_followup(job_id, body.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: int) -> StreamingResponse:
    queue = log_hub.subscribe(job_id)

    async def events():
        try:
            snapshot = get_job_snapshot(job_id)
            if not snapshot:
                yield _sse({"type": "error", "detail": "Job not found"})
                return
            # Lines already stored on the job are in the snapshot. Drop duplicates
            # that arrived between subscribe and this read.
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
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
