from __future__ import annotations

from datetime import datetime, timezone

from backend.domain.github_client import is_docs_or_learning_content

WEB_LANGUAGES = {"JavaScript", "TypeScript", "PHP", "Ruby", "HTML", "CSS", "Vue", "Dart"}
API_LANGUAGES = {"Go", "Python", "Java", "Kotlin", "C#", "Rust", "TypeScript", "Scala", "Elixir"}

WEB_HINTS = {
    "web", "frontend", "website", "ui", "react", "nextjs", "next.js", "vue", "angular",
    "django", "flask", "rails", "laravel", "wordpress", "browser", "css", "html",
}
API_HINTS = {
    "api", "graphql", "grpc", "rest", "openapi", "swagger", "backend", "sdk",
    "fastapi", "express", "service", "server", "rpc",
}


def classify_project(repo: dict) -> list[str]:
    haystack = " ".join(
        [
            repo.get("name") or "",
            repo.get("description") or "",
            repo.get("language") or "",
            " ".join(repo.get("topics") or []),
        ]
    ).lower()
    language = repo.get("language") or ""
    types: list[str] = []
    if language in WEB_LANGUAGES or any(hint in haystack for hint in WEB_HINTS):
        types.append("web")
    if language in API_LANGUAGES or any(hint in haystack for hint in API_HINTS):
        types.append("api")
    return types


def _stars_score(stars: int) -> float:
    if stars <= 0:
        return 0.15  # brand-new repos often have zero stars; don't zero them out
    # 50 stars ~ 0.35, 200 ~ 0.5, 2k ~ 0.75, 20k ~ 0.95
    return min(1.0, 0.15 + (stars**0.35) / 22)


def _age_days(timestamp: str) -> float | None:
    if not timestamp:
        return None
    try:
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds() / 86400)


def _recency_score(timestamp: str, window_days: int) -> float:
    age_days = _age_days(timestamp)
    if age_days is None:
        return 0.0
    if window_days <= 0 or age_days >= window_days:
        return 0.0
    return max(0.0, 1.0 - (age_days / window_days))


def _created_score(created_at: str, created_within_days: int) -> float:
    """Strongly prefer repos created recently so new targets surface first."""
    age_days = _age_days(created_at)
    if age_days is None:
        return 0.0
    # Always score creation freshness on a short horizon so brand-new repos win.
    horizon = max(14, min(created_within_days or 90, 180))
    if age_days >= horizon:
        return 0.0
    # Extra boost in the first two weeks.
    if age_days <= 14:
        return 1.0
    return max(0.0, 1.0 - ((age_days - 14) / max(1.0, horizon - 14)))


def _low_research_score(repo: dict) -> float:
    advisories = repo.get("advisory_count")
    stars = max(1, repo.get("stars") or 0)
    forks = repo.get("forks") or 0
    fork_ratio = min(1.0, forks / stars)
    # Fewer published advisories and fewer forks-per-star => less prior public research.
    if advisories is None:
        advisory_factor = 0.55
    elif advisories == 0:
        advisory_factor = 1.0
    elif advisories <= 2:
        advisory_factor = 0.7
    else:
        advisory_factor = 0.25
    return max(0.0, min(1.0, advisory_factor * (1.0 - 0.5 * fork_ratio)))


def score_repo(
    repo: dict,
    wanted_types: list[str],
    max_age_days: int,
    created_within_days: int = 0,
) -> float:
    types = repo.get("project_types") or []
    type_score = 1.0 if not wanted_types else (1.0 if set(types) & set(wanted_types) else 0.15)
    return round(
        100
        * (
            0.22 * _stars_score(repo.get("stars") or 0)
            + 0.18 * _recency_score(repo.get("pushed_at") or "", max_age_days)
            + 0.22 * _created_score(repo.get("created_at") or "", created_within_days)
            + 0.18 * type_score
            + 0.20 * _low_research_score(repo)
        ),
        1,
    )


def apply_filters(
    repos: list[dict],
    wanted_types: list[str],
    max_age_days: int,
    created_within_days: int = 0,
) -> list[dict]:
    scored: list[dict] = []
    for repo in repos:
        if is_docs_or_learning_content(repo):
            continue
        types = classify_project(repo)
        if wanted_types and not (set(types) & set(wanted_types)):
            continue
        if created_within_days > 0:
            age = _age_days(repo.get("created_at") or "")
            if age is None or age > created_within_days:
                continue
        item = {**repo, "project_types": types}
        item["research_score"] = score_repo(
            item, wanted_types, max_age_days, created_within_days
        )
        scored.append(item)
    scored.sort(
        key=lambda r: (r["research_score"], r.get("created_at") or "", r["stars"]),
        reverse=True,
    )
    return scored
