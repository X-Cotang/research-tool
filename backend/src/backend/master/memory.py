"""Working memory: a snapshot rebuilt from SQLite on every Master turn."""

from __future__ import annotations

from typing import Any

from backend.core.db import db, get_setting, row_to_dict


def build_working_memory() -> dict[str, Any]:
    with db() as conn:
        jobs = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT j.id, j.project_id, j.status, j.run_id, j.conversation_id,
                       j.created_at, j.finished_at, j.error, p.full_name, p.language
                FROM jobs j
                JOIN projects p ON p.id = j.project_id
                WHERE j.status IN ('queued', 'running')
                   OR j.id IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 8)
                ORDER BY j.id DESC
                LIMIT 12
                """
            ).fetchall()
            if row_to_dict(r)
        ]
        runs = [
            row_to_dict(r)
            for r in conn.execute(
                """
                SELECT id, status, conversation_id, created_at, finished_at
                FROM runs ORDER BY id DESC LIMIT 6
                """
            ).fetchall()
            if row_to_dict(r)
        ]
        finding_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS c FROM findings GROUP BY status
            """
        ).fetchall()
        languages = [
            r["language"]
            for r in conn.execute(
                """
                SELECT DISTINCT language FROM projects
                WHERE language IS NOT NULL AND language != ''
                  AND research_status IN ('queued', 'running', 'done')
                ORDER BY researched_at DESC
                LIMIT 6
                """
            ).fetchall()
            if r["language"]
        ]
    counts = {row["status"]: row["c"] for row in finding_rows}
    active_jobs = [j for j in jobs if j and j.get("status") in {"queued", "running"}]
    return {
        "last_org": get_setting("last_viewed_org", ""),
        "active_jobs": active_jobs,
        "recent_jobs": jobs,
        "runs": runs,
        "finding_counts": counts,
        "languages": languages,
    }


def render_working_memory(snapshot: dict[str, Any] | None = None) -> str:
    snap = snapshot or build_working_memory()
    lines = ["# Working memory", ""]
    org = snap.get("last_org") or "(none)"
    lines.append(f"- Last org: {org}")
    counts = snap.get("finding_counts") or {}
    if counts:
        bits = ", ".join(f"{k}={v}" for k, v in counts.items())
        lines.append(f"- Findings: {bits}")
    else:
        lines.append("- Findings: none parsed")
    active = snap.get("active_jobs") or []
    if active:
        lines.append("- Active jobs:")
        for job in active:
            lines.append(
                f"  - job {job.get('id')} {job.get('status')} {job.get('full_name')} "
                f"({job.get('language') or 'unknown'})"
            )
    else:
        lines.append("- Active jobs: none")
    runs = [r for r in (snap.get("runs") or []) if r and r.get("status") in {"queued", "running"}]
    if runs:
        lines.append("- Open runs: " + ", ".join(f"#{r['id']} {r['status']}" for r in runs))
    langs = snap.get("languages") or []
    if langs:
        lines.append("- Recent languages: " + ", ".join(langs))
    return "\n".join(lines)
