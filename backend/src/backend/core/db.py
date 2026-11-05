from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.core.config import DB_PATH, SKILLS_DIR, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    name TEXT,
    html_url TEXT,
    scanned_at TEXT
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL,
    full_name TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    html_url TEXT NOT NULL,
    clone_url TEXT NOT NULL,
    description TEXT,
    language TEXT,
    languages TEXT NOT NULL DEFAULT '{}',
    topics TEXT NOT NULL DEFAULT '[]',
    stars INTEGER NOT NULL DEFAULT 0,
    forks INTEGER NOT NULL DEFAULT 0,
    pushed_at TEXT,
    project_types TEXT NOT NULL DEFAULT '[]',
    advisory_count INTEGER,
    research_score REAL NOT NULL DEFAULT 0,
    research_status TEXT NOT NULL DEFAULT 'idle',
    local_path TEXT,
    last_report TEXT,
    researched_at TEXT,
    last_job_id INTEGER,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    command TEXT,
    log TEXT NOT NULL DEFAULT '',
    report TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS job_followups (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    parent_job_id INTEGER,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    job_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    org_login TEXT NOT NULL,
    org_url TEXT,
    status TEXT NOT NULL,
    error TEXT,
    result_count INTEGER NOT NULL DEFAULT 0,
    min_stars INTEGER,
    max_age_days INTEGER,
    project_types TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS search_cursors (
    org_login TEXT NOT NULL,
    filter_key TEXT NOT NULL,
    github_page INTEGER NOT NULL DEFAULT 1,
    star_ceiling INTEGER,
    exhausted INTEGER NOT NULL DEFAULT 0,
    total_discovered INTEGER NOT NULL DEFAULT 0,
    min_stars INTEGER,
    max_age_days INTEGER,
    project_types TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (org_login, filter_key)
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    language TEXT,
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'builtin',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    language TEXT,
    vuln_class TEXT,
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    plan TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS run_tasks (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    job_id INTEGER,
    skill_slug TEXT,
    prompt_slug TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    created_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id),
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    job_id INTEGER,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    cwe TEXT,
    file_path TEXT,
    line_start INTEGER,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate',
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    run_id INTEGER,
    job_id INTEGER,
    project_id INTEGER,
    conversation_id INTEGER,
    language TEXT,
    summary TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY,
    domain TEXT NOT NULL,
    cue TEXT NOT NULL,
    lesson TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'low',
    status TEXT NOT NULL DEFAULT 'active',
    job_id INTEGER,
    run_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS harness_components (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    parent_id INTEGER,
    note TEXT,
    created_at TEXT NOT NULL
);
"""

PROJECT_COLUMNS = {
    "languages": "TEXT NOT NULL DEFAULT '{}'",
    "last_report": "TEXT",
    "researched_at": "TEXT",
    "last_job_id": "INTEGER",
    "cli_session_id": "TEXT",
    "skipped": "INTEGER NOT NULL DEFAULT 0",
    "reported": "INTEGER NOT NULL DEFAULT 0",
    "false_positive": "INTEGER NOT NULL DEFAULT 0",
    "created_at": "TEXT",
}

JOB_COLUMNS = {
    "command": "TEXT",
    "kind": "TEXT NOT NULL DEFAULT 'research'",
    "portal_url": "TEXT",
    "run_id": "INTEGER",
    "conversation_id": "INTEGER",
    "error_step": "TEXT",
    "cli_session_id": "TEXT",
    "cli_activity": "TEXT",
}

SCAN_COLUMNS = {
    "org_url": "TEXT",
    "min_stars": "INTEGER",
    "max_age_days": "INTEGER",
    "project_types": "TEXT",
    "mode": "TEXT",
    "added_count": "INTEGER",
    "created_within_days": "INTEGER",
    "sort_by": "TEXT",
}

CURSOR_COLUMNS = {
    "time_ceiling": "TEXT",
}

BUILTIN_SKILLS: list[dict[str, str]] = [
    {
        "slug": "python",
        "name": "Python security review",
        "language": "python",
        "description": "Focus on pickle, template injection, SSRF, and auth bypass in Python web apps.",
        "content": "Review Python code for deserialization, SSTI, SQLi, path traversal, and unsafe subprocess usage.",
    },
    {
        "slug": "javascript",
        "name": "JavaScript / Node review",
        "language": "javascript",
        "description": "Express/Next.js prototype pollution, XSS, SSRF, and JWT issues.",
        "content": "Review JS/TS for prototype pollution, XSS sinks, open redirects, SSRF, and weak crypto.",
    },
    {
        "slug": "go",
        "name": "Go security review",
        "language": "go",
        "description": "Race conditions, unsafe SQL, path traversal, and TLS misconfig in Go services.",
        "content": "Review Go for SQL injection, path traversal, SSRF, authz gaps, and unsafe concurrency.",
    },
    {
        "slug": "java",
        "name": "Java security review",
        "language": "java",
        "description": "Deserialization, XXE, Spring misconfig, and injection in JVM stacks.",
        "content": "Review Java for deserialization gadgets, XXE, EL injection, and auth bypass.",
    },
    {
        "slug": "csharp",
        "name": "C# / .NET review",
        "language": "csharp",
        "description": "Deserialization, LDAP injection, and ASP.NET misconfiguration.",
        "content": "Review C# for unsafe deserialization, SQLi, path traversal, and auth issues.",
    },
]

BUILTIN_PROMPTS: list[dict[str, str]] = [
    {
        "slug": "general-rce",
        "name": "General RCE hunt",
        "language": None,
        "vuln_class": "rce",
        "description": "Broad remote code execution and dangerous sink review.",
        "content": (
            "Hunt for remote code execution: command execution, unsafe eval, "
            "deserialization, template injection, and unsafe file operations."
        ),
    },
    {
        "slug": "ssrf-sqli",
        "name": "SSRF and SQLi",
        "language": None,
        "vuln_class": "injection",
        "description": "Server-side request forgery and SQL injection focus.",
        "content": "Prioritize SSRF in URL fetchers and SQL/NoSQL injection in data access layers.",
    },
    {
        "slug": "auth-bypass",
        "name": "Authentication bypass",
        "language": None,
        "vuln_class": "auth",
        "description": "Session, JWT, and access-control review.",
        "content": "Review authentication, session handling, JWT validation, and authorization checks.",
    },
]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _parse_skill_md(path: Path) -> dict[str, str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip().lower()] = val.strip()
            body = parts[2].strip()
    slug = meta.get("slug") or path.parent.name
    name = meta.get("name") or slug
    language = meta.get("language") or path.parent.name
    description = body.splitlines()[0][:240] if body else name
    return {
        "slug": slug,
        "name": name,
        "language": language,
        "description": description,
        "content": body or name,
    }


def _sync_skills_from_disk(conn: sqlite3.Connection) -> None:
    if not SKILLS_DIR.is_dir():
        return
    now = utcnow()
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        item = _parse_skill_md(skill_md)
        if not item:
            continue
        existing = conn.execute(
            "SELECT id FROM skills WHERE slug = ?", (item["slug"],)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO skills (slug, name, language, description, content, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'disk', ?, ?)
            """,
            (
                item["slug"],
                item["name"],
                item.get("language"),
                item["description"],
                item["content"],
                now,
                now,
            ),
        )


def _seed_builtin_content(conn: sqlite3.Connection) -> None:
    skill_count = conn.execute("SELECT COUNT(*) AS c FROM skills").fetchone()["c"]
    if skill_count == 0:
        now = utcnow()
        for item in BUILTIN_SKILLS:
            conn.execute(
                """
                INSERT INTO skills (slug, name, language, description, content, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'builtin', ?, ?)
                """,
                (
                    item["slug"],
                    item["name"],
                    item.get("language"),
                    item["description"],
                    item["content"],
                    now,
                    now,
                ),
            )
    _sync_skills_from_disk(conn)
    prompt_count = conn.execute("SELECT COUNT(*) AS c FROM prompts").fetchone()["c"]
    if prompt_count == 0:
        now = utcnow()
        for item in BUILTIN_PROMPTS:
            conn.execute(
                """
                INSERT INTO prompts (slug, name, language, vuln_class, description, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["slug"],
                    item["name"],
                    item.get("language"),
                    item.get("vuln_class"),
                    item["description"],
                    item["content"],
                    now,
                    now,
                ),
            )


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn, "projects", PROJECT_COLUMNS)
        _ensure_columns(conn, "jobs", JOB_COLUMNS)
        _ensure_columns(conn, "scans", SCAN_COLUMNS)
        _ensure_columns(conn, "search_cursors", CURSOR_COLUMNS)
        _seed_builtin_content(conn)
        from backend.master.harness import seed_harness

        seed_harness(conn)


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key in ("topics", "project_types"):
        if key in item and isinstance(item[key], str):
            try:
                item[key] = json.loads(item[key] or "[]")
            except json.JSONDecodeError:
                item[key] = []
    if "languages" in item and isinstance(item["languages"], str):
        try:
            item["languages"] = json.loads(item["languages"] or "{}")
        except json.JSONDecodeError:
            item["languages"] = {}
    if "skipped" in item:
        item["skipped"] = bool(item["skipped"])
    if "reported" in item:
        item["reported"] = bool(item["reported"])
    if "false_positive" in item:
        item["false_positive"] = bool(item["false_positive"])
    return item


def list_organizations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            o.id,
            o.login,
            o.name,
            o.html_url,
            o.scanned_at,
            COUNT(p.id) AS project_count,
            SUM(CASE WHEN p.research_status = 'done' THEN 1 ELSE 0 END) AS researched_count,
            SUM(CASE WHEN COALESCE(p.skipped, 0) = 1 THEN 1 ELSE 0 END) AS skipped_count
        FROM organizations o
        LEFT JOIN projects p ON p.org_id = o.id
        GROUP BY o.id
        HAVING project_count > 0
        ORDER BY COALESCE(o.scanned_at, '') DESC, o.login
        """
    ).fetchall()
    orgs = []
    for row in rows:
        item = dict(row)
        item["project_count"] = int(item.get("project_count") or 0)
        item["researched_count"] = int(item.get("researched_count") or 0)
        item["skipped_count"] = int(item.get("skipped_count") or 0)
        orgs.append(item)
    return orgs


def load_org_projects(conn: sqlite3.Connection, login: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    org_row = conn.execute(
        "SELECT * FROM organizations WHERE login = ?", (login,)
    ).fetchone()
    if not org_row:
        return None, []
    rows = conn.execute(
        """
        SELECT * FROM projects
        WHERE org_id = ?
        ORDER BY research_score DESC, stars DESC
        """,
        (org_row["id"],),
    ).fetchall()
    return row_to_dict(org_row), [row_to_dict(row) for row in rows]


def make_filter_key(
    min_stars: int,
    max_age_days: int,
    project_types: list[str],
    created_within_days: int = 0,
    sort_by: str = "updated",
) -> str:
    types = ",".join(sorted(project_types)) if project_types else "any"
    sort = sort_by if sort_by in {"stars", "updated", "created"} else "updated"
    return (
        f"stars>={min_stars}|pushed<={max_age_days}|created<={created_within_days}"
        f"|sort={sort}|types={types}"
    )


def known_full_names(conn: sqlite3.Connection, org_login: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT p.full_name
        FROM projects p
        JOIN organizations o ON o.id = p.org_id
        WHERE o.login = ?
        """,
        (org_login,),
    ).fetchall()
    return {row["full_name"] for row in rows}


def get_search_cursor(conn: sqlite3.Connection, org_login: str, filter_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM search_cursors
        WHERE org_login = ? AND filter_key = ?
        """,
        (org_login, filter_key),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["exhausted"] = bool(item.get("exhausted"))
    return item


def upsert_search_cursor(
    conn: sqlite3.Connection,
    *,
    org_login: str,
    filter_key: str,
    github_page: int,
    star_ceiling: int | None,
    exhausted: bool,
    total_discovered: int,
    min_stars: int,
    max_age_days: int,
    project_types: list[str],
    time_ceiling: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    conn.execute(
        """
        INSERT INTO search_cursors (
            org_login, filter_key, github_page, star_ceiling, exhausted,
            total_discovered, min_stars, max_age_days, project_types, time_ceiling, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(org_login, filter_key) DO UPDATE SET
            github_page = excluded.github_page,
            star_ceiling = excluded.star_ceiling,
            exhausted = excluded.exhausted,
            total_discovered = excluded.total_discovered,
            min_stars = excluded.min_stars,
            max_age_days = excluded.max_age_days,
            project_types = excluded.project_types,
            time_ceiling = excluded.time_ceiling,
            updated_at = excluded.updated_at
        """,
        (
            org_login,
            filter_key,
            github_page,
            star_ceiling,
            1 if exhausted else 0,
            total_discovered,
            min_stars,
            max_age_days,
            json.dumps(project_types),
            time_ceiling,
            now,
        ),
    )
    return get_search_cursor(conn, org_login, filter_key) or {}


def reset_search_cursor(conn: sqlite3.Connection, org_login: str, filter_key: str) -> None:
    conn.execute(
        "DELETE FROM search_cursors WHERE org_login = ? AND filter_key = ?",
        (org_login, filter_key),
    )
