from __future__ import annotations

from pathlib import Path
from typing import Any

# Extension → canonical language name (GitHub-style).
EXTENSION_LANG = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".fs": "F#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".rs": "Rust",
    ".swift": "Swift",
    ".scala": "Scala",
    ".sc": "Scala",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".m": "Objective-C",
    ".mm": "Objective-C",
    ".vue": "Vue",
    ".svelte": "JavaScript",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".dart": "Dart",
}

# Marker files that strongly indicate a stack.
MARKER_LANG = {
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "Pipfile": "Python",
    "setup.py": "Python",
    "manage.py": "Python",
    "package.json": "JavaScript",
    "pnpm-lock.yaml": "JavaScript",
    "yarn.lock": "JavaScript",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "*.csproj": "C#",
    "Package.swift": "Swift",
}

# Semgrep/Opengrep registry packs keyed by primary language.
# Keep lists short: each pack costs scan time.
SEMGREP_PACKS: dict[str, list[str]] = {
    "Python": ["p/python", "p/security-audit", "p/secrets"],
    "JavaScript": ["p/javascript", "p/security-audit", "p/secrets"],
    "TypeScript": ["p/typescript", "p/javascript", "p/security-audit", "p/secrets"],
    "Go": ["p/golang", "p/security-audit", "p/secrets"],
    "Java": ["p/java", "p/security-audit", "p/secrets"],
    "Kotlin": ["p/kotlin", "p/java", "p/security-audit", "p/secrets"],
    "C#": ["p/csharp", "p/security-audit", "p/secrets"],
    "Ruby": ["p/ruby", "p/security-audit", "p/secrets"],
    "PHP": ["p/php", "p/security-audit", "p/secrets"],
    "Rust": ["p/rust", "p/security-audit", "p/secrets"],
    "Scala": ["p/scala", "p/security-audit", "p/secrets"],
    "Swift": ["p/swift", "p/security-audit", "p/secrets"],
    "C": ["p/c", "p/security-audit", "p/secrets"],
    "C++": ["p/cpp", "p/security-audit", "p/secrets"],
    "Vue": ["p/javascript", "p/security-audit", "p/secrets"],
    "Dart": ["p/security-audit", "p/secrets"],
    "Elixir": ["p/security-audit", "p/secrets"],
}

DEFAULT_PACKS = ["p/security-audit", "p/secrets", "p/owasp-top-ten"]

# Scientific focus areas for LLM / CLI agents by language family.
FOCUS_AREAS: dict[str, str] = {
    "Python": (
        "pickle/yaml/json deserialization, SSTI (Jinja/Mako), SSRF, SQLi/NoSQLi, "
        "command injection, path traversal, insecure tempfile, Django/Flask authz bypass"
    ),
    "JavaScript": (
        "XSS, prototype pollution, SSRF, path traversal, ReDoS, unsafe eval/Function, "
        "insecure child_process, Express authz gaps, supply-chain require gadgets"
    ),
    "TypeScript": (
        "XSS, prototype pollution, SSRF, path traversal, unsafe deserialization, "
        "authn/authz middleware gaps, injection into ORMs, unsafe dynamic imports"
    ),
    "Go": (
        "SSRF, path traversal, command injection, race conditions, TLS misconfig, "
        "SQL injection, unsafe deserialization of gob/json into privileged structs"
    ),
    "Java": (
        "deserialization gadgets, SSRF, XXE, SQLi, expression language injection, "
        "path traversal, authz filter bypass, Spring SpEL"
    ),
    "Kotlin": (
        "deserialization, SSRF, SQLi, path traversal, insecure crypto, "
        "Android/IPC issues if applicable, Spring/Ktor authz gaps"
    ),
    "C#": (
        "deserialization (BinaryFormatter/JSON), SSRF, XXE, SQLi, path traversal, "
        "insecure crypto, ASP.NET authz gaps"
    ),
    "Ruby": (
        "YAML/Marshal deserialization, SSRF, SQLi, command injection, "
        "mass assignment, ERB SSTI, Rails authz gaps"
    ),
    "PHP": (
        "SQLi, XSS, file include/upload, deserialization, SSTI, "
        "command injection, authz gaps, insecure session handling"
    ),
    "Rust": (
        "unsafe blocks, integer overflow around FFI, path traversal, "
        "command injection, TLS/certificate validation bugs, panic DoS in parsers"
    ),
    "C": (
        "buffer overflows, integer overflows, UAF, format strings, "
        "path traversal, command injection, insecure temp files"
    ),
    "C++": (
        "memory corruption, UAF, integer overflows, insecure parsers, "
        "path traversal, command injection"
    ),
    "Scala": (
        "deserialization, SSRF, SQLi, XSS in templates, authz gaps"
    ),
    "Swift": (
        "insecure crypto, path traversal, injection into system APIs, authz gaps"
    ),
    "Vue": (
        "XSS via v-html, prototype pollution, unsafe URL handling, SSR XSS"
    ),
    "Dart": (
        "path traversal, command injection, insecure deserialization, authz gaps"
    ),
    "Elixir": (
        "command injection, SSRF, unsafe atom creation DoS, SQLi, authz gaps"
    ),
}


