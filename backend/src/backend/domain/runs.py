from __future__ import annotations

import json
from typing import Any

from backend.core.db import db, row_to_dict, utcnow
from backend.domain.jobs import queue_research
from backend.domain.research import saved_research_command


def create_run(
    *,
    conversation_id: int | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utcnow()
    with db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO runs (conversation_id, status, plan, created_at)
            VALUES (?, 'queued', ?, ?)
            """,
            (conversation_id, json.dumps(plan or {}), now),
        )
        run_id = cursor.lastrowid
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
    return run or {}


def _compose_batch_command(
    *,
    command: str | None,
    skill_slug: str | None,
    prompt_slug: str | None,
) -> tuple[str, dict[str, Any]]:
    """Build worker command, appending selected skill/prompt guidance."""
    from backend.core.config import RESEARCH_PROMPT
    from backend.domain.prompt_enrich import replace_prompt_in_command

    base = (command or saved_research_command()).strip()
    meta: dict[str, Any] = {"skill_slug": skill_slug, "prompt_slug": prompt_slug}
    prompt_text = RESEARCH_PROMPT
    with db() as conn:
        if prompt_slug:
            row = conn.execute(
                "SELECT content FROM prompts WHERE slug = ?", (prompt_slug,)
            ).fetchone()
            if row and row["content"]:
                prompt_text = row["content"].strip()
                meta["prompt_body"] = prompt_text[:500]
        if skill_slug:
            row = conn.execute(
                "SELECT content FROM skills WHERE slug = ?", (skill_slug,)
            ).fetchone()
            if row and row["content"]:
                skill_body = row["content"].strip()
                meta["skill_body"] = skill_body[:500]
                prompt_text = f"{prompt_text}\n\n[Skill:{skill_slug}]\n{skill_body}"
    cmd = replace_prompt_in_command(base, prompt_text)
    return cmd.strip(), meta


def queue_research_batch(
    project_ids: list[int],
    *,
    conversation_id: int | None = None,
    skill_slug: str | None = None,
    prompt_slug: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    cmd, enrich_meta = _compose_batch_command(
        command=command, skill_slug=skill_slug, prompt_slug=prompt_slug
    )
    plan = {
        "project_ids": project_ids,
        "command": cmd,
        **enrich_meta,
    }
    run = create_run(conversation_id=conversation_id, plan=plan)
    run_id = run["id"]
    tasks: list[dict] = []
    jobs: list[dict] = []
    now = utcnow()
    with db() as conn:
        conn.execute("UPDATE runs SET status = 'running' WHERE id = ?", (run_id,))
        for project_id in project_ids:
            task_cur = conn.execute(
                """
                INSERT INTO run_tasks (run_id, project_id, skill_slug, prompt_slug, status, created_at)
                VALUES (?, ?, ?, ?, 'queued', ?)
                """,
                (run_id, project_id, skill_slug, prompt_slug, now),
            )
            task_id = task_cur.lastrowid
            job, created = queue_research(
                conn,
                project_id,
                cmd,
                run_id=run_id,
                conversation_id=conversation_id,
            )
            if created:
                conn.execute(
                    "UPDATE run_tasks SET job_id = ?, status = 'running' WHERE id = ?",
                    (job["id"], task_id),
                )
            else:
                conn.execute(
                    "UPDATE run_tasks SET job_id = ?, status = ? WHERE id = ?",
                    (job["id"], job.get("status") or "queued", task_id),
                )
            task = row_to_dict(
                conn.execute("SELECT * FROM run_tasks WHERE id = ?", (task_id,)).fetchone()
            )
            tasks.append(task or {})
            jobs.append({"job": job, "created": created, "task_id": task_id})
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
    return {"run": run, "tasks": tasks, "jobs": jobs}


def on_research_job_finished(job_id: int) -> None:
    summary = ""
    conv_id = None
    run_id = None
    with db() as conn:
        job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
        if not job:
            return
        run_id = job.get("run_id")
        status = "done" if job.get("status") == "done" else "error"
        project = conn.execute(
            "SELECT full_name FROM projects WHERE id = ?", (job["project_id"],)
        ).fetchone()
        name = project["full_name"] if project else f"project {job['project_id']}"
        if not run_id:
            conv_id = job.get("conversation_id")
            summary = f"Research job {job_id} for {name} finished with status {status}."
            if job.get("error"):
                summary += f"\nError: {str(job['error'])[:500]}"
        else:
            finished = job.get("finished_at") or utcnow()
            conn.execute(
                """
                UPDATE run_tasks
                SET status = ?, finished_at = ?
                WHERE job_id = ?
                """,
                (status, finished, job_id),
            )
            pending = conn.execute(
                """
                SELECT COUNT(*) AS c FROM run_tasks
                WHERE run_id = ? AND status IN ('queued', 'running')
                """,
                (run_id,),
            ).fetchone()["c"]
            if pending:
                return
            run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
            if not run:
                return
            tasks = conn.execute(
                """
                SELECT rt.*, p.full_name
                FROM run_tasks rt
                JOIN projects p ON p.id = rt.project_id
                WHERE rt.run_id = ?
                ORDER BY rt.id
                """,
                (run_id,),
            ).fetchall()
            lines = [f"Research batch run #{run_id} finished."]
            for row in tasks:
                item = dict(row)
                lines.append(
                    f"- {item['full_name']}: {item['status']}"
                    + (f" (job {item['job_id']})" if item.get("job_id") else "")
                )
            summary = "\n".join(lines)
            now = utcnow()
            conn.execute(
                "UPDATE runs SET status = 'done', finished_at = ? WHERE id = ?",
                (now, run_id),
            )
            conv_id = run.get("conversation_id") or job.get("conversation_id")
            if not conv_id:
                linked = conn.execute(
                    """
                    SELECT conversation_id FROM jobs
                    WHERE run_id = ? AND conversation_id IS NOT NULL
                    ORDER BY id DESC LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                conv_id = linked["conversation_id"] if linked else None
    if conv_id and summary:
        from backend.master.wake import schedule_wake

        schedule_wake(int(conv_id), summary, job_id=job_id, run_id=run_id)


def list_runs(limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row_to_dict(r) for r in rows if row_to_dict(r)]


def get_run(run_id: int) -> dict | None:
    with db() as conn:
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
        if not run:
            return None
        tasks = conn.execute(
            "SELECT * FROM run_tasks WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    run["tasks"] = [row_to_dict(t) for t in tasks if row_to_dict(t)]
    if isinstance(run.get("plan"), str):
        try:
            run["plan"] = json.loads(run["plan"] or "{}")
        except json.JSONDecodeError:
            run["plan"] = {}
    return run
