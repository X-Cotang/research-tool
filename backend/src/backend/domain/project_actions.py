"""Library actions the desk UI already has, exposed for the AI Master.

Skip keeps a repository in the catalog but out of research. Dropping a clone
removes the local checkout and keeps the report. A full delete removes the
row, jobs, and checkout.
"""

from __future__ import annotations

from typing import Any

from backend.core.db import db, row_to_dict
from backend.domain.library import delete_project
from backend.domain.project_lookup import resolve_project_query


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _card(project: dict) -> dict[str, Any]:
    return {
        "id": project.get("id"),
        "full_name": project.get("full_name"),
        "language": project.get("language"),
        "stars": project.get("stars"),
        "research_status": project.get("research_status"),
        "skipped": bool(project.get("skipped")),
        "reported": bool(project.get("reported")),
        "false_positive": bool(project.get("false_positive")),
        "description": (project.get("description") or "")[:180],
        "last_job_id": project.get("last_job_id"),
    }


def list_managed_projects(
    *,
    org: str | None = None,
    query: str | None = None,
    language: str | None = None,
    research_status: str | None = None,
    min_stars: int | None = None,
    include_skipped: bool = False,
    skipped_only: bool = False,
    reported: bool | None = None,
    false_positive: bool | None = None,
    hide_researched: bool = False,
    limit: int = 40,
) -> dict[str, Any]:
    clauses = ["1 = 1"]
    params: list[Any] = []
    if org:
        clauses.append(
            "org_id IN (SELECT id FROM organizations WHERE lower(login) = lower(?))"
        )
        params.append(org.strip())
    if query:
        like = f"%{query.strip()}%"
        clauses.append("(lower(full_name) LIKE lower(?) OR lower(description) LIKE lower(?))")
        params.extend([like, like])
    if language:
        clauses.append("lower(COALESCE(language, '')) = lower(?)")
        params.append(language.strip())
    if research_status:
        clauses.append("lower(COALESCE(research_status, '')) = lower(?)")
        params.append(research_status.strip())
    if min_stars is not None:
        clauses.append("COALESCE(stars, 0) >= ?")
        params.append(int(min_stars))
    if reported is True:
        clauses.append("COALESCE(reported, 0) = 1")
    elif reported is False:
        clauses.append("COALESCE(reported, 0) = 0")
    if false_positive is True:
        clauses.append("COALESCE(false_positive, 0) = 1")
    elif false_positive is False:
        clauses.append("COALESCE(false_positive, 0) = 0")
    if hide_researched:
        clauses.append(
            """
            research_status NOT IN ('done')
            AND (last_report IS NULL OR length(trim(last_report)) = 0)
            """
        )

    cap = max(1, min(int(limit or 40), 80))
    sql = f"""
        SELECT * FROM projects
        WHERE {' AND '.join(clauses)}
        ORDER BY research_score DESC, stars DESC
        LIMIT 400
    """
    with db() as conn:
        rows = [row_to_dict(row) for row in conn.execute(sql, params).fetchall()]
    rows = [row for row in rows if row]
    hidden_skipped = 0
    visible: list[dict] = []
    for row in rows:
        skipped = bool(row.get("skipped"))
        if skipped_only and not skipped:
            continue
        if not include_skipped and not skipped_only and skipped:
            hidden_skipped += 1
            continue
        visible.append(row)
    shown = visible[:cap]
    return {
        "projects": [_card(row) for row in shown],
        "count": len(shown),
        "matched": len(visible),
        "hidden_skipped": hidden_skipped,
        "truncated": len(visible) > cap,
        "include_skipped": include_skipped or skipped_only,
        "hint": (
            "Skipped projects are omitted. Pass include_skipped=true to see them, "
            "or update_projects to skip, unskip, mark reported, or mark a false positive."
        ),
    }


