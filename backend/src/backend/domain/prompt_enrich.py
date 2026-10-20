from __future__ import annotations

import re
from typing import Any

from backend.core.config import RESEARCH_PROMPT, quote_prompt
from backend.domain.language_profile import language_research_addendum

# Match a double-quoted string with basic escapes (how our presets store prompts).
_QUOTED_RE = re.compile(r'"((?:\\.|[^"\\])*)"')


def extract_prompt_from_command(command: str) -> str | None:
    matches = list(_QUOTED_RE.finditer(command or ""))
    if not matches:
        return None
    raw = matches[-1].group(1)
    return raw.replace('\\"', '"').replace("\\\\", "\\")


def replace_prompt_in_command(command: str, new_prompt: str) -> str:
    quoted = quote_prompt(new_prompt)
    matches = list(_QUOTED_RE.finditer(command or ""))
    if not matches:
        return f"{command.rstrip()} {quoted}".strip()
    last = matches[-1]
    return command[: last.start()] + quoted + command[last.end() :]


def build_enriched_prompt(
    base_prompt: str | None,
    profile: dict[str, Any],
    sast_summary: str = "",
) -> str:
    base = (base_prompt or RESEARCH_PROMPT).strip()
    addendum = language_research_addendum(profile, sast_summary)
    # Avoid duplicating if already enriched.
    if "## Language-aware research plan" in base:
        return base
    return f"{base}\n{addendum}".strip()


def enrich_research_command(
    command: str,
    profile: dict[str, Any],
    sast_summary: str = "",
) -> str:
    existing = extract_prompt_from_command(command)
    enriched = build_enriched_prompt(existing, profile, sast_summary)
    return replace_prompt_in_command(command, enriched)
