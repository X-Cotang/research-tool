from __future__ import annotations

import json
from typing import Any

from backend.core.db import db, row_to_dict, utcnow
from backend.domain.jobs import queue_research


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


def _library_prompt(
    *,
    prompt: str | None,
    skill_slug: str | None,
    prompt_slug: str | None,
) -> tuple[str | None, dict[str, Any]]:
    """Attach a stored prompt or skill to a brief the caller already wrote."""
    meta: dict[str, Any] = {"skill_slug": skill_slug, "prompt_slug": prompt_slug}
    text = (prompt or "").strip()
    with db() as conn:
        if prompt_slug and not text:
            row = conn.execute(
                "SELECT content FROM prompts WHERE slug = ?", (prompt_slug,)
            ).fetchone()
            if row and row["content"]:
                text = row["content"].strip()
                meta["prompt_body"] = text[:500]
        if skill_slug:
            row = conn.execute(
                "SELECT content FROM skills WHERE slug = ?", (skill_slug,)
            ).fetchone()
            if row and row["content"]:
                skill_body = row["content"].strip()
                meta["skill_body"] = skill_body[:500]
                text = f"{text}\n\n[Skill:{skill_slug}]\n{skill_body}".strip()
    return text or None, meta


def queue_research_batch(
    project_ids: list[int] | None = None,
    *,
    conversation_id: int | None = None,
    skill_slug: str | None = None,
    prompt_slug: str | None = None,
    command: str | None = None,
    prompt: str | None = None,
    preset_id: str | None = None,
    extra_args: list[str] | None = None,
    projects: list[Any] | None = None,
    expect_full_names: list[str] | None = None,
    allow_skipped: bool = False,
) -> dict[str, Any]:
    from backend.domain.project_lookup import resolve_research_targets
    from backend.domain.worker_command import WorkerCommandError, compose_worker_command

    resolved = resolve_research_targets(
        project_ids,
        projects,
        expect_full_names=expect_full_names,
    )
    if resolved.get("error"):
        return resolved

    shared_prompt, enrich_meta = _library_prompt(
        prompt=prompt, skill_slug=skill_slug, prompt_slug=prompt_slug
    )
    prepared: list[dict[str, Any]] = []
    for target in resolved["targets"]:
        target_prompt = (target.get("prompt") or "").strip() or shared_prompt
        try:
            cmd, meta = compose_worker_command(
                prompt=target_prompt,
                preset_id=target.get("preset") or preset_id,
                command=target.get("command") or command,
                extra_args=list(target.get("extra_args") or extra_args or []),
            )
        except WorkerCommandError as exc:
            return {
                "error": str(exc),
                "full_name": target.get("full_name"),
                "targets": [],
            }
        prepared.append({**target, "command": cmd, "command_meta": meta})

    ignored = [
        {"full_name": item.get("full_name"), "reason": "skipped"}
        for item in prepared
        if item.get("skipped") and not allow_skipped
    ]
    prepared = [item for item in prepared if allow_skipped or not item.get("skipped")]
    if not prepared:
        return {
            "error": "Nothing was queued. Every matching project is skipped.",
            "ignored": ignored,
        }

    plan = {
        "projects": [
            {
                "project_id": item["project_id"],
                "full_name": item["full_name"],
                "preset": item["command_meta"].get("preset"),
                "command_preview": item["command_meta"].get("command_preview"),
                "notes": item["command_meta"].get("notes"),
            }
            for item in prepared
        ],
        **enrich_meta,
    }
    run = create_run(conversation_id=conversation_id, plan=plan)
    run_id = run["id"]
    tasks: list[dict] = []
    jobs: list[dict] = []
    queued: list[dict] = []
    now = utcnow()
    with db() as conn:
        conn.execute("UPDATE runs SET status = 'running' WHERE id = ?", (run_id,))
        for item in prepared:
            task_cur = conn.execute(
                """
                INSERT INTO run_tasks (run_id, project_id, skill_slug, prompt_slug, status, created_at)
                VALUES (?, ?, ?, ?, 'queued', ?)
                """,
                (run_id, item["project_id"], skill_slug, prompt_slug, now),
            )
            task_id = task_cur.lastrowid
            job, created = queue_research(
                conn,
                item["project_id"],
                item["command"],
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
            if task is not None:
                task["full_name"] = item["full_name"]
                task["created"] = created
            tasks.append(task or {})
            jobs.append(
                {
                    "job": job,
                    "created": created,
                    "task_id": task_id,
                    "project_id": item["project_id"],
                    "full_name": item["full_name"],
                }
            )
            queued.append(
                {
                    "job_id": job["id"] if job else None,
                    "project_id": item["project_id"],
                    "full_name": item["full_name"],
                    "language": item.get("language"),
                    "created": created,
                    "preset": item["command_meta"].get("preset"),
                    "binary": item["command_meta"].get("binary"),
                    "prompt_source": item["command_meta"].get("prompt_source"),
                    "notes": item["command_meta"].get("notes"),
                    "command_preview": item["command_meta"].get("command_preview"),
                }
            )
        run = row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
    return {"run": run, "tasks": tasks, "jobs": jobs, "queued": queued, "ignored": ignored}


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
            if job.get("error_step"):
                summary += f"\nFailed step: {job['error_step']}"
            if job.get("error"):
                summary += f"\nError: {str(job['error'])[:800]}"
            if status == "done" and job.get("report"):
                summary += (
                    "\nA research report was saved. Read get_job_status for the preview "
                    "and tell the user how to open the job log."
                )
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
                SELECT rt.*, p.full_name, j.error AS job_error, j.error_step AS job_error_step,
                       j.status AS job_status
                FROM run_tasks rt
                JOIN projects p ON p.id = rt.project_id
                LEFT JOIN jobs j ON j.id = rt.job_id
                WHERE rt.run_id = ?
                ORDER BY rt.id
                """,
                (run_id,),
            ).fetchall()
            failed = 0
            lines = [f"Research batch run #{run_id} finished."]
            for row in tasks:
                item = dict(row)
                task_status = item.get("job_status") or item["status"]
                if task_status == "error":
                    failed += 1
                line = (
                    f"- {item['full_name']}: {task_status}"
                    + (f" (job {item['job_id']})" if item.get("job_id") else "")
                )
                if item.get("job_error_step"):
                    line += f" step={item['job_error_step']}"
                if item.get("job_error"):
                    line += f" error={str(item['job_error'])[:400]}"
                lines.append(line)
            if failed:
                lines.append(
                    "Open the job log in the UI. The log lines prefixed with [step:] "
                    "show how far the worker got."
                )
            summary = "\n".join(lines)
            now = utcnow()
            run_status = "error" if failed else "done"
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (run_status, now, run_id),
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
            """
            SELECT rt.*, p.full_name, j.error AS job_error, j.error_step AS job_error_step,
                   j.status AS job_status,
                   CASE WHEN j.report IS NOT NULL AND length(j.report) > 0 THEN 1 ELSE 0 END AS has_report
            FROM run_tasks rt
            LEFT JOIN projects p ON p.id = rt.project_id
            LEFT JOIN jobs j ON j.id = rt.job_id
            WHERE rt.run_id = ?
            ORDER BY rt.id
            """,
            (run_id,),
        ).fetchall()
    run["tasks"] = [row_to_dict(t) for t in tasks if row_to_dict(t)]
    if isinstance(run.get("plan"), str):
        try:
            run["plan"] = json.loads(run["plan"] or "{}")
        except json.JSONDecodeError:
            run["plan"] = {}
    return run