def _apply_marks(
    conn,
    project_id: int,
    *,
    skipped: bool | None,
    reported: bool | None,
    false_positive: bool | None,
) -> None:
    if skipped is not None:
        conn.execute(
            "UPDATE projects SET skipped = ? WHERE id = ?",
            (1 if skipped else 0, project_id),
        )
    if reported is not None:
        flag = 1 if reported else 0
        conn.execute(
            """
            UPDATE projects
            SET reported = ?,
                false_positive = CASE WHEN ? = 1 THEN 0 ELSE false_positive END
            WHERE id = ?
            """,
            (flag, flag, project_id),
        )
    if false_positive is not None:
        flag = 1 if false_positive else 0
        conn.execute(
            """
            UPDATE projects
            SET false_positive = ?,
                reported = CASE WHEN ? = 1 THEN 0 ELSE reported END
            WHERE id = ?
            """,
            (flag, flag, project_id),
        )


def set_project_marks(
    names: Any,
    *,
    skipped: Any = None,
    reported: Any = None,
    false_positive: Any = None,
) -> dict[str, Any]:
    skip_flag = _as_bool(skipped)
    reported_flag = _as_bool(reported)
    false_flag = _as_bool(false_positive)
    if skip_flag is None and reported_flag is None and false_flag is None:
        return {
            "error": "Set skipped, reported, and/or false_positive to true or false.",
        }
    wanted = _names(names)
    if not wanted:
        return {"error": "Pass projects as owner/repo names, for example ['microsoft/graphrag']."}
    resolved = resolve_project_query(wanted)
    updated: list[dict[str, Any]] = []
    with db() as conn:
        for match in resolved.get("matches") or []:
            project_id = int(match["id"])
            active = conn.execute(
                """
                SELECT id FROM jobs
                WHERE project_id = ? AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if skip_flag is True and active:
                updated.append(
                    {
                        "full_name": match.get("full_name"),
                        "error": "A job is queued or running. Skip it after that job finishes.",
                    }
                )
                continue
            _apply_marks(
                conn,
                project_id,
                skipped=skip_flag,
                reported=reported_flag,
                false_positive=false_flag,
            )
            row = row_to_dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            )
            if row:
                updated.append(_card(row))
    return {"updated": updated, "errors": resolved.get("errors") or []}


def remove_managed_projects(names: Any, *, mode: str = "clone", confirm: bool = False) -> dict[str, Any]:
    normalized = (mode or "clone").strip().lower()
    if normalized not in {"clone", "full"}:
        return {"error": "mode must be 'clone' (drop the checkout, keep the report) or 'full'."}
    if normalized == "full" and not confirm:
        return {
            "error": (
                "Full delete removes the project, its jobs, and the local clone. "
                "Call again with confirm=true only after the user asked to delete it."
            )
        }
    wanted = _names(names)
    if not wanted:
        return {"error": "Pass projects as owner/repo names."}
    resolved = resolve_project_query(wanted)
    removed: list[dict[str, Any]] = []
    for match in resolved.get("matches") or []:
        project_id = int(match["id"])
        with db() as conn:
            active = conn.execute(
                """
                SELECT id FROM jobs
                WHERE project_id = ? AND status IN ('queued', 'running')
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if active:
            removed.append(
                {
                    "full_name": match.get("full_name"),
                    "error": "A job is queued or running. Wait until it finishes before removing it.",
                }
            )
            continue
        try:
            project = delete_project(project_id, mode=normalized)
        except ValueError as exc:
            removed.append({"full_name": match.get("full_name"), "error": str(exc)})
            continue
        if not project:
            removed.append({"full_name": match.get("full_name"), "error": "Project not found."})
            continue
        removed.append(
            {
                "full_name": project.get("full_name") or match.get("full_name"),
                "mode": normalized,
                "kept_report": bool((project.get("last_report") or "").strip()) if normalized == "clone" else False,
            }
        )
    return {"removed": removed, "errors": resolved.get("errors") or []}
