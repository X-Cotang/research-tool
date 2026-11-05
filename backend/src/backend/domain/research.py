from __future__ import annotations

import asyncio
import os
import pty
import re
import select
import shlex
import subprocess
import time
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


def _clean_line(line: str, limit: int | None = 2000) -> str | None:
    text = ANSI_RE.sub("", line).replace("\r", "").rstrip()
    if not text.strip():
        return None
    if limit is not None and len(text) > limit:
        return text[:limit]
    return text


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


def _run_streamed(
    cmd: list[str],
    cwd: Path,
    log: LogFn,
    timeout: int,
    progress: Callable[[str | None, str | None], None] | None = None,
) -> str:
    """Run a CLI and emit each event as it is printed.

    A pseudo-terminal makes Node flush every line. Piped stdout stays blocked
    until the process exits, which is why a `--print` run looked idle.
    """
    from backend.domain.cli_stream import interpret_cli_line

    env = os.environ.copy()
    binary_dir = os.path.dirname(cmd[0])
    if binary_dir:
        env["PATH"] = binary_dir + os.pathsep + env.get("PATH", "")
    env.setdefault("CI", "1")
    env.setdefault("NO_COLOR", "1")
    env["TERM"] = "dumb"
    env.setdefault("PYTHONUNBUFFERED", "1")

    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        start_new_session=True,
    )
    os.close(slave_fd)

    chunks: list[str] = []
    final_text = ""
    pending = ""
    activity: str | None = "starting"
    session_id: str | None = None
    started = time.monotonic()
    last_output = started
    last_heartbeat = started
    deadline = started + timeout

    def note(next_activity: str | None, next_session: str | None) -> None:
        nonlocal activity, session_id
        changed = False
        if next_session and next_session != session_id:
            session_id = next_session
            changed = True
        if next_activity and next_activity != activity:
            activity = next_activity
            changed = True
        if changed and progress:
            progress(activity, session_id)

    def flush_delta(force: bool = False) -> None:
        nonlocal pending
        text = " ".join(pending.split())
        if not text:
            pending = ""
            return
        if not force and len(text) < 180:
            return
        pending = ""
        log(f"[cli] {_short_progress(text)}")
        note("writing", session_id)

    def handle_line(line: str) -> None:
        nonlocal final_text, pending, last_output
        last_output = time.monotonic()
        cleaned = _clean_line(line, limit=None)
        if not cleaned:
            return
        decision = interpret_cli_line(cleaned)
        if decision.get("session_id") or decision.get("activity"):
            note(decision.get("activity"), decision.get("session_id"))
        if decision.get("final_text"):
            final_text = str(decision["final_text"])
        kind = decision.get("kind")
        if kind == "delta":
            pending += str(decision.get("text") or "")
            flush_delta(False)
            return
        if kind == "skip":
            return
        flush_delta(True)
        text = str(decision.get("text") or "")
        if not text:
            return
        chunks.append(text)
        log(text[:2000])
        if sum(len(part) for part in chunks) > 400_000:
            del chunks[:-400]

    try:
        buffer = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(cmd, timeout)
            readable, _, _ = select.select([master_fd], [], [], min(5.0, remaining))
            now = time.monotonic()
            if readable:
                try:
                    data = os.read(master_fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer or "\r" in buffer:
                    cut = len(buffer)
                    for sep in ("\n", "\r"):
                        pos = buffer.find(sep)
                        if pos != -1:
                            cut = min(cut, pos)
                    line, buffer = buffer[:cut], buffer[cut + 1 :]
                    handle_line(line)
            elif process.poll() is not None:
                buffer += _drain_fd(master_fd)
                break
            elif now - last_output >= 12 and now - last_heartbeat >= 12:
                elapsed = int(now - started)
                log(f"[cli] still running · {elapsed}s · {activity or 'waiting for output'}")
                last_heartbeat = now
                if progress:
                    progress(activity, session_id)
        if buffer.strip():
            handle_line(buffer)
        flush_delta(True)
        code = process.wait(timeout=10)
    except subprocess.TimeoutExpired as exc:
        _kill_process_group(process)
        raise ResearchError(f"Command timed out after {timeout}s: {cmd[0]}") from exc
    finally:
        os.close(master_fd)

    output = final_text.strip() or "\n".join(chunks).strip()
    if code != 0:
        raise ResearchError(output[-4000:] or f"{cmd[0]} exited {code}")
    return output


def _drain_fd(fd: int) -> str:
    parts: list[str] = []
    while True:
        readable, _, _ = select.select([fd], [], [], 0)
        if not readable:
            break
        try:
            data = os.read(fd, 65536)
        except OSError:
            break
        if not data:
            break
        parts.append(data.decode("utf-8", errors="replace"))
    return "".join(parts)


def _short_progress(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > 500:
        return text[:499] + "…"
    return text


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, 15)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass


def run_research_command(
    dest: Path,
    command: str,
    log: LogFn,
    progress: Callable[[str | None, str | None], None] | None = None,
) -> str:
    from backend.domain.worker_command import looks_like_cli

    if not looks_like_cli(command):
        preview = (command or "").strip().split(" ", 1)[0][:80]
        raise ResearchError(
            "Research command is not a CLI invocation. "
            f"The first token is {preview!r}. Pass a preset plus a prompt, "
            "or a command that starts with an installed binary such as command-code, "
            "opencode, claude, codex, freebuff, or qoder."
        )
    try:
        cmd = parse_research_command(command)
    except ValueError as exc:
        raise ResearchError(f"Could not parse the research command: {exc}") from exc
    binary = cmd[0]
    if not Path(binary).exists() and not resolve_binary_path(Path(binary).name):
        raise ResearchError(
            f"CLI binary was not found: {binary}. "
            "Install it or choose another preset from list_presets."
        )
    # Log the resolved argv briefly; full enriched prompt can be huge.
    display = command if len(command) < 500 else (command[:240] + " …")
    log(f"$ {display}")
    try:
        return _run_streamed(cmd, dest, log, timeout=RESEARCH_TIMEOUT, progress=progress)
    except FileNotFoundError as exc:
        missing = getattr(exc, "filename", None) or binary
        raise ResearchError(f"CLI binary was not found: {missing}") from exc


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
    step = "prepare"

    def log(line: str) -> None:
        _append_log(job_id, line)

    def enter(name: str, detail: str = "") -> None:
        nonlocal step
        step = name
        line = f"[step:{name}]"
        if detail:
            line = f"{line} {detail}"
        log(line)

    dest = RESEARCH_DIR / project["full_name"]
    try:
        enter("prepare", project.get("full_name") or str(project_id))
        _set_job(job_id, status="running", error_step=step)
        _set_project(project_id, research_status="running", last_job_id=job_id)

        enter("clone", project.get("clone_url") or "")
        await asyncio.to_thread(clone_repo, project["clone_url"], dest, log)
        _set_project(project_id, local_path=str(dest))
        project["local_path"] = str(dest)
        log_hub.publish(job_id, {"type": "meta", "local_path": str(dest)})

        enter("language_profile")
        profile = build_language_profile(project, dest)
        log(
            f"Language profile: primary={profile.get('primary')} "
            f"langs={','.join(profile.get('languages') or [])}"
        )

        enter("sast", profile.get("primary") or "")
        sast = await asyncio.to_thread(run_sast_scan, dest, project, log, profile=profile)
        sast_summary = sast.summary_md if sast.summary_md else ""
        if sast.skipped_reason and not sast.findings:
            log(f"SAST skipped: {sast.skipped_reason}")

        enter("compose_prompt")
        enriched = enrich_research_command(command, profile, sast_summary)
        if enriched != command:
            log("Enriched research prompt with language focus + SAST leads.")
            command = enriched
            with db() as conn:
                conn.execute("UPDATE jobs SET command = ? WHERE id = ?", (command, job_id))

        notes = dest / NOTES_NAME
        before = notes.stat().st_mtime if notes.exists() else 0
        enter("research_cli")

        def on_progress(activity: str | None, session_id: str | None) -> None:
            fields: dict[str, Any] = {}
            if activity:
                fields["cli_activity"] = activity[:240]
            if session_id:
                fields["cli_session_id"] = session_id
            if fields:
                _set_job(job_id, **fields)
            if session_id:
                _set_project(project_id, cli_session_id=session_id)

        analysis = await asyncio.to_thread(
            run_research_command, dest, command, log, on_progress
        )
        enter("write_report")
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
        enter("finish")
        _set_job(job_id, status="done", report=report, error_step="", finished_at=finished)
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
        message = f"[{step}] {exc}"
        log(f"Error at step {step}: {exc}")
        _set_job(
            job_id,
            status="error",
            error=message,
            error_step=step,
            finished_at=utcnow(),
        )
        fields: dict[str, Any] = {"research_status": "error", "last_job_id": job_id}
        if dest.exists():
            fields["local_path"] = str(dest)
        _set_project(project_id, **fields)
        log_hub.publish(
            job_id,
            {"type": "done", "status": "error", "error": message, "error_step": step},
        )
        from backend.domain.runs import on_research_job_finished

        on_research_job_finished(job_id)
