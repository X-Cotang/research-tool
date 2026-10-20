from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.core.config import RESEARCH_DIR
from backend.core.db import db, row_to_dict, utcnow

HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
SEVERITY_HINT = re.compile(r"\b(critical|high|medium|low)\b", re.I)
CWE_RE = re.compile(r"\bCWE-(\d+)\b", re.I)
FILE_LINE_RE = re.compile(
    r"(?P<path>(?:[\w./\\-]+\.(?:py|js|ts|tsx|jsx|go|java|cs|rb|php|rs|c|cpp|h)))"
    r"(?:\s*[:#]\s*(?P<line>\d+))?",
    re.I,
)


def list_findings(*, project_id: int | None = None, limit: int = 200) -> list[dict]:
    with db() as conn:
        if project_id is not None:
            rows = conn.execute(
                """
                SELECT * FROM findings WHERE project_id = ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM findings ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [row_to_dict(r) for r in rows if row_to_dict(r)]


def get_finding(finding_id: int) -> dict | None:
    with db() as conn:
        return row_to_dict(
            conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        )


def patch_finding(finding_id: int, **fields: Any) -> dict | None:
    allowed = {"title", "severity", "cwe", "file_path", "line_start", "description", "status", "evidence"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_finding(finding_id)
    updates["updated_at"] = utcnow()
    assignments = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [finding_id]
    with db() as conn:
        conn.execute(f"UPDATE findings SET {assignments} WHERE id = ?", values)
        return row_to_dict(
            conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        )


def parse_research_notes(text: str) -> list[dict[str, Any]]:
    """Naive parse: each markdown heading becomes a finding candidate."""
    findings: list[dict[str, Any]] = []
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return findings
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if title.lower().startswith("research notes"):
            continue
        if title.lower() in {"analysis", "language profile", "sast leads"}:
            continue
        blob = f"{title}\n{body[:800]}"
        sev = "medium"
        sev_match = SEVERITY_HINT.search(blob)
        if sev_match:
            sev = sev_match.group(1).lower()
        cwe = None
        cwe_match = CWE_RE.search(blob)
        if cwe_match:
            cwe = f"CWE-{cwe_match.group(1)}"
        file_path = None
        line_start = None
        loc = FILE_LINE_RE.search(blob)
        if loc:
            file_path = loc.group("path")
            if loc.group("line"):
                line_start = int(loc.group("line"))
        findings.append(
            {
                "title": title[:500],
                "severity": sev,
                "cwe": cwe,
                "file_path": file_path,
                "line_start": line_start,
                "description": body[:8000],
                "evidence": body[:12000],
            }
        )
    return findings


def parse_project_findings(project_id: int) -> dict[str, Any]:
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        )
    if not project:
        raise ValueError("Project not found")
    notes_text = (project.get("last_report") or "").strip()
    path = project.get("local_path")
    if path:
        notes_path = Path(path) / "RESEARCH_NOTES.md"
    elif project.get("full_name"):
        notes_path = RESEARCH_DIR / project["full_name"] / "RESEARCH_NOTES.md"
    else:
        notes_path = None
    if notes_path and notes_path.is_file():
        try:
            notes_text = notes_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    parsed = parse_research_notes(notes_text)
    now = utcnow()
    inserted: list[dict] = []
    with db() as conn:
        for item in parsed:
            cur = conn.execute(
                """
                INSERT INTO findings (
                    project_id, title, severity, cwe, file_path, line_start,
                    description, evidence, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
                """,
                (
                    project_id,
                    item["title"],
                    item["severity"],
                    item.get("cwe"),
                    item.get("file_path"),
                    item.get("line_start"),
                    item["description"],
                    item["evidence"],
                    now,
                    now,
                ),
            )
            row = row_to_dict(
                conn.execute("SELECT * FROM findings WHERE id = ?", (cur.lastrowid,)).fetchone()
            )
            if row:
                inserted.append(row)
    return {"project_id": project_id, "parsed_count": len(parsed), "findings": inserted}
