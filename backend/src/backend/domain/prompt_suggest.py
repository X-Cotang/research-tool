from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from backend.domain.ai_settings import require_prompt_settings
from backend.core.config import RESEARCH_DIR, RESEARCH_PROMPT
from backend.domain.language_profile import build_language_profile

SYSTEM_PROMPT = """You write tailored defensive security research prompts for open-source projects.
The researcher will paste your prompt into a local CLI coding agent that reviews source code.

Rules:
- Focus on finding genuine, high-value vulnerabilities suitable for responsible disclosure / CVE / bounty.
- Prefer project-specific attack surfaces for the detected language stack (auth, parsers, deserializers, SSRF sinks, template engines, etc.).
- Emphasize the language focus areas provided; do not waste tokens on unrelated bug classes.
- Do NOT ask for weaponized exploits, live attacks, or PoCs against production systems.
- Do NOT request credential theft or malware.
- Output ONLY the prompt text the CLI should receive. No markdown fences, no preamble.
"""


def _tree_sample(local_path: str | None, limit: int = 40) -> str:
    if not local_path:
        return ""
    root = Path(local_path)
    if not root.is_dir():
        # Try research dir convention.
        candidate = RESEARCH_DIR / local_path
        root = candidate if candidate.is_dir() else root
    if not root.is_dir():
        return ""
    lines: list[str] = []
    skip = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
    try:
        for path in sorted(root.rglob("*")):
            if any(part in skip for part in path.parts):
                continue
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                lines.append(rel)
                if len(lines) >= limit:
                    break
    except OSError:
        return ""
    return "\n".join(lines)


def _resolve_root(project: dict[str, Any]) -> Path | None:
    local = project.get("local_path")
    if local:
        path = Path(local)
        if path.is_dir():
            return path
    full_name = project.get("full_name")
    if full_name:
        candidate = RESEARCH_DIR / full_name
        if candidate.is_dir():
            return candidate
    return None


def build_suggestion_context(project: dict[str, Any]) -> str:
    root = _resolve_root(project)
    profile = build_language_profile(project, root)
    languages = project.get("languages") or {}
    if isinstance(languages, dict) and languages:
        lang_line = ", ".join(list(languages.keys())[:12])
    else:
        lang_line = project.get("language") or "n/a"
    topics = project.get("topics") or []
    topic_line = ", ".join(topics[:20]) if topics else "n/a"
    tree = _tree_sample(str(root) if root else (project.get("local_path") or project.get("full_name")))
    parts = [
        f"Repository: {project.get('full_name')}",
        f"URL: {project.get('html_url')}",
        f"Description: {project.get('description') or 'n/a'}",
        f"GitHub languages: {lang_line}",
        f"Detected primary: {profile.get('primary')}",
        f"Detected stack: {', '.join(profile.get('languages') or []) or 'n/a'}",
        f"Focus areas: {profile.get('focus') or 'n/a'}",
        f"Recommended SAST packs: {', '.join(profile.get('semgrep_packs') or [])}",
        f"Topics: {topic_line}",
        f"Stars: {project.get('stars') or 0}",
        "",
        "Baseline prompt style to refine (keep the responsible-disclosure intent):",
        RESEARCH_PROMPT,
        "",
        "Agent hint:",
        profile.get("agent_hint") or "",
    ]
    if tree:
        parts.extend(["", "Sample file tree:", tree])
    return "\n".join(parts)


async def suggest_prompt(project: dict[str, Any]) -> dict[str, str]:
    cfg = require_prompt_settings()
    user = build_suggestion_context(project)
    root = _resolve_root(project)
    profile = build_language_profile(project, root)
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Write one tailored research prompt for this project.\n\n" + user
                ),
            },
        ],
    }
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.status_code >= 400:
        detail = response.text[:800]
        raise RuntimeError(f"Prompt suggestion failed ({response.status_code}): {detail}")
    payload = response.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected suggestion response: {json.dumps(payload)[:500]}") from exc
    prompt = str(content or "").strip()
    if prompt.startswith("```"):
        prompt = prompt.strip("`")
        if prompt.lower().startswith("text"):
            prompt = prompt[4:].lstrip()
    if not prompt:
        raise RuntimeError("Model returned an empty prompt.")
    return {
        "prompt": prompt,
        "rationale": (
            f"Tailored for {profile.get('primary')} "
            f"({', '.join((profile.get('languages') or [])[:3]) or 'unknown stack'})."
        ),
        "model": cfg["model"],
        "language_profile": {
            "primary": profile.get("primary"),
            "languages": profile.get("languages"),
            "semgrep_packs": profile.get("semgrep_packs"),
        },
    }


async def test_ai_connection() -> dict[str, str]:
    cfg = require_prompt_settings()
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": cfg["model"],
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "Reply with OK"}],
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(url, headers=headers, json=body)
    if response.status_code >= 400:
        raise RuntimeError(f"Test failed ({response.status_code}): {response.text[:500]}")
    return {"status": "ok", "model": cfg["model"]}
