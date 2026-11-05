from __future__ import annotations

import re
import shlex
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


def _resume_message_index(parts: list[str]) -> int | None:
    """Index of the one query argument on a command-code --resume/--continue argv."""
    if not any(part in {"--resume", "--continue", "-c", "-r"} for part in parts[1:]):
        return None
    if len(parts) > 1 and not parts[-1].startswith("-"):
        return len(parts) - 1
    return None


def enrich_research_command(
    command: str,
    profile: dict[str, Any],
    sast_summary: str = "",
) -> str:
    try:
        parts = shlex.split(command or "")
    except ValueError:
        parts = []
    message_at = _resume_message_index(parts)
    if message_at is not None:
        # command-code accepts one positional query. The resume note is already
        # that argument; appending the default brief makes a second one.
        enriched = build_enriched_prompt(parts[message_at], profile, sast_summary)
        if enriched == parts[message_at]:
            return command
        parts[message_at] = enriched
        return shlex.join(parts)
    existing = extract_prompt_from_command(command)
    enriched = build_enriched_prompt(existing, profile, sast_summary)
    return replace_prompt_in_command(command, enriched)
