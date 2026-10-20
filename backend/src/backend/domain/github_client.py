from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend.core.config import GITHUB_API
from backend.domain.github_settings import get_github_token

# Content we usually do not want to research for vulns.
DOC_NAME_TOKENS = (
    "docs",
    "doc-",
    "-doc",
    "documentation",
    "guide",
    "tutorial",
    "course",
    "courses",
    "curriculum",
    "workshop",
    "workshops",
    "bootcamp",
    "learning",
    "learn-",
    "-learn",
    "handbook",
    "cheatsheet",
    "cheat-sheet",
    "awesome-",
    "samples-day",
    "training",
)
DOC_TOPIC_TOKENS = {
    "documentation",
    "docs",
    "tutorial",
    "tutorials",
    "course",
    "courses",
    "guide",
    "guides",
    "learning",
    "workshop",
    "education",
    "curriculum",
    "handbook",
    "cheatsheet",
}
DOC_DESCRIPTION_PHRASES = (
    "official documentation",
    "documentation site",
    "learning path",
    "online course",
    "training materials",
    "tutorial series",
    "getting started guide",
    "course materials",
)


class GitHubError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "research-tool",
    }
    token = get_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def github_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    try:
        response = await client.get(url, headers=_headers(), params=params)
    except httpx.HTTPError as exc:
        raise GitHubError(f"GitHub request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:400]
        raise GitHubError(
            f"GitHub API error {response.status_code}: {detail}",
            status_code=response.status_code,
        )
    return response


def parse_org_input(raw: str) -> str:
    text = (raw or "").strip().rstrip("/")
    if not text:
        raise GitHubError("Organization URL or login is required.", 400)
    if "github.com" in text:
        # https://github.com/microsoft[/...]
        parts = text.split("github.com/", 1)[-1].split("/")
        login = parts[0]
    else:
        login = text.split("/")[0]
    login = login.strip()
    if not login:
        raise GitHubError("Could not parse organization login.", 400)
    return login


def parse_repo_input(raw: str) -> tuple[str, str]:
    text = (raw or "").strip().rstrip("/")
    if not text:
        raise GitHubError("Repository URL is required.", 400)
    if "github.com" in text:
        parts = [p for p in text.split("github.com/", 1)[-1].split("/") if p]
    else:
        parts = [p for p in text.split("/") if p]
    if len(parts) < 2:
        raise GitHubError("Expected owner/repo or a GitHub repository URL.", 400)
    return parts[0], parts[1]


async def get_owner(client: httpx.AsyncClient, login: str) -> dict:
    try:
        response = await github_get(client, f"/orgs/{login}")
        data = response.json()
        kind = "org"
    except GitHubError as exc:
        if exc.status_code != 404:
            raise
        response = await github_get(client, f"/users/{login}")
        data = response.json()
        kind = "org" if data.get("type") == "Organization" else "user"
    return {
        "login": data["login"],
        "name": data.get("name") or data["login"],
        "html_url": data.get("html_url") or f"https://github.com/{data['login']}",
        "kind": kind,
    }


def _iso_day(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_docs_or_learning_content(repo: dict) -> bool:
    """True for documentation, guides, courses, and similar non-product repos."""
    name = (repo.get("name") or "").lower()
    full = (repo.get("full_name") or "").lower()
    desc = (repo.get("description") or "").lower()
    topics = {str(t).lower() for t in (repo.get("topics") or [])}
    hay = f"{name} {full} {desc}"

    if topics & DOC_TOPIC_TOKENS:
        return True
    if any(token in name for token in DOC_NAME_TOKENS):
        return True
    if any(phrase in desc for phrase in DOC_DESCRIPTION_PHRASES):
        return True
    # Bare "docs" / "documentation" repos.
    if name in {"docs", "documentation", "doc", "guides", "tutorials", "learn", "learning", "course", "courses"}:
        return True
    if hay.count("documentation") >= 1 and (repo.get("language") or "") in {"", "HTML", "Markdown", "CSS"}:
        return True
    return False


def _exclusion_qualifiers() -> list[str]:
    # Prefer client-side filtering for name tokens — GitHub's `-in:name docs`
    # style qualifiers are easy to get wrong and can zero the result set.
    # Topic exclusions are reliable.
    return [
        "-topic:documentation",
        "-topic:tutorial",
        "-topic:tutorials",
        "-topic:course",
        "-topic:courses",
        "-topic:learning",
        "-topic:guide",
        "-topic:guides",
        "-topic:workshop",
        "-topic:education",
        "-topic:curriculum",
    ]


def _search_query(
    login: str,
    kind: str,
    min_stars: int,
    max_age_days: int,
    *,
    star_ceiling: int | None = None,
    created_within_days: int = 0,
    time_ceiling: str | None = None,
    sort: str = "updated",
) -> str:
    pushed_after = _iso_day(max_age_days)
    owner = f"org:{login}" if kind == "org" else f"user:{login}"
    parts = [
        owner,
        "archived:false",
        "fork:false",
        f"stars:>={min_stars}",
        f"pushed:>={pushed_after}",
        *_exclusion_qualifiers(),
    ]
    created_after = _iso_day(created_within_days) if created_within_days > 0 else None
    if created_after:
        parts.append(f"created:>={created_after}")

    # Time banding: only apply an upper bound when it still leaves a non-empty window.
    # A resumed cursor can otherwise become created:>=X created:<X (zero results forever).
    if time_ceiling:
        if sort == "created":
            if not created_after or time_ceiling > created_after:
                parts.append(f"created:<{time_ceiling}")
        elif sort == "updated":
            if time_ceiling > pushed_after:
                parts.append(f"pushed:<{time_ceiling}")

    if star_ceiling is not None and star_ceiling > min_stars:
        parts.append(f"stars:<{star_ceiling}")
    return " ".join(parts)


def sanitize_search_cursor(
    *,
    sort: str,
    min_stars: int,
    max_age_days: int,
    created_within_days: int,
    star_ceiling: int | None,
    time_ceiling: str | None,
    github_page: int,
) -> tuple[int, int | None, str | None, bool]:
    """Drop contradictory ceilings from a saved cursor. Returns (page, stars, time, reset)."""
    page = max(1, min(int(github_page or 1), 10))
    stars = star_ceiling
    time = time_ceiling
    reset = False
    sort_key = sort if sort in {"stars", "updated", "created"} else "updated"

    if stars is not None and stars <= min_stars:
        stars = None
        page = 1
        reset = True

    if time and sort_key == "created" and created_within_days > 0:
        floor = _iso_day(created_within_days)
        if time <= floor:
            time = None
            page = 1
            reset = True
    elif time and sort_key == "updated":
        floor = _iso_day(max_age_days)
        if time <= floor:
            time = None
            page = 1
            reset = True

    return page, stars, time, reset


@dataclass
class SearchBatch:
    repos: list[dict]
    next_page: int
    star_ceiling: int | None
    time_ceiling: str | None
    exhausted: bool
    pages_fetched: int
    raw_seen: int
    skipped_docs: int = 0
    query: str = ""


async def get_repo(client: httpx.AsyncClient, owner: str, name: str) -> dict:
    response = await github_get(client, f"/repos/{owner}/{name}")
    data = response.json()
    if data.get("fork"):
        raise GitHubError("Forked repositories are skipped. Paste the upstream repo instead.", 400)
    if data.get("archived"):
        raise GitHubError("That repository is archived.", 400)
    return _normalize_repo(data)


async def search_org_repos(
    client: httpx.AsyncClient,
    org: str,
    min_stars: int,
    max_age_days: int,
    target_new: int = 40,
    kind: str = "org",
    exclude: set[str] | None = None,
    start_page: int = 1,
    star_ceiling: int | None = None,
    time_ceiling: str | None = None,
    max_pages: int = 25,
    created_within_days: int = 0,
    sort: str = "updated",
) -> SearchBatch:
    """Fetch unseen repos with star and/or time banding past GitHub's 1k window."""
    known = set(exclude or ())
    collected: list[dict] = []
    sort_key = sort if sort in {"stars", "updated", "created"} else "updated"
    page, ceiling, t_ceiling, _ = sanitize_search_cursor(
        sort=sort_key,
        min_stars=min_stars,
        max_age_days=max_age_days,
        created_within_days=created_within_days,
        star_ceiling=star_ceiling,
        time_ceiling=time_ceiling,
        github_page=start_page,
    )
    pages_fetched = 0
    raw_seen = 0
    skipped_docs = 0
    band_lowest_stars: int | None = None
    band_oldest: datetime | None = None
    empty_advances = 0
    last_query = ""

    created_floor = (
        datetime.now(timezone.utc) - timedelta(days=created_within_days)
        if created_within_days > 0
        else None
    )
    pushed_floor = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    def _time_field(repo: dict) -> datetime | None:
        if sort_key == "created":
            return _parse_iso(repo.get("created_at"))
        return _parse_iso(repo.get("pushed_at"))

    def _floor_day() -> str | None:
        floor = created_floor if sort_key == "created" else pushed_floor
        return floor.date().isoformat() if floor else None

    def advance_band() -> bool:
        """Move to the next star or time window when the current band is spent."""
        nonlocal page, ceiling, t_ceiling, band_lowest_stars, band_oldest

        # Prefer time banding for created/updated sorts — star banding alone is weak there.
        if sort_key in {"created", "updated"} and band_oldest is not None:
            next_day = band_oldest.date().isoformat()
            if t_ceiling and next_day >= t_ceiling:
                next_day = (band_oldest - timedelta(days=1)).date().isoformat()
            floor_day = _floor_day()
            if not floor_day or next_day > floor_day:
                t_ceiling = next_day
                page = 1
                band_lowest_stars = None
                band_oldest = None
                return True
            # At the floor of the time window — clear a useless ceiling and try stars.
            t_ceiling = None

        if band_lowest_stars is None or band_lowest_stars <= min_stars:
            return False
        next_ceiling = band_lowest_stars if ceiling is None else min(ceiling - 1, band_lowest_stars)
        if ceiling is not None and next_ceiling >= ceiling:
            return False
        if next_ceiling <= min_stars:
            return False
        ceiling = next_ceiling
        page = 1
        band_lowest_stars = None
        band_oldest = None
        return True

    while len(collected) < target_new and pages_fetched < max_pages:
        last_query = _search_query(
            org,
            kind,
            min_stars,
            max_age_days,
            star_ceiling=ceiling,
            created_within_days=created_within_days,
            time_ceiling=t_ceiling,
            sort=sort_key,
        )
        try:
            response = await github_get(
                client,
                "/search/repositories",
                params={
                    "q": last_query,
                    "sort": sort_key,
                    "order": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
        except GitHubError as exc:
            if exc.status_code == 422:
                if not advance_band():
                    break
                empty_advances += 1
                if empty_advances > 8:
                    break
                continue
            raise

        payload = response.json()
        items = payload.get("items") or []
        pages_fetched += 1
        if not items:
            if not advance_band():
                break
            empty_advances += 1
            if empty_advances > 8:
                break
            continue

        page_new = 0
        for item in items:
            raw_seen += 1
            stars = int(item.get("stargazers_count") or 0)
            band_lowest_stars = stars if band_lowest_stars is None else min(band_lowest_stars, stars)
            repo = _normalize_repo(item)
            moment = _time_field(repo)
            if moment is not None:
                band_oldest = moment if band_oldest is None else min(band_oldest, moment)

            if repo["full_name"] in known:
                continue
            if is_docs_or_learning_content(repo):
                skipped_docs += 1
                known.add(repo["full_name"])
                continue
            known.add(repo["full_name"])
            collected.append(repo)
            page_new += 1
            if len(collected) >= target_new:
                break

        empty_advances = 0 if page_new or collected else empty_advances + 1

        if len(collected) >= target_new:
            page += 1
            break

        if len(items) < 100:
            if not advance_band():
                break
            continue

        page += 1
        if page > 10:
            if not advance_band():
                break

    can_advance = False
    if band_oldest is not None and sort_key in {"created", "updated"}:
        floor_day = _floor_day()
        oldest_day = band_oldest.date().isoformat()
        if not floor_day or oldest_day > floor_day:
            can_advance = True
    if band_lowest_stars is not None and band_lowest_stars > min_stars:
        can_advance = True

    # If the active time ceiling is already at/under the floor, this cursor cannot
    # produce more hits even when star banding looks available — force exhaustion.
    floor_day = _floor_day()
    if (
        sort_key in {"created", "updated"}
        and t_ceiling
        and floor_day
        and t_ceiling <= floor_day
        and not collected
    ):
        can_advance = False
        t_ceiling = None

    exhausted = len(collected) == 0 and not can_advance
    next_page = page if page <= 10 else 1
    return SearchBatch(
        repos=collected,
        next_page=next_page,
        star_ceiling=ceiling,
        time_ceiling=t_ceiling,
        exhausted=exhausted,
        pages_fetched=pages_fetched,
        raw_seen=raw_seen,
        skipped_docs=skipped_docs,
        query=last_query,
    )


def _normalize_repo(item: dict) -> dict:
    return {
        "full_name": item["full_name"],
        "name": item["name"],
        "html_url": item["html_url"],
        "clone_url": item.get("clone_url") or item["html_url"] + ".git",
        "description": item.get("description") or "",
        "language": item.get("language") or "",
        "topics": item.get("topics") or [],
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "pushed_at": item.get("pushed_at") or "",
        "created_at": item.get("created_at") or "",
        "open_issues": item.get("open_issues_count") or 0,
        "archived": bool(item.get("archived")),
        "fork": bool(item.get("fork")),
    }


async def repo_languages(client: httpx.AsyncClient, full_name: str) -> dict[str, int]:
    try:
        response = await client.get(
            f"{GITHUB_API}/repos/{full_name}/languages",
            headers=_headers(),
        )
    except httpx.HTTPError:
        return {}
    if response.status_code >= 400:
        return {}
    data = response.json()
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}


async def advisory_count(client: httpx.AsyncClient, full_name: str) -> int | None:
    try:
        response = await client.get(
            f"{GITHUB_API}/repos/{full_name}/security-advisories",
            headers={**_headers(), "Accept": "application/vnd.github+json"},
            params={"per_page": 1},
        )
    except httpx.HTTPError:
        return None
    if response.status_code == 404:
        return 0
    if response.status_code >= 400:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, list):
        return len(data)
    return None
