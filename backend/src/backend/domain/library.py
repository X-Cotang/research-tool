from __future__ import annotations

import shutil
from pathlib import Path

from backend.core.config import RESEARCH_DIR
from backend.core.db import db, row_to_dict, utcnow

NOTE_FILES = ("RESEARCH_NOTES.md", "FINDINGS.md")


def recover_stale_jobs() -> None:
    now = utcnow()
    notice = (
        "[step:interrupted] Server restarted while this job was queued or running. "
        "No later step output was captured.\n"
    )
    with db() as conn:
        rows = conn.execute(
            "SELECT id FROM jobs WHERE status = 'running'"
        ).fetchall()
        job_ids = [int(row["id"]) for row in rows]
        if job_ids:
            placeholders = ",".join("?" for _ in job_ids)
            conn.execute(
                f"""
                UPDATE jobs
                SET status = 'error',
                    error_step = 'interrupted',
                    error = '[interrupted] Interrupted when the server restarted.',
                    log = CASE
                        WHEN log IS NULL OR log = '' THEN ?
                        ELSE log || ?
                    END,
                    finished_at = COALESCE(finished_at, ?)
                WHERE id IN ({placeholders})
                """,
                (notice, notice, now, *job_ids),
            )
        conn.execute(
            """
            UPDATE projects
            SET research_status = 'error'
            WHERE research_status = 'running'
            """
        )
    from backend.domain.runs import on_research_job_finished

    with db() as conn:
        stuck = conn.execute(
            """
            SELECT DISTINCT j.id
            FROM jobs j
            JOIN run_tasks rt ON rt.job_id = j.id
            WHERE rt.status IN ('queued', 'running')
              AND j.status IN ('done', 'error')
            """
        ).fetchall()
    pending_ids = list(dict.fromkeys([*job_ids, *[int(row["id"]) for row in stuck]]))
    for job_id in pending_ids:
        on_research_job_finished(job_id)


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


def research_folder_summary(*, group: str = "all", limit: int = 40) -> dict:
    """Count checkouts still in the research folder.

    on_disk is a clone that has not been dropped. reported and unreported
    are split from that set. clone_removed is a library row whose checkout
    is already gone.
    """
    selected = (group or "all").strip().lower()
    if selected not in {"all", "on_disk", "unreported", "reported", "false_positive", "dropped"}:
        selected = "all"
    cap = max(1, min(int(limit or 40), 80))
    clones = iter_local_clones()
    disk_names = {f"{path.parent.name}/{path.name}".lower(): path for path in clones}
    with db() as conn:
        rows = [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT id, full_name, language, stars, research_status,
                       skipped, reported, false_positive, local_path
                FROM projects
                """
            ).fetchall()
        ]
    by_name = {
        str(row.get("full_name") or "").lower(): row
        for row in rows
        if row and row.get("full_name")
    }

    def card(full_name: str, row: dict | None, path: Path | None) -> dict:
        reported = bool(row and row.get("reported"))
        false_positive = bool(row and row.get("false_positive"))
        return {
            "id": row.get("id") if row else None,
            "full_name": row.get("full_name") if row else full_name,
            "language": row.get("language") if row else None,
            "stars": row.get("stars") if row else None,
            "research_status": row.get("research_status") if row else "untracked",
            "skipped": bool(row and row.get("skipped")),
            "reported": reported,
            "false_positive": false_positive,
            "on_disk": path is not None,
        }

    on_disk: list[dict] = []
    for key, path in sorted(disk_names.items()):
        row = by_name.get(key)
        full_name = row.get("full_name") if row else f"{path.parent.name}/{path.name}"
        on_disk.append(card(str(full_name), row, path))

    reported = [item for item in on_disk if item["reported"]]
    false_positive = [item for item in on_disk if item["false_positive"] and not item["reported"]]
    unreported = [item for item in on_disk if not item["reported"] and not item["false_positive"]]

    dropped: list[dict] = []
    for row in rows:
        if not row or not row.get("full_name"):
            continue
        if str(row["full_name"]).lower() in disk_names:
            continue
        had_clone = bool(row.get("local_path")) or row.get("research_status") in {
            "cloned",
            "done",
            "error",
        } or bool(row.get("reported")) or bool(row.get("false_positive"))
        if not had_clone:
            continue
        dropped.append(card(str(row["full_name"]), row, None))

    groups = {
        "on_disk": on_disk,
        "unreported": unreported,
        "reported": reported,
        "false_positive": false_positive,
        "dropped": dropped,
    }

    def pack(name: str) -> dict:
        items = groups[name]
        # The full on-disk list repeats the reported and unreported lists.
        show_names = selected == name or (selected == "all" and name != "on_disk")
        return {
            "count": len(items),
            "projects": items[:cap] if show_names else [],
            "truncated": len(items) > cap and show_names,
        }

    return {
        "research_dir": str(RESEARCH_DIR),
        "counts": {
            "on_disk": len(on_disk),
            "unreported": len(unreported),
            "reported": len(reported),
            "false_positive": len(false_positive),
            "dropped": len(dropped),
        },
        "on_disk": pack("on_disk"),
        "unreported": pack("unreported"),
        "reported": pack("reported"),
        "false_positive": pack("false_positive"),
        "dropped": pack("dropped"),
        "hint": (
            "on_disk is still in the research folder and has not been deleted. "
            "unreported and reported are split from that set. "
            "dropped means the checkout is gone and the library row was kept. "
            "Pass group=unreported, reported, on_disk, or dropped to list one set."
        ),
    }


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
