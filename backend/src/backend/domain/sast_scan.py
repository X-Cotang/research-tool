from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.core.db import get_setting, set_setting
from backend.domain.language_profile import build_language_profile

LogFn = Callable[[str], None]
FINDINGS_NAME = "SAST_FINDINGS.md"
FINDINGS_JSON = "sast_findings.json"

SAST_KEYS = ("sast_enabled", "sast_tool", "sast_timeout")


@dataclass
class SastResult:
    tool: str
    packs: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    summary_md: str = ""
    skipped_reason: str = ""
    exit_code: int | None = None


def sast_enabled() -> bool:
    raw = (get_setting("sast_enabled") or os.getenv("SAST_ENABLED", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def sast_timeout() -> int:
    raw = (get_setting("sast_timeout") or os.getenv("SAST_TIMEOUT", "180")).strip()
    try:
        return max(30, min(int(raw), 900))
    except ValueError:
        return 180


def preferred_sast_tool() -> str:
    raw = (get_setting("sast_tool") or os.getenv("SAST_TOOL", "auto")).strip().lower()
    if raw in {"semgrep", "opengrep", "auto", "off"}:
        return raw
    return "auto"


def load_sast_settings() -> dict[str, Any]:
    resolved = resolve_sast_binary()
    return {
        "sast_enabled": sast_enabled(),
        "sast_tool": preferred_sast_tool(),
        "sast_timeout": sast_timeout(),
        "binary_available": bool(resolved),
        "resolved_tool": resolved[0] if resolved else None,
        "resolved_path": resolved[1] if resolved else None,
    }


def save_sast_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if "sast_enabled" in payload and payload["sast_enabled"] is not None:
        enabled = payload["sast_enabled"]
        if isinstance(enabled, bool):
            set_setting("sast_enabled", "1" if enabled else "0")
        else:
            text = str(enabled).strip().lower()
            set_setting("sast_enabled", "0" if text in {"0", "false", "no", "off"} else "1")
    if "sast_tool" in payload and payload["sast_tool"] is not None:
        tool = str(payload["sast_tool"]).strip().lower()
        if tool not in {"semgrep", "opengrep", "auto", "off"}:
            raise ValueError("sast_tool must be auto, semgrep, opengrep, or off")
        set_setting("sast_tool", tool)
    if "sast_timeout" in payload and payload["sast_timeout"] is not None:
        try:
            timeout = int(payload["sast_timeout"])
        except (TypeError, ValueError) as exc:
            raise ValueError("sast_timeout must be an integer") from exc
        set_setting("sast_timeout", str(max(30, min(timeout, 900))))
    return load_sast_settings()


def resolve_sast_binary(preference: str | None = None) -> tuple[str, str] | None:
    pref = (preference or preferred_sast_tool()).lower()
    if pref == "off":
        return None
    order = ["semgrep", "opengrep"] if pref == "auto" else [pref]
    if pref == "opengrep":
        order = ["opengrep", "semgrep"]
    for name in order:
        path = shutil.which(name)
        if path:
            return name, path
    return None


def _severity_rank(value: str) -> int:
    key = (value or "").upper()
    order = {"ERROR": 0, "CRITICAL": 0, "HIGH": 1, "WARNING": 2, "MEDIUM": 2, "INFO": 3, "LOW": 3}
    return order.get(key, 4)


def _parse_semgrep_json(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results") or []
    findings: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        extra = item.get("extra") or {}
        meta = extra.get("metadata") or {}
        severity = str(extra.get("severity") or meta.get("severity") or "WARNING")
        path = str(item.get("path") or "")
        start = (item.get("start") or {}) if isinstance(item.get("start"), dict) else {}
        line = int(start.get("line") or 0)
        message = str(extra.get("message") or item.get("check_id") or "finding")
        check_id = str(item.get("check_id") or "")
        snippet = ""
        if isinstance(extra.get("lines"), str):
            snippet = extra["lines"].strip()[:240]
        findings.append(
            {
                "rule": check_id,
                "severity": severity,
                "path": path,
                "line": line,
                "message": message[:400],
                "snippet": snippet,
            }
        )
    findings.sort(key=lambda f: (_severity_rank(f["severity"]), f["path"], f["line"]))
    return findings


def _summarize(findings: list[dict[str, Any]], *, limit: int = 25) -> str:
    if not findings:
        return "No static-analysis findings reported (or scan produced an empty set)."
    lines = [
        f"Static analysis reported {len(findings)} finding(s). "
        f"Showing top {min(limit, len(findings))} by severity — verify in source before trusting:",
        "",
    ]
    for idx, item in enumerate(findings[:limit], start=1):
        loc = item["path"]
        if item.get("line"):
            loc = f"{loc}:{item['line']}"
        lines.append(
            f"{idx}. [{item.get('severity', '?')}] {item.get('rule', '')} @ `{loc}` — {item.get('message', '')}"
        )
        if item.get("snippet"):
            lines.append(f"   `{item['snippet']}`")
    if len(findings) > limit:
        lines.append(f"… {len(findings) - limit} more omitted.")
    return "\n".join(lines)


def run_sast_scan(
    root: Path,
    project: dict[str, Any],
    log: LogFn,
    *,
    profile: dict[str, Any] | None = None,
) -> SastResult:
    if not sast_enabled():
        return SastResult(tool="off", skipped_reason="SAST disabled in settings")

    resolved = resolve_sast_binary()
    if not resolved:
        log("SAST: semgrep/opengrep not on PATH — skipping pre-scan.")
        return SastResult(tool="none", skipped_reason="semgrep/opengrep not installed")

    tool, binary = resolved
    profile = profile or build_language_profile(project, root)
    packs = list(profile.get("semgrep_packs") or ["p/security-audit", "p/secrets"])
    timeout = sast_timeout()

    json_path = root / FINDINGS_JSON
    # Prefer stdout JSON for portability across semgrep/opengrep versions.
    cmd = [binary, "scan", "--quiet", "--json"]
    for pack in packs:
        cmd.extend(["--config", pack])
    # Include INFO+; agent will triage. ERROR-only misses useful leads.
    cmd.extend(["--severity", "INFO"])
    cmd.append(".")

    log(f"SAST: {tool} for primary={profile.get('primary')} packs={','.join(packs)}")
    log(f"$ {' '.join(cmd)}")

    env = os.environ.copy()
    env.setdefault("CI", "1")
    env.setdefault("NO_COLOR", "1")
    try:
        completed = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log(f"SAST: timed out after {timeout}s")
        return SastResult(tool=tool, packs=packs, skipped_reason=f"timeout after {timeout}s")
    except OSError as exc:
        log(f"SAST: failed to start ({exc})")
        return SastResult(tool=tool, packs=packs, skipped_reason=str(exc))

    # Semgrep exits 1 when findings exist — that is success for our purposes.
    if completed.returncode not in {0, 1}:
        err = (completed.stderr or completed.stdout or "")[-800:]
        log(f"SAST: {tool} exited {completed.returncode}: {err}")
        return SastResult(
            tool=tool,
            packs=packs,
            exit_code=completed.returncode,
            skipped_reason=f"exit {completed.returncode}",
        )

    payload: dict[str, Any] = {}
    stdout = (completed.stdout or "").strip()
    if stdout.startswith("{"):
        try:
            payload = json.loads(stdout)
            json_path.write_text(stdout, encoding="utf-8")
        except json.JSONDecodeError:
            payload = {}
    elif json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            payload = {}

    findings = _parse_semgrep_json(payload) if isinstance(payload, dict) else []
    summary = _summarize(findings)
    md_path = root / FINDINGS_NAME
    md = "\n".join(
        [
            f"# SAST findings — {project.get('full_name', root.name)}",
            "",
            f"- Tool: `{tool}`",
            f"- Primary language: `{profile.get('primary')}`",
            f"- Packs: {', '.join(packs)}",
            "",
            summary,
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    log(f"SAST: {len(findings)} finding(s); wrote {md_path.name}")
    return SastResult(
        tool=tool,
        packs=packs,
        findings=findings,
        summary_md=summary,
        exit_code=completed.returncode,
    )
