#!/usr/bin/env python3
"""Migrate organizations, projects, jobs, scans, and on-disk research from research-tool-old."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `uv run python scripts/migrate_from_old.py` from backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_SRC = _BACKEND_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from backend.core.config import DB_PATH, RESEARCH_DIR, ROOT_DIR
from backend.core.db import init_db
from backend.domain.findings import parse_project_findings

LEGACY_TABLES = (
    "organizations",
    "projects",
    "jobs",
    "scans",
    "search_cursors",
)

def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _backup_db(path: Path) -> Path:
    backup = path.with_name(f"{path.name}.pre-migrate-{_utc_stamp()}")
    shutil.copy2(path, backup)
    return backup


def _rows_as_dicts(conn: sqlite3.Connection, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cols = _table_columns(conn, table)
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    return [{col: row[col] for col in cols} for row in rows]


def _insert_rows(
    conn: sqlite3.Connection,
    table: str,
    rows: list[dict],
    *,
    columns: list[str] | None = None,
) -> int:
    if not rows:
        return 0
    cols = columns or sorted({key for row in rows for key in row})
    placeholders = ", ".join("?" for _ in cols)
    col_sql = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
    values = [[row.get(col) for col in cols] for row in rows]
    conn.executemany(sql, values)
    return len(values)


def _clear_legacy_domain(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM findings")
    conn.execute("DELETE FROM run_tasks")
    conn.execute("DELETE FROM jobs")
    conn.execute("DELETE FROM projects")
    conn.execute("DELETE FROM organizations")
    conn.execute("DELETE FROM scans")
    conn.execute("DELETE FROM search_cursors")


def _import_legacy(conn: sqlite3.Connection, old_db: Path) -> None:
    legacy = sqlite3.connect(old_db)
    legacy.row_factory = sqlite3.Row
    try:
        for table in LEGACY_TABLES:
            target_cols = set(_table_columns(conn, table))
            legacy_cols = _table_columns(legacy, table)
            shared = [col for col in legacy_cols if col in target_cols]
            if not shared:
                continue
            rows = legacy.execute(f"SELECT {', '.join(shared)} FROM {table}").fetchall()
            if not rows:
                continue
            payload = [{col: row[col] for col in shared} for row in rows]
            _insert_rows(conn, table, payload, columns=shared)
        for key, value in legacy.execute("SELECT key, value FROM settings"):
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
    finally:
        legacy.close()


def _bump_sequences(conn: sqlite3.Connection) -> None:
    has_seq = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
    ).fetchone()
    if not has_seq:
        return
    for table in ("organizations", "projects", "jobs", "scans"):
        max_id = conn.execute(f"SELECT MAX(id) FROM {table}").fetchone()[0]
        if max_id is None:
            continue
        conn.execute(
            """
            INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET seq = excluded.seq
            """,
            (table, max_id),
        )


def _reinsert_new_only_projects(
    conn: sqlite3.Connection,
    new_only_projects: list[dict],
    old_full_names: set[str],
) -> int:
    added = 0
    for row in new_only_projects:
        full_name = row.get("full_name")
        if not full_name or full_name in old_full_names:
            continue
        org_id = row.get("org_id")
        if org_id is not None:
            exists = conn.execute(
                "SELECT 1 FROM organizations WHERE id = ?", (org_id,)
            ).fetchone()
            if not exists:
                org_id = None
        if org_id is None:
            login = full_name.split("/", 1)[0]
            org_row = conn.execute(
                "SELECT id FROM organizations WHERE login = ?", (login,)
            ).fetchone()
            if org_row:
                org_id = org_row[0]
            else:
                conn.execute(
                    """
                    INSERT INTO organizations (login, name, html_url, scanned_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (login, login, f"https://github.com/{login}", row.get("created_at")),
                )
                org_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        payload = {k: v for k, v in row.items() if k != "id"}
        payload["org_id"] = org_id
        cols = [c for c in _table_columns(conn, "projects") if c in payload and c != "id"]
        _insert_rows(conn, "projects", [{c: payload[c] for c in cols}], columns=cols)
        added += 1
    return added


def sync_research_trees(
    sources: list[Path],
    destination: Path,
    *,
    dry_run: bool,
) -> tuple[int, int]:
    """Copy org/repo trees from sources into destination (skip existing repos)."""
    copied = 0
    skipped = 0
    destination.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    for src_root in sources:
        if not src_root.is_dir():
            continue
        for org_dir in sorted(src_root.iterdir()):
            if not org_dir.is_dir() or org_dir.name.startswith("."):
                continue
            for repo_dir in sorted(org_dir.iterdir()):
                if not repo_dir.is_dir() or repo_dir.name.startswith("."):
                    continue
                full_name = f"{org_dir.name}/{repo_dir.name}"
                if full_name in seen:
                    continue
                seen.add(full_name)
                dest = destination / org_dir.name / repo_dir.name
                if dest.exists():
                    skipped += 1
                    continue
                if dry_run:
                    copied += 1
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(repo_dir, dest, symlinks=True, ignore_dangling_symlinks=True)
                copied += 1
    return copied, skipped


