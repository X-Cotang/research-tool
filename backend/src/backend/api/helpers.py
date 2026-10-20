from __future__ import annotations

import json

from backend.core.db import (
    list_organizations,
    load_org_projects,
    row_to_dict,
    set_setting,
    utcnow,
)


def serialize_cursor(cursor: dict | None) -> dict | None:
    if not cursor:
        return None
    return {
        "filter_key": cursor.get("filter_key"),
        "github_page": cursor.get("github_page", 1),
        "star_ceiling": cursor.get("star_ceiling"),
        "time_ceiling": cursor.get("time_ceiling"),
        "exhausted": bool(cursor.get("exhausted")),
        "total_discovered": int(cursor.get("total_discovered") or 0),
        "can_continue": True,
        "updated_at": cursor.get("updated_at"),
    }


def upsert_org(conn, org: dict, now: str) -> int:
    conn.execute(
        """
        INSERT INTO organizations (login, name, html_url, scanned_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(login) DO UPDATE SET
            name = excluded.name,
            html_url = excluded.html_url,
            scanned_at = excluded.scanned_at
        """,
        (org["login"], org["name"], org["html_url"], now),
    )
    return conn.execute(
        "SELECT id FROM organizations WHERE login = ?", (org["login"],)
    ).fetchone()["id"]


def upsert_project(conn, org_id: int, repo: dict) -> dict:
    conn.execute(
        """
        INSERT INTO projects (
            org_id, full_name, name, html_url, clone_url, description, language,
            languages, topics, stars, forks, pushed_at, created_at, project_types,
            advisory_count, research_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(full_name) DO UPDATE SET
            description = excluded.description,
            language = excluded.language,
            languages = excluded.languages,
            topics = excluded.topics,
            stars = excluded.stars,
            forks = excluded.forks,
            pushed_at = excluded.pushed_at,
            created_at = excluded.created_at,
            project_types = excluded.project_types,
            advisory_count = excluded.advisory_count,
            research_score = excluded.research_score
        """,
        (
            org_id,
            repo["full_name"],
            repo["name"],
            repo["html_url"],
            repo["clone_url"],
            repo.get("description") or "",
            repo.get("language") or "",
            json.dumps(repo.get("languages") or {}),
            json.dumps(repo.get("topics") or []),
            repo.get("stars") or 0,
            repo.get("forks") or 0,
            repo.get("pushed_at") or "",
            repo.get("created_at") or "",
            json.dumps(repo.get("project_types") or []),
            repo.get("advisory_count"),
            repo.get("research_score") or 0,
        ),
    )
    return row_to_dict(
        conn.execute("SELECT * FROM projects WHERE full_name = ?", (repo["full_name"],)).fetchone()
    )


def serialize_org(org: dict) -> dict:
    return {
        "login": org["login"],
        "name": org.get("name") or org["login"],
        "html_url": org.get("html_url") or f"https://github.com/{org['login']}",
        "scanned_at": org.get("scanned_at"),
        "project_count": org.get("project_count"),
        "researched_count": org.get("researched_count"),
        "skipped_count": org.get("skipped_count"),
    }


def remember_org(login: str) -> None:
    if login:
        set_setting("last_viewed_org", login)


def org_catalog(conn) -> list[dict]:
    return [serialize_org(org) for org in list_organizations(conn)]
