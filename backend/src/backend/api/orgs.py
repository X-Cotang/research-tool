from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from backend.api.helpers import org_catalog, remember_org, serialize_cursor, serialize_org, upsert_org, upsert_project
from backend.core.db import (
    db,
    get_search_cursor,
    get_setting,
    known_full_names,
    load_org_projects,
    make_filter_key,
    reset_search_cursor,
    row_to_dict,
    upsert_search_cursor,
    utcnow,
)
from backend.domain.jobs import queue_research
from backend.domain.research import run_research_job, saved_research_command
from backend.domain.github_client import (
    GitHubError,
    advisory_count,
    get_owner,
    get_repo,
    parse_org_input,
    parse_repo_input,
    repo_languages,
    sanitize_search_cursor,
    search_org_repos,
)
from backend.domain.library import sync_research_dir
from backend.domain.scoring import apply_filters, classify_project, score_repo

router = APIRouter()


class ScanRequest(BaseModel):
    org_url: str
    min_stars: int = Field(default=0, ge=0, le=100000)
    max_age_days: int = Field(default=180, ge=1, le=3650)
    created_within_days: int = Field(default=90, ge=0, le=3650)
    sort_by: str = Field(default="created")
    project_types: list[str] = Field(default_factory=lambda: ["web", "api"])
    max_results: int = Field(default=40, ge=5, le=200)
    mode: str = Field(default="fresh")


class RepoResearchRequest(BaseModel):
    repo_url: str = Field(min_length=3, max_length=500)
    command: str | None = Field(default=None, max_length=32000)


@router.get("/latest")
def latest() -> dict:
    sync_research_dir()
    remembered = get_setting("last_viewed_org")
    with db() as conn:
        orgs = org_catalog(conn)
        org = None
        projects: list[dict] = []
        if remembered:
            org, projects = load_org_projects(conn, remembered)
        if not org:
            org = row_to_dict(
                conn.execute("SELECT * FROM organizations ORDER BY scanned_at DESC LIMIT 1").fetchone()
            )
            if org:
                org, projects = load_org_projects(conn, org["login"])
        scans = conn.execute(
            "SELECT * FROM scans ORDER BY id DESC LIMIT 12"
        ).fetchall()
    return {
        "organization": serialize_org(org) if org else None,
        "projects": projects,
        "organizations": orgs,
        "scans": [row_to_dict(row) for row in scans],
    }



@router.get("/orgs")
def list_orgs() -> dict:
    with db() as conn:
        orgs = org_catalog(conn)
    return {"organizations": orgs}



@router.get("/scans")
def list_scans() -> dict:
    with db() as conn:
        rows = conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 30").fetchall()
    return {"scans": [row_to_dict(row) for row in rows]}



