from __future__ import annotations

from backend.core.db import db, row_to_dict, utcnow


def queue_research(
    conn,
    project_id: int,
    command: str,
    *,
    run_id: int | None = None,
    conversation_id: int | None = None,
) -> tuple[dict, bool]:
    """Return (job, created). created is False when a job was already running."""
    running = conn.execute(
        "SELECT id FROM jobs WHERE project_id = ? AND status IN ('queued', 'running')",
        (project_id,),
    ).fetchone()
    if running:
        if conversation_id:
            conn.execute(
                """
                UPDATE jobs
                SET conversation_id = COALESCE(conversation_id, ?)
                WHERE id = ?
                """,
                (conversation_id, running["id"]),
            )
        job = row_to_dict(
            conn.execute("SELECT * FROM jobs WHERE id = ?", (running["id"],)).fetchone()
        )
        return job, False
    cursor = conn.execute(
        """
        INSERT INTO jobs (project_id, status, command, kind, run_id, conversation_id, created_at)
        VALUES (?, ?, ?, 'research', ?, ?, ?)
        """,
        (project_id, "queued", command, run_id, conversation_id, utcnow()),
    )
    job_id = cursor.lastrowid
    conn.execute(
        "UPDATE projects SET research_status = ?, last_job_id = ?, skipped = 0 WHERE id = ?",
        ("queued", job_id, project_id),
    )
    job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    return job, True


def get_job_snapshot(job_id: int) -> dict | None:
    with db() as conn:
        job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
        project = None
        if job:
            project = row_to_dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (job["project_id"],)).fetchone()
            )
    if not job:
        return None
    return {"job": job, "project": project}
