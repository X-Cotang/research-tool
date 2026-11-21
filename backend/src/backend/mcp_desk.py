"""Streamable HTTP MCP for Hermes.

The endpoint is the same process and the same admin JWT as the desk API.
Tools queue work and return. They never accept a shell command.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations

from backend.api.orgs import ScanRequest, scan
from backend.core.auth import read_username
from backend.core.db import db, row_to_dict
from backend.domain.findings import list_findings
from backend.domain.jobs import get_job_snapshot, queue_research
from backend.domain.research import saved_research_command
from backend.domain.runs import queue_research_batch
from backend.domain.supervisor import schedule_job

_INSTRUCTIONS = """
You are connected to the research desk. Use these tools in order:
1. research_list_repos or research_scan_org to get numeric project ids.
2. research_create_task or research_create_batch to queue work. Both return immediately with job ids.
3. research_get_task or research_list_tasks until status is done or error. Do not wait inside the create call.
4. research_list_findings for a finished project.
A second create for a project that is already queued or running returns the existing job.
Never invent a shell command. The desk runs its saved CLI preset.
""".strip()

_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)

server = MCPServer(
    "research-desk",
    instructions=_INSTRUCTIONS,
)


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _ok(**payload: Any) -> str:
    return _dump({"ok": True, **payload})


def _err(message: str) -> str:
    return _dump({"ok": False, "error": message})


def _bearer(headers: Any) -> str | None:
    if not headers:
        return None
    raw = ""
    for key, value in headers.items():
        if str(key).lower() == "authorization":
            raw = str(value)
            break
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
        return token or None
    return None


def _repo(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "full_name": row.get("full_name"),
        "stars": row.get("stars"),
        "language": row.get("language"),
        "research_status": row.get("research_status"),
        "last_job_id": row.get("last_job_id"),
    }


def _task(job: dict[str, Any], full_name: str | None = None) -> dict[str, Any]:
    error = job.get("error") or ""
    if len(error) > 1000:
        error = error[-1000:]
    return {
        "job_id": job.get("id"),
        "project_id": job.get("project_id"),
        "full_name": full_name,
        "status": job.get("status"),
        "error_step": job.get("error_step"),
        "cli_activity": job.get("cli_activity"),
        "error": error or None,
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
    }


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    body = text.strip()
    if len(body) <= 4000:
        return body
    return body[-4000:]


@server.tool(annotations=_READ)
def research_whoami(ctx: Context) -> str:
    """Confirm which admin account this MCP connection is using. Call this first if a later tool returns not authenticated."""
    username = read_username(_bearer(ctx.headers))
    if not username:
        return _err("Not authenticated")
    return _ok(username=username)


@server.tool(annotations=_READ)
def research_list_repos(
    org: str | None = None,
    research_status: str | None = None,
    limit: int = 30,
) -> str:
    """List repositories already stored on the desk. Returns at most 50 rows with project id, full_name, stars, language, research_status, and last_job_id."""
    cap = max(1, min(int(limit or 30), 50))
    status = (research_status or "").strip().lower()
    org_name = (org or "").strip()
    clauses = ["1 = 1"]
    params: list[Any] = []
    if org_name:
        clauses.append("lower(o.login) = lower(?)")
        params.append(org_name)
    if status:
        clauses.append("p.research_status = ?")
        params.append(status)
    params.append(cap)
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT p.id, p.full_name, p.stars, p.language, p.research_status, p.last_job_id
            FROM projects p
            JOIN organizations o ON o.id = p.org_id
            WHERE {' AND '.join(clauses)}
            ORDER BY p.research_score DESC, p.stars DESC, p.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    repos = [_repo(row_to_dict(row) or {}) for row in rows]
    return _ok(count=len(repos), repos=repos)


@server.tool(annotations=_WRITE)
async def research_scan_org(
    org: str,
    mode: str = "fresh",
    min_stars: int = 0,
    max_age_days: int = 180,
    created_within_days: int = 90,
    sort_by: str = "created",
    project_types: list[str] | None = None,
) -> str:
    """Discover one page of GitHub repositories for an org or user login and store them. This waits on GitHub, not on research workers. mode is fresh or continue. Use the returned project ids with research_create_task."""
    try:
        result = await scan(
            ScanRequest(
                org_url=org,
                mode=mode,
                min_stars=min_stars,
                max_age_days=max_age_days,
                created_within_days=created_within_days,
                sort_by=sort_by,
                project_types=project_types or ["web", "api"],
            )
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _err(detail)
    added = [_repo(item) for item in (result.get("added") or [])[:50]]
    return _ok(
        message=result.get("message"),
        added_count=result.get("added_count") or 0,
        mode=result.get("mode"),
        repos=added,
    )


@server.tool(annotations=_WRITE)
def research_create_task(project_id: int | None = None, full_name: str | None = None) -> str:
    """Queue one research job with the desk's saved CLI preset and return immediately. Pass project_id or full_name such as owner/repo. If a job is already queued or running, created is false and job_id is that job. Then poll research_get_task."""
    if project_id is None and not (full_name or "").strip():
        return _err("Provide project_id or full_name")
    command = saved_research_command().strip()
    if not command:
        return _err("Research command is not configured")
    with db() as conn:
        if project_id is not None:
            project = row_to_dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (int(project_id),)).fetchone()
            )
        else:
            project = row_to_dict(
                conn.execute(
                    "SELECT * FROM projects WHERE lower(full_name) = lower(?)",
                    ((full_name or "").strip(),),
                ).fetchone()
            )
        if not project:
            return _err("Project not found")
        job, created = queue_research(conn, int(project["id"]), command)
    if created and job:
        schedule_job(int(job["id"]), int(project["id"]))
    return _ok(
        created=created,
        job_id=job.get("id") if job else None,
        project_id=project["id"],
        full_name=project.get("full_name"),
        status=job.get("status") if job else None,
    )