@router.post("/scan")
async def scan(body: ScanRequest) -> dict:
    mode = (body.mode or "fresh").strip().lower()
    if mode not in {"fresh", "continue"}:
        raise HTTPException(status_code=400, detail="mode must be fresh or continue")

    try:
        login = parse_org_input(body.org_url)
    except GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Empty / unknown types => filter-free (keep any non-docs repo).
    wanted = [item for item in body.project_types if item in {"web", "api"}]
    sort_by = (body.sort_by or "created").strip().lower()
    if sort_by not in {"stars", "updated", "created"}:
        raise HTTPException(status_code=400, detail="sort_by must be stars, updated, or created")
    created_within = body.created_within_days
    filter_key = make_filter_key(
        body.min_stars,
        body.max_age_days,
        wanted,
        created_within_days=created_within,
        sort_by=sort_by,
    )

    async with httpx.AsyncClient(timeout=45) as client:
        try:
            org = await get_owner(client, login)
        except GitHubError as exc:
            raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

        with db() as conn:
            if mode == "fresh":
                reset_search_cursor(conn, org["login"], filter_key)
                cursor = None
            else:
                cursor = get_search_cursor(conn, org["login"], filter_key)
            exclude = known_full_names(conn, org["login"])
            previous_total = int((cursor or {}).get("total_discovered") or 0)

        start_page = int((cursor or {}).get("github_page") or 1)
        star_ceiling = (cursor or {}).get("star_ceiling")
        time_ceiling = (cursor or {}).get("time_ceiling")
        cursor_reset = False
        if cursor:
            start_page, star_ceiling, time_ceiling, cursor_reset = sanitize_search_cursor(
                sort=sort_by,
                min_stars=body.min_stars,
                max_age_days=body.max_age_days,
                created_within_days=created_within,
                star_ceiling=star_ceiling,
                time_ceiling=time_ceiling,
                github_page=start_page,
            )
        # Even when older-band discovery is exhausted, continue mode still runs a
        # newest-head catch-up so brand-new org repos can appear.
        walk_exhausted = bool(cursor and cursor.get("exhausted") and not cursor_reset)

        # Keep requesting GitHub pages/bands until we have enough filtered matches
        # or the search truly runs out — avoids false exhaustion when pages are
        # mostly already-saved or docs/courses.
        need = body.max_results
        filtered: list[dict] = []
        known = set(exclude)
        # Large orgs (microsoft etc.) need a deeper page budget once many repos are known.
        if len(known) > 400:
            pages_budget = 120
        elif len(known) > 200:
            pages_budget = 90
        elif len(known) > 80:
            pages_budget = 70
        elif len(known) > 40:
            pages_budget = 50
        else:
            pages_budget = 35
        batch = None
        skipped_docs_total = 0
        catchup_count = 0
        catchup_query = ""
        walk_star_ceiling = star_ceiling
        walk_time_ceiling = time_ceiling
        walk_page = start_page
        # Filter-free walks collect more raw hits per page (no type attrition).
        collect_mult = 2 if not wanted else 4
        try:
            # Catch-up: always re-check the newest head of the window so brand-new
            # repos appear even after Load More has walked into older time bands.
            if mode == "continue" and sort_by in {"created", "updated"} and need > 0:
                catchup = await search_org_repos(
                    client,
                    org["login"],
                    min_stars=body.min_stars,
                    max_age_days=body.max_age_days,
                    target_new=max(need * 2, 40),
                    kind=org["kind"],
                    exclude=known,
                    start_page=1,
                    star_ceiling=None,
                    time_ceiling=None,
                    max_pages=8,
                    created_within_days=created_within,
                    sort=sort_by,
                )
                catchup_query = catchup.query or ""
                skipped_docs_total += int(catchup.skipped_docs or 0)
                pages_budget -= catchup.pages_fetched
                for repo in catchup.repos:
                    known.add(repo["full_name"])
                chunk = apply_filters(
                    catchup.repos, wanted, body.max_age_days, created_within
                )
                if chunk:
                    filtered.extend(chunk)
                    catchup_count = len(chunk)

            while (
                not walk_exhausted
                and len(filtered) < need
                and pages_budget > 0
            ):
                batch = await search_org_repos(
                    client,
                    org["login"],
                    min_stars=body.min_stars,
                    max_age_days=body.max_age_days,
                    target_new=max((need - len(filtered)) * collect_mult, 40),
                    kind=org["kind"],
                    exclude=known,
                    start_page=walk_page,
                    star_ceiling=walk_star_ceiling,
                    time_ceiling=walk_time_ceiling,
                    max_pages=min(20, pages_budget),
                    created_within_days=created_within,
                    sort=sort_by,
                )
                skipped_docs_total += int(batch.skipped_docs or 0)
                pages_budget -= batch.pages_fetched
                for repo in batch.repos:
                    known.add(repo["full_name"])
                chunk = apply_filters(
                    batch.repos, wanted, body.max_age_days, created_within
                )
                filtered.extend(chunk)
                walk_page = batch.next_page
                walk_star_ceiling = batch.star_ceiling
                walk_time_ceiling = batch.time_ceiling
                if batch.exhausted or pages_budget <= 0:
                    break
                if not batch.repos and not batch.exhausted:
                    # Advanced a band with no collectable repos; continue loop.
                    continue
                if not chunk and batch.repos:
                    # Raw hits existed but none matched type filters — keep going.
                    continue
                if not chunk and not batch.repos:
                    break
        except GitHubError as exc:
            raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

        if batch is None:
            # Catch-up-only path (filled need without walking older bands).
            batch = type(
                "Batch",
                (),
                {
                    "exhausted": False,
                    "next_page": walk_page,
                    "star_ceiling": walk_star_ceiling,
                    "time_ceiling": walk_time_ceiling,
                    "query": catchup_query,
                    "pages_fetched": 0,
                    "raw_seen": 0,
                    "skipped_docs": 0,
                    "repos": [],
                },
            )()

        # Dedupe and trim.
        seen_names: set[str] = set()
        unique: list[dict] = []
        for repo in filtered:
            name = repo["full_name"]
            if name in seen_names:
                continue
            seen_names.add(name)
            unique.append(repo)
        filtered = unique[: body.max_results]

        async def enrich(repo: dict, *, light: bool = False) -> None:
            if light:
                languages = await repo_languages(client, repo["full_name"])
                count = None
            else:
                count, languages = await asyncio.gather(
                    advisory_count(client, repo["full_name"]),
                    repo_languages(client, repo["full_name"]),
                )
            repo["advisory_count"] = count
            repo["languages"] = languages
            if not repo.get("language") and languages:
                repo["language"] = max(languages, key=languages.get)
            repo["research_score"] = score_repo(
                repo, wanted, body.max_age_days, created_within
            )

        if filtered:
            # Large filter-free batches skip advisory lookups to stay under rate limits.
            light = (not wanted) and len(filtered) >= 25
            await asyncio.gather(*(enrich(repo, light=light) for repo in filtered))
            filtered.sort(
                key=lambda r: (r["research_score"], r.get("created_at") or "", r["stars"]),
                reverse=True,
            )

    now = utcnow()
    sync_research_dir()
    with db() as conn:
        org_id = upsert_org(conn, org, now)
        saved: list[dict] = []
        for repo in filtered:
            saved.append(upsert_project(conn, org_id, repo))

        # Preserve older-band exhaustion across catch-up-only continues.
        exhausted = walk_exhausted or bool(getattr(batch, "exhausted", False))
        cursor_row = upsert_search_cursor(
            conn,
            org_login=org["login"],
            filter_key=filter_key,
            github_page=int(getattr(batch, "next_page", walk_page) or walk_page),
            star_ceiling=getattr(batch, "star_ceiling", walk_star_ceiling),
            time_ceiling=getattr(batch, "time_ceiling", walk_time_ceiling),
            exhausted=exhausted,
            total_discovered=previous_total + len(saved),
            min_stars=body.min_stars,
            max_age_days=body.max_age_days,
            project_types=wanted,
        )
        conn.execute(
            """
            INSERT INTO scans (
                org_login, org_url, status, result_count, min_stars, max_age_days,
                project_types, mode, added_count, created_within_days, sort_by,
                created_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                org["login"],
                org["html_url"],
                "done",
                len(saved),
                body.min_stars,
                body.max_age_days,
                json.dumps(wanted),
                mode,
                len(saved),
                created_within,
                sort_by,
                now,
                now,
            ),
        )
        _, projects = load_org_projects(conn, org["login"])
        orgs = org_catalog(conn)

    remember_org(org["login"])
    if saved:
        mode_note = " filter-free" if not wanted else ""
        message = f"Added {len(saved)} new{mode_note} project{'s' if len(saved) != 1 else ''}."
        if catchup_count:
            message += f" ({catchup_count} from newest catch-up)."
        if skipped_docs_total:
            message += f" Skipped {skipped_docs_total} docs/guide/course repo{'s' if skipped_docs_total != 1 else ''}."
        if cursor_reset:
            message += " Reset a stuck discovery window."
    elif exhausted:
        message = (
            "Older discovery bands are exhausted for these filters. "
            "Load more still rechecks newest repos; widen Created/Pushed days, "
            "enable filter-free, or run Find projects to reset."
        )
    else:
        message = (
            "No new matches in this batch (already saved or filtered out). "
            "Load more will keep walking older bands; Find projects resets to newest."
        )
    return {
        "organization": org,
        "projects": projects,
        "added": saved,
        "added_count": len(saved),
        "organizations": orgs,
        "cursor": serialize_cursor(cursor_row),
        "mode": mode,
        "message": message,
        "skipped_docs": skipped_docs_total,
        "catchup_count": catchup_count,
        "cursor_reset": cursor_reset,
        "query": getattr(batch, "query", "") or "",
        "filter_free": not wanted,
    }



@router.post("/research/repo")
async def research_repo(body: RepoResearchRequest, background: BackgroundTasks) -> dict:
    command = (body.command or saved_research_command()).strip()
    if not command:
        raise HTTPException(status_code=400, detail="Research command cannot be empty.")
    try:
        owner, name = parse_repo_input(body.repo_url)
    except GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            repo = await get_repo(client, owner, name)
            count, languages = await asyncio.gather(
                advisory_count(client, repo["full_name"]),
                repo_languages(client, repo["full_name"]),
            )
        except GitHubError as exc:
            raise HTTPException(status_code=exc.status_code or 502, detail=str(exc)) from exc

    repo["advisory_count"] = count
    repo["languages"] = languages
    if not repo.get("language") and languages:
        repo["language"] = max(languages, key=languages.get)
    types = classify_project(repo)
    repo["project_types"] = types
    repo["research_score"] = score_repo(repo, types or ["web", "api"], 3650)

    org = {
        "login": owner,
        "name": owner,
        "html_url": f"https://github.com/{owner}",
    }
    now = utcnow()
    sync_research_dir()
    with db() as conn:
        org_id = upsert_org(conn, org, now)
        project = upsert_project(conn, org_id, repo)
        job, created = queue_research(conn, project["id"], command)
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project["id"],)).fetchone()
        )
        orgs = org_catalog(conn)

    if created:
        background.add_task(run_research_job, job["id"], project["id"])

    remember_org(owner)
    return {
        "organization": org,
        "project": project,
        "job": job,
        "organizations": orgs,
        "created": created,
    }

