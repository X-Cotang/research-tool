"""Evidence-backed lessons. A lesson without a job id in its evidence is rejected."""

from __future__ import annotations

import re
from typing import Any

import httpx

from backend.core.db import db, row_to_dict, utcnow
from backend.domain.ai_settings import get_ai_setting
from backend.master.harness import propose_component

_EXPERIENCE = re.compile(r"<experience>(.*?)</experience>", re.S | re.I)
_PATCH = re.compile(r"<patch>(.*?)</patch>", re.S | re.I)
_FIELD = re.compile(r"^([a-z_]+):\s*(.+)$", re.I | re.M)
_JOB_REF = re.compile(r"job\s*#?\s*(\d+)", re.I)


def list_experiences(*, domain: str | None = None, limit: int = 40) -> list[dict]:
    with db() as conn:
        if domain:
            rows = conn.execute(
                """
                SELECT * FROM experiences
                WHERE domain = ? AND status = 'active'
                ORDER BY id DESC LIMIT ?
                """,
                (domain.lower(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM experiences WHERE status = 'active'
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [row_to_dict(r) for r in rows if row_to_dict(r)]


def lessons_for_languages(languages: list[str], *, limit: int = 4) -> list[dict]:
    domains = _normalize_domains(languages)
    if not domains:
        return list_experiences(limit=limit)
    found: list[dict] = []
    seen: set[int] = set()
    for domain in domains:
        for item in list_experiences(domain=domain, limit=limit):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            found.append(item)
            if len(found) >= limit:
                return found
    return found


def render_lessons(languages: list[str]) -> str:
    items = lessons_for_languages(languages)
    lines = ["# Experience library", ""]
    if not items:
        lines.append("No lessons yet for the current languages.")
        return "\n".join(lines)
    for item in items:
        lines.append(
            f"- [{item.get('domain')}] {item.get('cue')} → {item.get('lesson')} "
            f"(confidence {item.get('confidence')}; evidence: {item.get('evidence')})"
        )
    return "\n".join(lines)


def record_episode(
    *,
    summary: str,
    outcome: str,
    job_id: int | None = None,
    run_id: int | None = None,
    project_id: int | None = None,
    conversation_id: int | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO episodes (
                run_id, job_id, project_id, conversation_id, language,
                summary, outcome, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                job_id,
                project_id,
                conversation_id,
                (language or "").lower() or None,
                summary[:4000],
                outcome[:80],
                now,
            ),
        )
        row = row_to_dict(
            conn.execute("SELECT * FROM episodes WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return row or {}


def accept_lesson(
    *,
    domain: str,
    cue: str,
    lesson: str,
    evidence: str,
    confidence: str = "low",
    job_id: int | None = None,
    run_id: int | None = None,
) -> dict[str, Any] | None:
    """Store a lesson only when evidence cites a real job."""
    cue_t = (cue or "").strip()
    lesson_t = (lesson or "").strip()
    evidence_t = (evidence or "").strip()
    if not cue_t or not lesson_t or not evidence_t:
        return None
    if len(lesson_t) < 24:
        return None
    cited_ids = [int(m) for m in _JOB_REF.findall(evidence_t)]
    cited: int | None = None
    if job_id is not None and _job_exists(int(job_id)):
        cited = int(job_id)
        if not any(item == cited for item in cited_ids):
            evidence_t = f"{evidence_t} (job {cited})"
    else:
        cited = next((item for item in cited_ids if _job_exists(item)), None)
    if cited is None:
        return None
    domain_t = (domain or "general").strip().lower()[:40] or "general"
    conf = (confidence or "low").strip().lower()
    if conf not in {"high", "medium", "low"}:
        conf = "low"
    now = utcnow()
    with db() as conn:
        dup = conn.execute(
            """
            SELECT id FROM experiences
            WHERE domain = ? AND lesson = ? AND status = 'active'
            """,
            (domain_t, lesson_t),
        ).fetchone()
        if dup:
            return row_to_dict(
                conn.execute("SELECT * FROM experiences WHERE id = ?", (dup["id"],)).fetchone()
            )
        cur = conn.execute(
            """
            INSERT INTO experiences (
                domain, cue, lesson, evidence, confidence, status, job_id, run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (domain_t, cue_t[:500], lesson_t[:2000], evidence_t[:2000], conf, cited, run_id, now),
        )
        row = row_to_dict(
            conn.execute("SELECT * FROM experiences WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return row


async def reflect_on_job(job_id: int, *, run_id: int | None = None) -> dict[str, Any]:
    """Write an episode, then at most one lesson. Missing evidence becomes NO_ENTRY."""
    context = _job_context(job_id)
    if not context:
        return {"stored": False, "reason": "job not found"}
    record_episode(
        summary=context["summary"],
        outcome=context["outcome"],
        job_id=job_id,
        run_id=run_id or context.get("run_id"),
        project_id=context.get("project_id"),
        conversation_id=context.get("conversation_id"),
        language=context.get("language"),
    )
    raw = await _ask_reflector(context)
    if not raw or "NO_ENTRY" in raw.upper() and "<experience>" not in raw.lower():
        return {"stored": False, "reason": "NO_ENTRY", "episode": True}
    parsed = _parse_experience(raw)
    if not parsed:
        return {"stored": False, "reason": "unparsed", "episode": True}
    lesson = accept_lesson(
        domain=parsed.get("domain") or context.get("language") or "general",
        cue=parsed.get("cue", ""),
        lesson=parsed.get("lesson", ""),
        evidence=parsed.get("evidence", ""),
        confidence=parsed.get("confidence", "low"),
        job_id=job_id,
        run_id=run_id or context.get("run_id"),
    )
    patch = _parse_patch(raw)
    proposed = None
    if patch and lesson:
        try:
            proposed = propose_component(
                patch["component"],
                patch["content"],
                note=f"candidate from job {job_id}",
            )
        except ValueError as exc:
            proposed = {"error": str(exc)}
    return {
        "stored": bool(lesson),
        "lesson": lesson,
        "harness_candidate": proposed,
        "reason": None if lesson else "rejected",
    }


def _job_exists(job_id: int) -> bool:
    with db() as conn:
        row = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row is not None


def _job_context(job_id: int) -> dict[str, Any] | None:
    with db() as conn:
        job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
        if not job:
            return None
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (job["project_id"],)).fetchone()
        )
        findings = conn.execute(
            """
            SELECT status, COUNT(*) AS c FROM findings
            WHERE project_id = ? GROUP BY status
            """,
            (job["project_id"],),
        ).fetchall()
    finding_bits = ", ".join(f"{r['status']}={r['c']}" for r in findings) or "none"
    language = ((project or {}).get("language") or "general").lower()
    outcome = job.get("status") or "unknown"
    summary = (
        f"job {job_id} {outcome} on {(project or {}).get('full_name')} "
        f"language={language} findings({finding_bits})"
    )
    if job.get("error"):
        summary += f" error={str(job['error'])[:300]}"
    return {
        "job_id": job_id,
        "run_id": job.get("run_id"),
        "project_id": job.get("project_id"),
        "conversation_id": job.get("conversation_id"),
        "language": language,
        "outcome": outcome,
        "summary": summary,
        "report_excerpt": ((job.get("report") or (project or {}).get("last_report") or "")[:1500]),
    }


async def _ask_reflector(context: dict[str, Any]) -> str:
    base_url = get_ai_setting("ai_base_url").rstrip("/")
    api_key = get_ai_setting("ai_api_key")
    model = get_ai_setting("ai_model")
    if not base_url or not api_key or not model:
        return "NO_ENTRY"
    prompt = (
        "You reflect on one finished research job. Write at most one transferable lesson, "
        "or the single line NO_ENTRY.\n"
        "The cue is the shape of the situation, not this repository's name. "
        "The lesson is a checkable operation and must name a harness component "
        "(system_prompt, guardrails, tool_guidance, memory, skill, or prompt). "
        "Evidence must cite the job id. Adoption alone is not evidence. "
        "If you also want a harness change, add a patch. It stays a candidate until a person adopts it.\n\n"
        f"Record:\n{context['summary']}\n\nNotes excerpt:\n{context.get('report_excerpt') or '(none)'}\n\n"
        "Format:\n<experience>\n"
        "cue: ...\nlesson: ...\nevidence: job <id> ...\nconfidence: low|medium|high\n"
        f"domain: {context.get('language') or 'general'}\n</experience>\n"
        "<patch>\ncomponent: tool_guidance\ncontent: full replacement text\n</patch>"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
            return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except (httpx.HTTPError, ValueError, KeyError):
        return "NO_ENTRY"


def _parse_experience(text: str) -> dict[str, str] | None:
    match = _EXPERIENCE.search(text or "")
    if not match:
        return None
    fields = {m.group(1).lower(): m.group(2).strip() for m in _FIELD.finditer(match.group(1))}
    if not fields.get("cue") or not fields.get("lesson") or not fields.get("evidence"):
        return None
    return fields


def _parse_patch(text: str) -> dict[str, str] | None:
    match = _PATCH.search(text or "")
    if not match:
        return None
    fields = {m.group(1).lower(): m.group(2).strip() for m in _FIELD.finditer(match.group(1))}
    component = fields.get("component", "")
    content = fields.get("content", "")
    if component not in {"system_prompt", "guardrails", "tool_guidance", "memory"} or not content:
        return None
    return {"component": component, "content": content}


def _normalize_domains(languages: list[str]) -> list[str]:
    aliases = {
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
        "typescript": "javascript",
        "ts": "javascript",
        "node": "javascript",
        "go": "go",
        "golang": "go",
        "java": "java",
        "c#": "csharp",
        "csharp": "csharp",
        "cs": "csharp",
    }
    out: list[str] = []
    for lang in languages:
        key = aliases.get((lang or "").strip().lower(), (lang or "").strip().lower())
        if key and key not in out:
            out.append(key)
    return out