@server.tool(annotations=_WRITE)
def research_create_batch(project_ids: list[int]) -> str:
    """Queue research for several project ids as one run. Returns immediately. Each row has job_id and created. Poll research_list_tasks or research_get_task. Maximum 30 ids."""
    ids = [int(item) for item in project_ids]
    if not ids:
        return _err("Provide at least one project_id")
    if len(ids) > 30:
        return _err("At most 30 projects per batch")
    result = queue_research_batch(ids)
    if result.get("error"):
        return _err(str(result["error"]))
    jobs = []
    for entry in result.get("jobs") or []:
        job = entry.get("job") or {}
        if entry.get("created") and job.get("id") and entry.get("project_id"):
            schedule_job(int(job["id"]), int(entry["project_id"]))
        jobs.append(
            {
                "job_id": job.get("id"),
                "project_id": entry.get("project_id"),
                "full_name": entry.get("full_name"),
                "created": bool(entry.get("created")),
                "status": job.get("status"),
            }
        )
    run = result.get("run") or {}
    return _ok(run_id=run.get("id"), jobs=jobs)


@server.tool(annotations=_READ)
def research_get_task(job_id: int) -> str:
    """Read one research job. status is queued, running, done, or error. The report excerpt is at most 4000 characters. Poll this after research_create_task."""
    snapshot = get_job_snapshot(int(job_id))
    if not snapshot:
        return _err("Job not found")
    job = snapshot["job"]
    project = snapshot.get("project") or {}
    excerpt = _excerpt(job.get("report"))
    if excerpt is None and job.get("status") in {"done", "error"}:
        excerpt = _excerpt(job.get("log"))
    return _ok(
        task=_task(job, project.get("full_name")),
        research_status=project.get("research_status"),
        report_excerpt=excerpt,
    )


@server.tool(annotations=_READ)
def research_list_tasks(limit: int = 30) -> str:
    """List queued and running jobs, then the latest done or error jobs. Cap 30. Use this to check a batch without calling research_get_task for every id."""
    cap = max(1, min(int(limit or 30), 30))
    with db() as conn:
        live = conn.execute(
            """
            SELECT j.id, j.project_id, j.status, j.error_step, j.cli_activity, j.error,
                   j.created_at, j.finished_at, p.full_name
            FROM jobs j
            JOIN projects p ON p.id = j.project_id
            WHERE j.status IN ('queued', 'running')
            ORDER BY j.id
            """
        ).fetchall()
        recent = conn.execute(
            """
            SELECT j.id, j.project_id, j.status, j.error_step, j.cli_activity, j.error,
                   j.created_at, j.finished_at, p.full_name
            FROM jobs j
            JOIN projects p ON p.id = j.project_id
            WHERE j.status IN ('done', 'error')
            ORDER BY j.id DESC
            LIMIT ?
            """,
            (cap,),
        ).fetchall()
    return _ok(
        active=[_task(row_to_dict(row) or {}, (row_to_dict(row) or {}).get("full_name")) for row in live],
        recent=[_task(row_to_dict(row) or {}, (row_to_dict(row) or {}).get("full_name")) for row in recent],
    )


@server.tool(annotations=_READ)
def research_list_findings(project_id: int | None = None, limit: int = 40) -> str:
    """List parsed findings. Optional project_id. Each row has id, project_id, title, severity, status, and file_path. Cap 40."""
    cap = max(1, min(int(limit or 40), 40))
    rows = list_findings(project_id=project_id, limit=cap)
    findings = [
        {
            "id": row.get("id"),
            "project_id": row.get("project_id"),
            "title": row.get("title"),
            "severity": row.get("severity"),
            "status": row.get("status"),
            "file_path": row.get("file_path"),
        }
        for row in rows
    ]
    return _ok(count=len(findings), findings=findings)


def mcp_http_app():
    """ASGI app whose route is `/`. Mount it at `/mcp`."""
    return server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
