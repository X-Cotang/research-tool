"""Start queued CLI jobs from every path, including a Master wake.

The analysis CLIs are one-shot processes. A follow-up is the next turn: it
waits until the current job for that repository finishes, then starts a new
process with the same CLI and the user's note.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from pathlib import Path

from backend.core.db import db, row_to_dict, utcnow
from backend.domain.jobs import queue_research

log = logging.getLogger(__name__)

_inflight: set[int] = set()


def schedule_job(job_id: int, project_id: int) -> bool:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    if job_id in _inflight:
        return False
    _inflight.add(job_id)
    loop.create_task(_guarded(job_id, project_id))
    return True


async def _guarded(job_id: int, project_id: int) -> None:
    from backend.domain.research import run_research_job

    try:
        await run_research_job(job_id, project_id)
    except Exception:
        log.exception("research job %s failed outside the worker", job_id)
    finally:
        _inflight.discard(job_id)
        try:
            kick()
        except Exception:
            log.exception("failed to start the next queued job")


def build_followup_command(parent: dict, project: dict, message: str) -> str:
    from backend.domain.worker_command import compose_resume_command, compose_worker_command

    session_id = (parent.get("cli_session_id") or project.get("cli_session_id") or "").strip()
    resumed = compose_resume_command(parent.get("command") or "", session_id, message)
    if resumed:
        return resumed

    brief = (
        f"Continue the security review of {project.get('full_name')}. "
        f"This is a follow-up to job {parent.get('id')} "
        f"(status {parent.get('status') or 'unknown'}). "
        "Read RESEARCH_NOTES.md when it exists. Continue from that work "
        "instead of repeating it, unless this note asks you to recheck it.\n\n"
        f"User note:\n{message.strip()}"
    )
    command, _meta = compose_worker_command(
        prompt=brief,
        command=(parent.get("command") or None),
    )
    return command


def queue_followup(parent_job_id: int, message: str) -> dict:
    text = (message or "").strip()
    if not text:
        raise ValueError("Follow-up cannot be empty.")
    if len(text) > 8000:
        raise ValueError("Follow-up is too long.")
    with db() as conn:
        parent = row_to_dict(
            conn.execute("SELECT * FROM jobs WHERE id = ?", (parent_job_id,)).fetchone()
        )
        if not parent:
            raise ValueError("Job not found.")
        project = row_to_dict(
            conn.execute(
                "SELECT * FROM projects WHERE id = ?", (parent["project_id"],)
            ).fetchone()
        )
        if not project:
            raise ValueError("Project not found.")
        cursor = conn.execute(
            """
            INSERT INTO job_followups
                (project_id, parent_job_id, message, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (project["id"], parent_job_id, text, utcnow()),
        )
        followup_id = int(cursor.lastrowid)
    started = activate_pending_followups()
    match = next((item for item in started if item["followup_id"] == followup_id), None)
    if match:
        return {
            "followup_id": followup_id,
            "waiting": False,
            "job_id": match["job_id"],
            "project_id": project["id"],
            "detail": _followup_detail(parent, project, waiting=False),
        }
    return {
        "followup_id": followup_id,
        "waiting": True,
        "job_id": None,
        "project_id": project["id"],
        "detail": _followup_detail(parent, project, waiting=True),
    }


def _followup_cli_name(parent: dict) -> str:
    command = parent.get("command") or ""
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = []
    if not parts:
        return "CLI"
    return Path(parts[0]).name


def _followup_detail(parent: dict, project: dict, *, waiting: bool) -> str:
    session_id = (parent.get("cli_session_id") or project.get("cli_session_id") or "").strip()
    cli_name = _followup_cli_name(parent)
    if session_id:
        when = "after the current process exits" if waiting else "now"
        return (
            f"This note reopens {cli_name} session {session_id} {when}. "
            "The previous process is not kept alive."
        )
    if waiting:
        return (
            "The current CLI run cannot take input. This note starts the next "
            "turn when it finishes. A session id has not been saved yet, "
            "so the next turn reads RESEARCH_NOTES.md."
        )
    return "Started the next CLI turn."


def activate_pending_followups() -> list[dict]:
    started: list[dict] = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT f.* FROM job_followups f
            WHERE f.status = 'pending'
              AND NOT EXISTS (
                SELECT 1 FROM jobs j
                WHERE j.project_id = f.project_id
                  AND j.status IN ('queued', 'running')
              )
            ORDER BY f.id
            """
        ).fetchall()
        seen: set[int] = set()
        for row in rows:
            project_id = int(row["project_id"])
            if project_id in seen:
                continue
            seen.add(project_id)
            parent = row_to_dict(
                conn.execute("SELECT * FROM jobs WHERE id = ?", (row["parent_job_id"],)).fetchone()
            )
            project = row_to_dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            )
            if not parent or not project:
                continue
            try:
                command = build_followup_command(parent, project, row["message"])
            except Exception as exc:
                conn.execute(
                    """
                    UPDATE job_followups
                    SET status = 'error', message = message || ?
                    WHERE id = ?
                    """,
                    (f"\n\n[could not start: {exc}]", row["id"]),
                )
                continue
            job, created = queue_research(
                conn,
                project_id,
                command,
                conversation_id=parent.get("conversation_id"),
            )
            if not created or not job:
                continue
            conn.execute(
                "UPDATE job_followups SET status = 'started', job_id = ? WHERE id = ?",
                (job["id"], row["id"]),
            )
            started.append(
                {
                    "followup_id": int(row["id"]),
                    "job_id": int(job["id"]),
                    "project_id": project_id,
                }
            )
    for item in started:
        schedule_job(item["job_id"], item["project_id"])
    return started


def kick() -> int:
    """Start every queued job that this process is not already running."""
    activate_pending_followups()
    with db() as conn:
        rows = conn.execute(
            "SELECT id, project_id FROM jobs WHERE status = 'queued' ORDER BY id"
        ).fetchall()
    started = 0
    for row in rows:
        if schedule_job(int(row["id"]), int(row["project_id"])):
            started += 1
    return started


def list_pending_followups(project_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, parent_job_id, message, status, job_id, created_at
            FROM job_followups
            WHERE project_id = ? AND status = 'pending'
            ORDER BY id
            """,
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


async def supervise_forever() -> None:
    while True:
        try:
            kick()
        except Exception:
            log.exception("job supervisor tick failed")
        await asyncio.sleep(2)
