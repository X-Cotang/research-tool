"""Resolve repository names to stored projects without guessing ids."""

from __future__ import annotations

import re
from typing import Any

from backend.core.db import db, row_to_dict

_GITHUB_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/", re.IGNORECASE)


def normalize_repo_name(value: str) -> str:
    text = (value or "").strip().strip("/")
    text = _GITHUB_RE.sub("", text)
    if text.endswith(".git"):
        text = text[:-4]
    return text.strip()


def _candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "full_name": row.get("full_name"),
        "language": row.get("language"),
        "stars": row.get("stars"),
        "description": (row.get("description") or "")[:180],
        "research_status": row.get("research_status"),
        "skipped": bool(row.get("skipped")),
        "reported": bool(row.get("reported")),
        "false_positive": bool(row.get("false_positive")),
    }


def find_projects(conn, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    name = normalize_repo_name(query)
    if not name:
        return []
    if name.isdigit():
        row = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (int(name),)).fetchone()
        )
        return [_candidate(row)] if row else []

    exact = row_to_dict(
        conn.execute(
            "SELECT * FROM projects WHERE lower(full_name) = lower(?)",
            (name,),
        ).fetchone()
    )
    if exact:
        return [_candidate(exact)]

    rows = conn.execute(
        """
        SELECT * FROM projects
        WHERE lower(name) = lower(?)
           OR lower(full_name) = lower(?)
           OR lower(full_name) LIKE lower(?)
        ORDER BY stars DESC
        LIMIT ?
        """,
        (name, name, f"%/{name}", limit),
    ).fetchall()
    found = [_candidate(row_to_dict(row) or {}) for row in rows if row_to_dict(row)]
    if found:
        return found

    like = f"%{name}%"
    rows = conn.execute(
        """
        SELECT * FROM projects
        WHERE lower(full_name) LIKE lower(?) OR lower(description) LIKE lower(?)
        ORDER BY stars DESC
        LIMIT ?
        """,
        (like, like, limit),
    ).fetchall()
    return [_candidate(row_to_dict(row) or {}) for row in rows if row_to_dict(row)]


def resolve_project_query(names: list[str]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with db() as conn:
        for raw in names:
            text = str(raw or "").strip()
            if not text:
                continue
            found = find_projects(conn, text)
            if len(found) == 1:
                matches.append({"query": text, **found[0]})
            elif not found:
                errors.append({"query": text, "error": "No stored project matches this name."})
            else:
                errors.append(
                    {
                        "query": text,
                        "error": "Name is ambiguous. Pass the full owner/repo name.",
                        "candidates": found,
                    }
                )
    return {"matches": matches, "errors": errors}


def _as_spec(item: Any) -> dict[str, Any]:
    if isinstance(item, int):
        return {"project_id": item}
    if isinstance(item, str):
        text = item.strip()
        if text.isdigit():
            return {"project_id": int(text)}
        return {"full_name": text}
    if isinstance(item, dict):
        spec = dict(item)
        if spec.get("name") and not spec.get("full_name"):
            spec["full_name"] = spec["name"]
        return spec
    return {}


def resolve_research_targets(
    project_ids: list[int] | None = None,
    projects: list[Any] | None = None,
    *,
    expect_full_names: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve ids and owner/repo names. Refuse the whole batch on any mismatch."""
    specs = [_as_spec(item) for item in (projects or [])]
    specs = [spec for spec in specs if spec]
    for project_id in project_ids or []:
        specs.append({"project_id": int(project_id)})

    if not specs and expect_full_names:
        specs = [{"full_name": name} for name in expect_full_names]

    if not specs:
        return {"error": "No projects were provided.", "targets": [], "errors": []}

    targets: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[int] = set()
    with db() as conn:
        for spec in specs:
            project_id = spec.get("project_id")
            full_name = normalize_repo_name(str(spec.get("full_name") or ""))
            row = None
            if project_id not in (None, ""):
                row = row_to_dict(
                    conn.execute(
                        "SELECT * FROM projects WHERE id = ?",
                        (int(project_id),),
                    ).fetchone()
                )
                if not row:
                    errors.append({"project_id": project_id, "error": "Project id was not found."})
                    continue
            if full_name:
                found = find_projects(conn, full_name)
                if len(found) != 1:
                    errors.append(
                        {
                            "full_name": full_name,
                            "error": "Could not uniquely resolve this repository.",
                            "candidates": found,
                        }
                    )
                    continue
                if row and int(row["id"]) != int(found[0]["id"]):
                    errors.append(
                        {
                            "project_id": row["id"],
                            "full_name": row.get("full_name"),
                            "expected": found[0]["full_name"],
                            "error": (
                                f"project_id {row['id']} is {row.get('full_name')}, "
                                f"not {found[0]['full_name']}."
                            ),
                        }
                    )
                    continue
                if row is None:
                    row = row_to_dict(
                        conn.execute(
                            "SELECT * FROM projects WHERE id = ?",
                            (found[0]["id"],),
                        ).fetchone()
                    )
            if not row:
                errors.append({"error": "Each target needs a project_id or full_name."})
                continue
            pid = int(row["id"])
            if pid in seen:
                continue
            seen.add(pid)
            targets.append(
                {
                    "project_id": pid,
                    "full_name": row.get("full_name"),
                    "language": row.get("language"),
                    "description": (row.get("description") or "")[:180],
                    "skipped": bool(row.get("skipped")),
                    "reported": bool(row.get("reported")),
                    "false_positive": bool(row.get("false_positive")),
                    "prompt": spec.get("prompt"),
                    "preset": spec.get("preset"),
                    "command": spec.get("command"),
                    "extra_args": spec.get("extra_args") or [],
                }
            )

        if expect_full_names:
            expected = {normalize_repo_name(name).lower() for name in expect_full_names if str(name).strip()}
            actual = {str(item["full_name"] or "").lower() for item in targets}
            missing = sorted(expected - actual)
            if missing or len(actual) != len(expected):
                errors.append(
                    {
                        "error": "Resolved projects do not match expect_full_names.",
                        "expected": sorted(expected),
                        "actual": sorted(actual),
                        "missing": missing,
                    }
                )

    if errors:
        return {
            "error": "Nothing was queued. Fix the project names and try again.",
            "targets": [],
            "errors": errors,
        }
    return {"targets": targets, "errors": []}
