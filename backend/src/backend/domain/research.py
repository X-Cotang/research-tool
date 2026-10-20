from __future__ import annotations

import asyncio
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from backend.core.config import (
    COMMAND_CODE_BIN,
    DEFAULT_PRESET_ID,
    RESEARCH_DIR,
    RESEARCH_TIMEOUT,
    default_research_command,
    get_preset,
    infer_preset_id,
    resolve_binary_path,
)
from backend.core.db import db, get_setting, row_to_dict, set_setting, utcnow
from backend.domain.language_profile import build_language_profile
from backend.domain.logs import log_hub
from backend.domain.prompt_enrich import enrich_research_command
from backend.domain.sast_scan import run_sast_scan

LogFn = Callable[[str], None]
NOTES_NAME = "RESEARCH_NOTES.md"
ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|].*?(?:\x07|\x1b\\))")


class ResearchError(Exception):
    pass


def saved_research_preset() -> str:
    preset = (get_setting("research_preset") or DEFAULT_PRESET_ID).strip()
    if preset == "custom" or get_preset(preset):
        return preset
    return DEFAULT_PRESET_ID


def saved_research_command() -> str:
    saved = get_setting("research_command").strip()
    if saved:
        return saved
    return default_research_command(saved_research_preset())


def save_research_settings(command: str, preset_id: str | None = None) -> tuple[str, str]:
    command = command.strip()
    if not command:
        raise ResearchError("Research command cannot be empty.")
    resolved = (preset_id or "").strip() or infer_preset_id(command)
    if resolved != "custom" and not get_preset(resolved):
        resolved = infer_preset_id(command)
    set_setting("research_command", command)
    set_setting("research_preset", resolved)
    return command, resolved


def resolve_command_code() -> str:
    found = resolve_binary_path("command-code", COMMAND_CODE_BIN)
    if found:
        return found
    raise ResearchError(
        "command-code was not found on PATH. Install it or set COMMAND_CODE_BIN to the binary."
    )


def _ensure_token_group(parts: list[str], group: tuple[str, ...], insert_at: int) -> int:
    """Insert a flag group near the front if its leading token is missing."""
    if not group:
        return insert_at
    if group[0] in parts[1:]:
        return insert_at
    for offset, token in enumerate(group):
        parts.insert(insert_at + offset, token)
    return insert_at + len(group)


def parse_research_command(command: str) -> list[str]:
    parts = shlex.split(command.strip())
    if not parts:
        raise ResearchError("Research command is empty.")

    binary_name = Path(parts[0]).name
    preset_id = infer_preset_id(command)
    preset = get_preset(preset_id)
    configured = preset.get("default_bin") if preset else (
        COMMAND_CODE_BIN if binary_name in {"command-code", "commandcode", "cmdc"} else None
    )
    resolved = resolve_binary_path(binary_name, configured)
    if resolved:
        parts[0] = resolved

    if not preset:
        return parts

    insert_at = 1
    # Subcommands like `run` / `exec` must stay immediately after the binary.
    for group in preset.get("required_groups") or ():
        insert_at = _ensure_token_group(parts, tuple(group), insert_at)

    if preset_id == "command-code":
        lower = set(parts[1:])
        if "--yolo" not in lower and "--dangerously-skip-permissions" not in lower:
            parts.insert(1, "--yolo")

    return parts


def _clean_line(line: str) -> str | None:
    text = ANSI_RE.sub("", line).replace("\r", "").rstrip()
    if not text.strip():
        return None
    return text[:2000]


def _append_log(job_id: int, line: str) -> None:
    with db() as conn:
        row = conn.execute("SELECT log FROM jobs WHERE id = ?", (job_id,)).fetchone()
        current = row["log"] if row else ""
        conn.execute("UPDATE jobs SET log = ? WHERE id = ?", (current + line + "\n", job_id))
    log_hub.publish(job_id, {"type": "log", "line": line})


def _set_job(job_id: int, **fields: Any) -> None:
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with db() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
    payload = {"type": "status", **fields}
    log_hub.publish(job_id, payload)


def _set_project(project_id: int, **fields: Any) -> None:
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [project_id]
    with db() as conn:
        conn.execute(f"UPDATE projects SET {assignments} WHERE id = ?", values)