def _bytes_map(languages: Any) -> dict[str, int]:
    if isinstance(languages, dict):
        out: dict[str, int] = {}
        for key, value in languages.items():
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def detect_languages_from_tree(root: Path, limit_files: int = 4000) -> dict[str, int]:
    """Heuristic byte-ish weights from file extensions and markers."""
    weights: dict[str, int] = {}
    if not root.is_dir():
        return weights
    skip = {
        ".git", "node_modules", "dist", "build", ".venv", "venv",
        "__pycache__", "target", "vendor", ".next", "coverage",
    }
    seen = 0
    try:
        for path in root.rglob("*"):
            if any(part in skip for part in path.parts):
                continue
            if path.is_file():
                name = path.name
                for marker, lang in MARKER_LANG.items():
                    if marker.startswith("*"):
                        if name.endswith(marker[1:]):
                            weights[lang] = weights.get(lang, 0) + 50_000
                    elif name == marker:
                        weights[lang] = weights.get(lang, 0) + 50_000
                ext = path.suffix.lower()
                lang = EXTENSION_LANG.get(ext)
                if lang:
                    try:
                        size = min(path.stat().st_size, 200_000)
                    except OSError:
                        size = 1000
                    weights[lang] = weights.get(lang, 0) + max(size, 200)
                seen += 1
                if seen >= limit_files:
                    break
    except OSError:
        return weights
    return weights


def merge_language_maps(*maps: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for mapping in maps:
        for lang, weight in mapping.items():
            merged[lang] = merged.get(lang, 0) + int(weight)
    return merged


def ranked_languages(languages: dict[str, int], *, limit: int = 5) -> list[str]:
    return [
        name
        for name, _ in sorted(languages.items(), key=lambda item: item[1], reverse=True)[:limit]
        if name and name not in {"HTML", "CSS", "Markdown", "Shell", "Dockerfile", "Makefile"}
    ]


def detect_project_languages(project: dict[str, Any], root: Path | None = None) -> dict[str, int]:
    github = _bytes_map(project.get("languages"))
    primary = (project.get("language") or "").strip()
    if primary and primary not in github:
        github[primary] = max(github.values() if github else [0]) + 1
    disk = detect_languages_from_tree(root) if root else {}
    return merge_language_maps(github, disk)


def build_language_profile(project: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    weights = detect_project_languages(project, root)
    ranked = ranked_languages(weights)
    primary = ranked[0] if ranked else (project.get("language") or "Unknown")
    secondary = ranked[1:4]
    packs: list[str] = []
    for lang in [primary, *secondary]:
        for pack in SEMGREP_PACKS.get(lang, []):
            if pack not in packs:
                packs.append(pack)
    if not packs:
        packs = list(DEFAULT_PACKS)
    # Always include secrets + a generic security pack.
    for pack in ("p/secrets", "p/security-audit"):
        if pack not in packs:
            packs.append(pack)
    # Cap packs for scan budget.
    packs = packs[:5]

    focus_bits = []
    for lang in [primary, *secondary[:2]]:
        tip = FOCUS_AREAS.get(lang)
        if tip:
            focus_bits.append(f"{lang}: {tip}")
    if not focus_bits:
        focus_bits.append(
            "generic: injection, authz bypass, SSRF, path traversal, deserialization, XSS"
        )

    return {
        "primary": primary,
        "languages": ranked,
        "weights": {k: weights[k] for k in ranked if k in weights},
        "semgrep_packs": packs,
        "focus": " | ".join(focus_bits),
        "agent_hint": (
            f"Primary language appears to be {primary}"
            + (f" (also {', '.join(secondary)})" if secondary else "")
            + ". Prioritize attack surfaces for that stack. "
            "If semgrep or opengrep is on PATH, run a targeted scan and verify each HIGH finding in code."
        ),
    }


def language_research_addendum(profile: dict[str, Any], sast_summary: str = "") -> str:
    """Extra instructions appended into the CLI agent prompt."""
    parts = [
        "",
        "## Language-aware research plan",
        profile.get("agent_hint") or "",
        f"Focus areas: {profile.get('focus') or 'n/a'}",
        "",
        "Method:",
        "1. Map entrypoints (HTTP handlers, CLI, parsers, deserializers, auth middleware).",
        "2. Prefer high-impact bug classes for this stack over stylistic issues.",
        "3. Confirm each candidate in source; discard false positives.",
        "4. Write confirmed findings into RESEARCH_NOTES.md with file paths and impact.",
        "5. Do not attack remote systems; local code review only.",
    ]
    if sast_summary.strip():
        parts.extend(
            [
                "",
                "## Static analysis leads (verify, do not trust blindly)",
                sast_summary.strip(),
            ]
        )
    return "\n".join(parts)
