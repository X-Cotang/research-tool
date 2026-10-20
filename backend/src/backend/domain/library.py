from __future__ import annotations

import shutil
from pathlib import Path

from backend.core.config import RESEARCH_DIR
from backend.core.db import db, row_to_dict, utcnow

NOTE_FILES = ("RESEARCH_NOTES.md", "FINDINGS.md")


def recover_stale_jobs() -> None:
    now = utcnow()
    with db() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'error',
                error = 'Interrupted when the server restarted.',
                finished_at = COALESCE(finished_at, ?)
            WHERE status IN ('queued', 'running')
            """,
            (now,),
        )
        conn.execute(
            """
            UPDATE projects
            SET research_status = CASE
                WHEN local_path IS NOT NULL AND local_path != '' THEN 'cloned'
                ELSE 'idle'
            END
            WHERE research_status IN ('queued', 'running')
            """
        )


def iter_local_clones() -> list[Path]:
    if not RESEARCH_DIR.exists():
        return []
    clones: list[Path] = []
    for org_dir in sorted(RESEARCH_DIR.iterdir()):
        if not org_dir.is_dir() or org_dir.name.startswith("."):
            continue
        for repo_dir in sorted(org_dir.iterdir()):
            if repo_dir.is_dir() and (repo_dir / ".git").exists():
                clones.append(repo_dir)
    return clones


def has_research_output(path: Path) -> bool:
    return any((path / name).exists() for name in NOTE_FILES)


def sync_research_dir() -> None:
    now = utcnow()
    for dest in iter_local_clones():
        org_login = dest.parent.name
        name = dest.name
        full_name = f"{org_login}/{name}"
        researched = has_research_output(dest)
        notes = next((dest / name for name in NOTE_FILES if (dest / name).exists()), None)
        report = None
        if notes:
            try:
                report = notes.read_text(encoding="utf-8", errors="replace")
            except OSError:
                report = None
        with db() as conn:
            conn.execute(
                """
                INSERT INTO organizations (login, name, html_url, scanned_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(login) DO UPDATE SET html_url = excluded.html_url
                """,
                (org_login, org_login, f"https://github.com/{org_login}", now),
            )
            org_id = conn.execute(
                "SELECT id FROM organizations WHERE login = ?", (org_login,)
            ).fetchone()["id"]
            existing = conn.execute(
                "SELECT research_status FROM projects WHERE full_name = ?", (full_name,)
            ).fetchone()
            if existing and existing["research_status"] in {"queued", "running"}:
                conn.execute(
                    "UPDATE projects SET local_path = ? WHERE full_name = ?",
                    (str(dest), full_name),
                )
                continue
            status = "done" if researched else "cloned"
            conn.execute(
                """
                INSERT INTO projects (
                    org_id, full_name, name, html_url, clone_url, description,
                    language, languages, topics, local_path, research_status,
                    last_report, researched_at
                ) VALUES (?, ?, ?, ?, ?, '', '', '{}', '[]', ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    local_path = excluded.local_path,
                    research_status = CASE
                        WHEN projects.research_status IN ('queued', 'running') THEN projects.research_status
                        ELSE excluded.research_status
                    END,
                    last_report = COALESCE(excluded.last_report, projects.last_report),
                    researched_at = COALESCE(excluded.researched_at, projects.researched_at)
                """,
                (
                    org_id,
                    full_name,
                    name,
                    f"https://github.com/{full_name}",
                    f"https://github.com/{full_name}.git",
                    str(dest),
                    status,
                    report,
                    now if researched else None,
                ),
            )


def _enrich_library_item(item: dict) -> dict:
    path = Path(item["local_path"]) if item.get("local_path") else None
    on_disk = bool(path and path.exists())
    researched = (
        item.get("research_status") == "done"
        or bool((item.get("last_report") or "").strip())
        or (path is not None and has_research_output(path))
    )
    reported = bool(item.get("reported"))
    false_positive = bool(item.get("false_positive"))
    # Soft-deleted: clone removed but research metadata retained.
    clone_removed = researched and not on_disk and item.get("research_status") not in {
        "queued",
        "running",
    }
    in_history = reported or false_positive or clone_removed
    item["on_disk"] = on_disk
    item["researched"] = researched
    item["reported"] = reported
    item["false_positive"] = false_positive
    item["clone_removed"] = clone_removed
    item["in_history"] = in_history
    return item


def list_library(*, view: str = "all") -> dict:
    """List library projects, optionally filtered to Active or History.

    Active = still in the working queue (on disk / in flight, not closed out).
    History = reported, false positive, or clone-removed-with-report-kept.
    """
    sync_research_dir()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM projects
            WHERE (local_path IS NOT NULL AND local_path != '')
               OR research_status IN ('cloned', 'done', 'running', 'queued', 'error')
               OR COALESCE(reported, 0) = 1
               OR COALESCE(false_positive, 0) = 1
               OR (last_report IS NOT NULL AND length(trim(last_report)) > 0)
            ORDER BY
                CASE
                    WHEN research_status = 'running' THEN 0
                    WHEN research_status = 'queued' THEN 1
                    WHEN research_status = 'done'
                         AND COALESCE(reported, 0) = 0
                         AND COALESCE(false_positive, 0) = 0 THEN 2
                    WHEN research_status = 'error' THEN 3
                    WHEN COALESCE(reported, 0) = 1
                         OR COALESCE(false_positive, 0) = 1 THEN 5
                    ELSE 4
                END,
                researched_at DESC,
                full_name
            """
        ).fetchall()
    items = []
    for row in rows:
        item = row_to_dict(row)
        if not item:
            continue
        item = _enrich_library_item(item)
        if item["on_disk"] or item["researched"] or item["reported"] or item["false_positive"]:
            items.append(item)

    active = [p for p in items if not p["in_history"]]
    history = [p for p in items if p["in_history"]]
    if view == "active":
        projects = active
    elif view == "history":
        projects = history
    else:
        projects = items
    return {
        "projects": projects,
        "view": view,
        "counts": {
            "all": len(items),
            "active": len(active),
            "history": len(history),
        },
    }


def _safe_clone_path(local_path: str | None) -> Path | None:
    if not local_path:
        return None
    try:
        path = Path(local_path).resolve()
    except OSError:
        return None
    root = RESEARCH_DIR.resolve()
    if path == root or root not in path.parents:
        return None
    return path


def _resolve_clone(project: dict) -> Path | None:
    clone = _safe_clone_path(project.get("local_path"))
    if clone is None and project.get("full_name"):
        clone = _safe_clone_path(str(RESEARCH_DIR / project["full_name"]))
    return clone


def _remove_clone_dir(clone: Path | None) -> str | None:
    if not clone or not clone.exists():
        return str(clone) if clone else None
    shutil.rmtree(clone)
    parent = clone.parent
    try:
        if parent.is_dir() and parent != RESEARCH_DIR.resolve() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
    return str(clone)


def _read_notes_report(clone: Path | None) -> str | None:
    if not clone or not clone.is_dir():
        return None
    for name in NOTE_FILES:
        notes = clone / name
        if not notes.is_file():
            continue
        try:
            text = notes.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            return text
    return None


def delete_project(project_id: int, *, mode: str = "full") -> dict | None:
    """Delete a project clone and optionally wipe library data.

    Modes:
    - ``clone``: remove the on-disk repository but keep the project row,
      reports, and jobs (essential research metadata).
    - ``full``: remove jobs, the project row, and the local clone.
    """
    if mode not in {"clone", "full"}:
        raise ValueError(f"Unknown delete mode: {mode}")

    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        if not project:
            return None

        clone = _resolve_clone(project)

        if mode == "clone":
            report = (project.get("last_report") or "").strip() or _read_notes_report(clone)
            researched_at = project.get("researched_at")
            status = project.get("research_status") or "idle"
            if report:
                status = "done"
                researched_at = researched_at or utcnow()
            elif status in {"cloned", "queued", "running", "error"}:
                status = "idle"
            conn.execute(
                """
                UPDATE projects
                SET local_path = NULL,
                    research_status = ?,
                    last_report = COALESCE(?, last_report),
                    researched_at = ?
                WHERE id = ?
                """,
                (status, report or None, researched_at, project_id),
            )
            updated = row_to_dict(
                conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            )
            if updated:
                project = updated
        else:
            conn.execute("DELETE FROM jobs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    project["delete_mode"] = mode
    project["deleted_path"] = _remove_clone_dir(clone)
    return project
