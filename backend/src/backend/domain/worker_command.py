"""Turn a research brief into a real CLI argv string.

The master writes a prompt and chooses a tool. This module refuses to treat a
prose sentence as an executable, which is what made the worker try to run
`Focus` as a binary.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from backend.core.config import (
    RESEARCH_PRESETS,
    binary_available,
    default_research_command,
    get_preset,
    infer_preset_id,
    resolve_binary_path,
)
from backend.domain.prompt_enrich import replace_prompt_in_command
from backend.domain.research import saved_research_command, saved_research_preset


class WorkerCommandError(Exception):
    pass


_KNOWN_BINARIES = {
    "command-code",
    "commandcode",
    "cmdc",
    "opencode",
    "freebuff",
    "claude",
    "codex",
    "qoder",
    "qodercli",
}


def looks_like_cli(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    try:
        parts = shlex.split(text)
    except ValueError:
        return False
    if not parts:
        return False
    binary = parts[0]
    name = Path(binary).name.lower()
    if name in _KNOWN_BINARIES or "/" in binary or binary.startswith("."):
        return True
    if resolve_binary_path(name) and any(part.startswith("-") for part in parts[1:]):
        return True
    return False


def first_available_preset_id() -> str | None:
    for preset in RESEARCH_PRESETS:
        if binary_available(preset):
            return preset["id"]
    return None


def _insert_extra_args(command: str, extra_args: list[str]) -> str:
    extras = [str(arg) for arg in extra_args if str(arg).strip()]
    if not extras:
        return command
    parts = shlex.split(command)
    if not parts:
        raise WorkerCommandError("Research command is empty.")
    insert_at = 2 if len(parts) > 1 and parts[1] in {"run", "exec"} else 1
    for offset, token in enumerate(extras):
        parts.insert(insert_at + offset, token)
    return shlex.join(parts)


def _base_command(preset_id: str | None, notes: list[str]) -> tuple[str, str]:
    requested = (preset_id or "").strip() or None
    preset = get_preset(requested) if requested else None
    if requested and requested != "custom" and preset is None:
        notes.append(f"Unknown preset {requested!r}; choosing an installed CLI.")
        requested = None
        preset = None

    if preset and not binary_available(preset):
        fallback = first_available_preset_id()
        if not fallback:
            raise WorkerCommandError(
                f"CLI preset {preset['id']} is not installed, and no other research CLI was found on PATH."
            )
        notes.append(f"Preset {preset['id']} is not installed; using {fallback}.")
        return default_research_command(fallback), fallback

    if preset:
        return default_research_command(preset["id"]), preset["id"]

    saved = saved_research_command().strip()
    saved_preset = saved_research_preset()
    if looks_like_cli(saved):
        binary = Path(shlex.split(saved)[0]).name
        if resolve_binary_path(binary) or saved_preset == "custom":
            return saved, saved_preset or infer_preset_id(saved)
        notes.append(f"Saved CLI {binary} is not on PATH.")

    fallback = first_available_preset_id()
    if not fallback:
        raise WorkerCommandError(
            "No research CLI is installed. Install command-code, opencode, claude, codex, freebuff, or qoder."
        )
    notes.append(f"Using installed CLI preset {fallback}.")
    return default_research_command(fallback), fallback


def _flag_value(parts: list[str], flag: str) -> str:
    if flag not in parts:
        return ""
    index = parts.index(flag)
    if index + 1 < len(parts):
        return parts[index + 1]
    return ""


def compose_resume_command(parent_command: str, session_id: str, message: str) -> str | None:
    """Reopen a finished command-code or qoder session. Other CLIs return None."""
    session_id = (session_id or "").strip()
    message = (message or "").strip()
    if not session_id or not message:
        return None
    try:
        parts = shlex.split(parent_command or "")
    except ValueError:
        parts = []
    if not parts:
        return None
    name = Path(parts[0]).name.lower()
    model = _flag_value(parts, "--model")
    if name in {"command-code", "commandcode", "cmdc"}:
        argv = [
            parts[0],
            "--resume",
            session_id,
            "--yolo",
            "--skip-onboarding",
            "--print",
            "--tools-all",
            "--output-format",
            "json",
        ]
        if model:
            argv.extend(["--model", model])
        argv.append(message)
        return shlex.join(argv)
    if name in {"qoder", "qodercli"}:
        permission = _flag_value(parts, "--permission-mode") or "bypass_permissions"
        argv = [
            parts[0],
            "--resume",
            session_id,
            "--print",
            "--output-format",
            "stream-json",
            "--permission-mode",
            permission,
        ]
        if model:
            argv.extend(["--model", model])
        argv.append(message)
        return shlex.join(argv)
    return None


def compose_worker_command(
    *,
    prompt: str | None = None,
    preset_id: str | None = None,
    command: str | None = None,
    extra_args: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (argv_string, meta).

    `command` is used only when it already starts with a real CLI. A bare
    research brief is treated as `prompt` instead of being executed.
    """
    notes: list[str] = []
    prompt_text = (prompt or "").strip()
    raw_command = (command or "").strip()
    prompt_source = "custom" if prompt_text else "preset-default"
    if isinstance(extra_args, str):
        extra_args = shlex.split(extra_args)

    if raw_command and not looks_like_cli(raw_command):
        notes.append(
            "Ignored a non-executable command string and used it as the research prompt."
        )
        if not prompt_text:
            prompt_text = raw_command
            prompt_source = "rewritten-from-command"
        raw_command = ""

    if raw_command:
        base = raw_command
        chosen = infer_preset_id(raw_command)
        source = "custom-command"
    else:
        base, chosen = _base_command(preset_id, notes)
        source = "preset"

    if extra_args:
        base = _insert_extra_args(base, extra_args)
        notes.append("Inserted extra CLI arguments.")

    if prompt_text:
        base = replace_prompt_in_command(base, prompt_text)
    elif prompt_source == "preset-default":
        notes.append("No custom prompt was provided; the preset's default brief is used.")

    if not looks_like_cli(base):
        raise WorkerCommandError(
            "Refusing to queue a research job whose command does not start with a CLI binary."
        )

    binary = ""
    try:
        binary = Path(shlex.split(base)[0]).name
    except ValueError:
        binary = ""

    return base, {
        "preset": chosen,
        "source": source,
        "prompt_source": prompt_source,
        "binary": binary,
        "notes": notes,
        "command_preview": base[:280],
    }