def rewrite_local_paths(conn: sqlite3.Connection, research_dir: Path) -> int:
    updated = 0
    rows = conn.execute("SELECT id, full_name, local_path FROM projects").fetchall()
    for project_id, full_name, local_path in rows:
        canonical = research_dir / full_name
        if not canonical.is_dir():
            continue
        target = str(canonical.resolve())
        if local_path != target:
            conn.execute(
                "UPDATE projects SET local_path = ? WHERE id = ?",
                (target, project_id),
            )
            updated += 1
    return updated


def migrate_settings_summary(conn: sqlite3.Connection) -> list[str]:
    keys = [
        row[0]
        for row in conn.execute(
            "SELECT key FROM settings ORDER BY key"
        ).fetchall()
    ]
    return keys


def run_migration(
    *,
    old_root: Path,
    old_db: Path,
    dry_run: bool,
    skip_research: bool,
    parse_findings: bool,
) -> dict:
    if not old_db.is_file():
        raise FileNotFoundError(f"Legacy database not found: {old_db}")

    init_db()

    old_conn = sqlite3.connect(old_db)
    old_conn.row_factory = sqlite3.Row
    old_full_names = {
        row[0] for row in old_conn.execute("SELECT full_name FROM projects").fetchall()
    }
    with sqlite3.connect(DB_PATH) as snap:
        new_only_projects = [
            row
            for row in _rows_as_dicts(snap, "projects")
            if row.get("full_name") not in old_full_names
        ]
    old_conn.close()

    stats: dict[str, int | list[str]] = {}
    if dry_run:
        stats["dry_run"] = 1
        stats["old_projects"] = len(old_full_names)
        stats["new_only_projects"] = len(new_only_projects)
        return stats

    backup = _backup_db(DB_PATH)
    stats["backup"] = str(backup)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        _clear_legacy_domain(conn)
        _import_legacy(conn, old_db)
        stats["reinserted_new_only"] = _reinsert_new_only_projects(
            conn, new_only_projects, old_full_names
        )
        _bump_sequences(conn)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    research_sources = [
        old_root / "research",
        ROOT_DIR.parent / "research",
    ]
    if not skip_research:
        copied, skipped = sync_research_trees(
            research_sources, RESEARCH_DIR, dry_run=False
        )
        stats["research_repos_copied"] = copied
        stats["research_repos_skipped"] = skipped

    with sqlite3.connect(DB_PATH) as conn:
        stats["local_paths_updated"] = rewrite_local_paths(conn, RESEARCH_DIR)
        for table in LEGACY_TABLES:
            stats[f"count_{table}"] = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        stats["settings_keys"] = migrate_settings_summary(conn)
        conn.commit()

    if parse_findings:
        parsed_projects = 0
        finding_rows = 0
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            project_ids = [
                r["id"]
                for r in conn.execute("SELECT id, full_name FROM projects").fetchall()
                if (RESEARCH_DIR / r["full_name"] / "RESEARCH_NOTES.md").is_file()
            ]
        for project_id in project_ids:
            result = parse_project_findings(project_id)
            parsed_projects += 1
            finding_rows += int(result.get("parsed_count") or 0)
        stats["findings_parsed_projects"] = parsed_projects
        stats["findings_parsed_rows"] = finding_rows

    return stats


def main() -> None:
    default_old_root = ROOT_DIR.parent / "research-tool-old"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old-root",
        type=Path,
        default=default_old_root,
        help=f"Legacy app root (default: {default_old_root})",
    )
    parser.add_argument(
        "--old-db",
        type=Path,
        default=None,
        help="Legacy SQLite file (default: <old-root>/data/research.db)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-research", action="store_true")
    parser.add_argument(
        "--parse-findings",
        action="store_true",
        help="Parse RESEARCH_NOTES.md into findings after migration",
    )
    args = parser.parse_args()

    old_root = args.old_root.resolve()
    old_db = (args.old_db or old_root / "data" / "research.db").resolve()

    print(f"Target DB:      {DB_PATH}")
    print(f"Research dir:   {RESEARCH_DIR}")
    print(f"Legacy root:    {old_root}")
    print(f"Legacy DB:      {old_db}")

    stats = run_migration(
        old_root=old_root,
        old_db=old_db,
        dry_run=args.dry_run,
        skip_research=args.skip_research,
        parse_findings=args.parse_findings,
    )
    print("Migration complete:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