def clone_repo(clone_url: str, dest: Path, log: LogFn) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        log(f"Repo already present at {dest}; fetching latest.")
        _run_streamed(
            ["git", "-C", str(dest), "fetch", "--depth", "1", "origin"],
            dest,
            log,
            timeout=180,
        )
        subprocess.run(
            ["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return

    if dest.exists() and any(dest.iterdir()):
        raise ResearchError(f"Destination exists but is not a git clone: {dest}")

    log(f"Cloning {clone_url} into {dest}")
    _run_streamed(
        ["git", "clone", "--depth", "1", "--progress", clone_url, str(dest)],
        dest.parent,
        log,
        timeout=300,
    )


def _run_streamed(cmd: list[str], cwd: Path, log: LogFn, timeout: int) -> str:
    env = os.environ.copy()
    binary_dir = os.path.dirname(cmd[0])
    if binary_dir:
        env["PATH"] = binary_dir + os.pathsep + env.get("PATH", "")
    env.setdefault("CI", "1")
    env.setdefault("NO_COLOR", "1")
    env.setdefault("TERM", "dumb")
    env.setdefault("PYTHONUNBUFFERED", "1")

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    chunks: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            chunks.append(line)
            cleaned = _clean_line(line)
            if cleaned:
                log(cleaned)
            if sum(len(part) for part in chunks) > 400_000:
                chunks = chunks[-400:]
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise ResearchError(f"Command timed out after {timeout}s: {cmd[0]}") from exc
    output = "".join(chunks).strip()
    if code != 0:
        raise ResearchError(output[-4000:] or f"{cmd[0]} exited {code}")
    return output


def run_research_command(dest: Path, command: str, log: LogFn) -> str:
    cmd = parse_research_command(command)
    # Log the resolved argv briefly; full enriched prompt can be huge.
    display = command if len(command) < 500 else (command[:240] + " …")
    log(f"$ {display}")
    return _run_streamed(cmd, dest, log, timeout=RESEARCH_TIMEOUT)


def _compose_report(
    project: dict,
    analysis: str,
    command: str,
    *,
    profile: dict | None = None,
    sast_summary: str = "",
) -> str:
    languages = project.get("languages") or {}
    if isinstance(languages, dict) and languages:
        lang_line = ", ".join(languages.keys())
    else:
        lang_line = project.get("language") or "n/a"
    if profile and profile.get("primary"):
        lang_line = (
            f"{profile['primary']}"
            + (f" (+{', '.join(profile.get('languages', [])[1:4])})" if len(profile.get("languages") or []) > 1 else "")
            + f" · github/disk: {lang_line}"
        )
    topics = project.get("topics") or []
    topic_line = ", ".join(topics) if topics else "n/a"
    sections = [
        f"# Research notes — {project['full_name']}",
        "",
        f"- URL: {project.get('html_url')}",
        f"- Local path: `{project.get('local_path')}`",
        f"- Languages: {lang_line}",
        f"- Topics: {topic_line}",
        f"- Command: `{command[:300]}{'…' if len(command) > 300 else ''}`",
        "",
    ]
    if profile:
        sections.extend(
            [
                "## Language profile",
                "",
                f"- Primary: `{profile.get('primary')}`",
                f"- Focus: {profile.get('focus')}",
                f"- SAST packs: {', '.join(profile.get('semgrep_packs') or [])}",
                "",
            ]
        )
    if sast_summary.strip():
        sections.extend(["## SAST leads", "", sast_summary.strip(), ""])
    sections.extend(["## Analysis", "", analysis.strip() or "_No output captured._", ""])
    return "\n".join(sections)


async def run_research_job(job_id: int, project_id: int) -> None:
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
        job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
    if not project or not job:
        _set_job(job_id, status="error", error="Project not found", finished_at=utcnow())
        return

    command = (job.get("command") or saved_research_command()).strip()

    def log(line: str) -> None:
        _append_log(job_id, line)

    dest = RESEARCH_DIR / project["full_name"]
    try:
        _set_job(job_id, status="running")
        _set_project(project_id, research_status="running", last_job_id=job_id)
        await asyncio.to_thread(clone_repo, project["clone_url"], dest, log)
        _set_project(project_id, local_path=str(dest))
        project["local_path"] = str(dest)
        log_hub.publish(job_id, {"type": "meta", "local_path": str(dest)})

        profile = build_language_profile(project, dest)
        log(
            f"Language profile: primary={profile.get('primary')} "
            f"langs={','.join(profile.get('languages') or [])}"
        )

        sast = await asyncio.to_thread(run_sast_scan, dest, project, log, profile=profile)
        sast_summary = sast.summary_md if sast.summary_md else ""
        if sast.skipped_reason and not sast.findings:
            log(f"SAST skipped: {sast.skipped_reason}")

        enriched = enrich_research_command(command, profile, sast_summary)
        if enriched != command:
            log("Enriched research prompt with language focus + SAST leads.")
            command = enriched
            with db() as conn:
                conn.execute("UPDATE jobs SET command = ? WHERE id = ?", (command, job_id))

        notes = dest / NOTES_NAME
        before = notes.stat().st_mtime if notes.exists() else 0
        analysis = await asyncio.to_thread(run_research_command, dest, command, log)
        if notes.exists() and notes.stat().st_mtime > before:
            report = notes.read_text(encoding="utf-8", errors="replace")
            log(f"Using notes written by the research command: {notes}")
        else:
            report = _compose_report(
                project,
                analysis,
                command,
                profile=profile,
                sast_summary=sast_summary,
            )
            notes.write_text(report, encoding="utf-8")
            log(f"Wrote {notes}")

        finished = utcnow()
        _set_job(job_id, status="done", report=report, finished_at=finished)
        _set_project(
            project_id,
            research_status="done",
            local_path=str(dest),
            last_report=report,
            researched_at=finished,
            last_job_id=job_id,
        )
        log("Research job finished.")
        log_hub.publish(job_id, {"type": "done", "status": "done", "report": report})
        from backend.domain.runs import on_research_job_finished

        on_research_job_finished(job_id)
    except Exception as exc:
        message = str(exc)
        log(f"Error: {message}")
        _set_job(job_id, status="error", error=message, finished_at=utcnow())
        status = "cloned" if dest.exists() else "error"
        _set_project(project_id, research_status=status, local_path=str(dest) if dest.exists() else None)
        log_hub.publish(job_id, {"type": "done", "status": "error", "error": message})
        from backend.domain.runs import on_research_job_finished

        on_research_job_finished(job_id)
