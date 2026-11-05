from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.helpers import org_catalog, remember_org, serialize_cursor, serialize_org
from backend.core.db import (
    db,
    get_search_cursor,
    load_org_projects,
    make_filter_key,
    row_to_dict,
)
from backend.domain.jobs import queue_research
from backend.domain.library import delete_project
from backend.domain.prompt_suggest import suggest_prompt
from backend.domain.research import saved_research_command
from backend.domain.supervisor import schedule_job

router = APIRouter()


class ResearchRequest(BaseModel):
    command: str | None = Field(default=None, max_length=32000)


class ProjectPatch(BaseModel):
    skipped: bool | None = None
    reported: bool | None = None
    false_positive: bool | None = None


class SuggestPromptRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    language: str | None = Field(default=None, max_length=80)
    topics: list[str] | None = None
    html_url: str | None = Field(default=None, max_length=500)
    local_path: str | None = Field(default=None, max_length=500)
    stars: int | None = None


@router.get("/projects")
def list_projects(
    org: str | None = None,
    min_stars: int | None = None,
    max_age_days: int | None = None,
    created_within_days: int | None = None,
    sort_by: str | None = None,
    project_types: str | None = None,
) -> dict:
    with db() as conn:
        orgs = org_catalog(conn)
        cursor = None
        if org:
            organization, projects = load_org_projects(conn, org)
            if organization is not None:
                if project_types is None:
                    types = ["web", "api"]
                else:
                    types = [
                        t.strip()
                        for t in project_types.split(",")
                        if t.strip() in {"web", "api"}
                    ]
                stars = 0 if min_stars is None else min_stars
                age = 180 if max_age_days is None else max_age_days
                created = 90 if created_within_days is None else created_within_days
                sort = (sort_by or "created").strip().lower()
                if sort not in {"stars", "updated", "created"}:
                    sort = "created"
                key = make_filter_key(
                    stars, age, types, created_within_days=created, sort_by=sort
                )
                cursor = get_search_cursor(conn, organization["login"], key)
        else:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY research_score DESC, stars DESC LIMIT 100"
            ).fetchall()
            organization, projects = None, [row_to_dict(row) for row in rows]
    if org and organization:
        remember_org(organization["login"])
    return {
        "organization": serialize_org(organization) if organization else None,
        "projects": projects,
        "organizations": orgs,
        "cursor": serialize_cursor(cursor),
    }


@router.get("/projects/{project_id}")
def get_project(project_id: int) -> dict:
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        jobs = conn.execute(
            "SELECT * FROM jobs WHERE project_id = ? ORDER BY id DESC LIMIT 5",
            (project_id,),
        ).fetchall()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project, "jobs": [row_to_dict(row) for row in jobs]}


@router.patch("/projects/{project_id}")
def patch_project(project_id: int, body: ProjectPatch) -> dict:
    if body.skipped is None and body.reported is None and body.false_positive is None:
        raise HTTPException(
            status_code=400,
            detail="Provide skipped, reported, and/or false_positive",
        )
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        if body.skipped is not None:
            conn.execute(
                "UPDATE projects SET skipped = ? WHERE id = ?",
                (1 if body.skipped else 0, project_id),
            )
        if body.reported is not None:
            reported = 1 if body.reported else 0
            conn.execute(
                """
                UPDATE projects
                SET reported = ?,
                    false_positive = CASE WHEN ? = 1 THEN 0 ELSE false_positive END
                WHERE id = ?
                """,
                (reported, reported, project_id),
            )
        if body.false_positive is not None:
            false_positive = 1 if body.false_positive else 0
            conn.execute(
                """
                UPDATE projects
                SET false_positive = ?,
                    reported = CASE WHEN ? = 1 THEN 0 ELSE reported END
                WHERE id = ?
                """,
                (false_positive, false_positive, project_id),
            )
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        org_row = conn.execute(
            "SELECT login FROM organizations WHERE id = ?", (project["org_id"],)
        ).fetchone()
        orgs = org_catalog(conn)
    return {
        "project": project,
        "organizations": orgs,
        "organization_login": org_row["login"] if org_row else None,
    }


@router.delete("/projects/{project_id}")
def remove_project(project_id: int, mode: str = "full") -> dict:
    normalized = (mode or "full").strip().lower()
    if normalized not in {"clone", "full"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be 'clone' (keep reports) or 'full' (wipe everything)",
        )
    try:
        project = delete_project(project_id, mode=normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    with db() as conn:
        orgs = org_catalog(conn)
    name = project.get("full_name") or str(project_id)
    if normalized == "clone":
        message = f"Removed local clone for {name}; reports and library entry kept."
    else:
        message = f"Permanently deleted {name} (clone, reports, and library data)."
    return {
        "ok": True,
        "mode": normalized,
        "project": project,
        "organizations": orgs,
        "message": message,
    }


@router.post("/projects/{project_id}/research")
def start_research(
    project_id: int,
    body: ResearchRequest = ResearchRequest(),
) -> dict:
    command = (body.command or saved_research_command()).strip()
    if not command:
        raise HTTPException(status_code=400, detail="Research command cannot be empty.")
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        job, created = queue_research(conn, project_id, command)
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
    if created:
        schedule_job(int(job["id"]), project_id)
    return {"job": job, "project": project, "created": created}


@router.post("/projects/{project_id}/suggest-prompt")
async def suggest_project_prompt(project_id: int) -> dict:
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return await suggest_prompt(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/suggest-prompt")
async def suggest_ad_hoc_prompt(body: SuggestPromptRequest) -> dict:
    project = {
        "full_name": body.full_name or "unknown/repo",
        "description": body.description or "",
        "language": body.language or "",
        "topics": body.topics or [],
        "html_url": body.html_url or "",
        "local_path": body.local_path or "",
        "stars": body.stars or 0,
    }
    try:
        return await suggest_prompt(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
