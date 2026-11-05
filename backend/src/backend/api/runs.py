from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.domain.runs import get_run, list_runs, queue_research_batch
from backend.domain.supervisor import schedule_job

router = APIRouter()


class RunCreate(BaseModel):
    project_ids: list[int] = Field(min_length=1)
    conversation_id: int | None = None
    skill_slug: str | None = Field(default=None, max_length=80)
    prompt_slug: str | None = Field(default=None, max_length=80)
    command: str | None = Field(default=None, max_length=32000)


@router.get("/runs")
def runs_index(limit: int = 50) -> dict:
    return {"runs": list_runs(limit=limit)}


@router.get("/runs/{run_id}")
def runs_show(run_id: int) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": run}


@router.post("/runs")
def runs_create(body: RunCreate) -> dict:
    result = queue_research_batch(
        body.project_ids,
        conversation_id=body.conversation_id,
        skill_slug=body.skill_slug,
        prompt_slug=body.prompt_slug,
        command=body.command,
    )
    if result.get("error"):
        detail = result["error"]
        if result.get("errors"):
            detail = f"{detail} {result['errors']}"
        raise HTTPException(status_code=400, detail=str(detail)[:500])
    for entry in result.get("jobs") or []:
        if entry.get("created") and entry.get("job"):
            job = entry["job"]
            schedule_job(int(job["id"]), int(job["project_id"]))
    return result
