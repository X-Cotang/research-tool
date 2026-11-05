from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from backend.core.db import db, row_to_dict
from backend.domain.findings import list_findings, patch_finding
from backend.domain.jobs import get_job_snapshot, queue_research
from backend.domain.prompt_suggest import suggest_prompt
from backend.domain.runs import queue_research_batch
from backend.master.experience import list_experiences
from backend.master.harness import adopt_component, propose_component, rollback_component
from backend.master.memory import build_working_memory

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "workspace_status",
            "description": "Current jobs, runs, finding counts, and last org. Call this before guessing progress.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": (
                "List stored projects. Skipped projects are hidden unless include_skipped is true. "
                "Filter by org, name query, language, research_status, min_stars, reported, "
                "false_positive, or hide_researched."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "org": {"type": "string", "description": "GitHub org or user login."},
                    "query": {"type": "string", "description": "Substring of owner/repo or description."},
                    "language": {"type": "string"},
                    "research_status": {
                        "type": "string",
                        "description": "idle, queued, running, done, error, or cloned.",
                    },
                    "min_stars": {"type": "integer"},
                    "include_skipped": {
                        "type": "boolean",
                        "description": "Include projects the user has skipped. Default false.",
                    },
                    "skipped_only": {"type": "boolean", "description": "Return only skipped projects."},
                    "reported": {"type": "boolean"},
                    "false_positive": {"type": "boolean"},
                    "hide_researched": {
                        "type": "boolean",
                        "description": "Omit projects that already have a finished report.",
                    },
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project",
            "description": "Get a project by id with recent jobs.",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_status",
            "description": "Get job status snapshot.",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_research_prompt",
            "description": "Suggest a tailored research prompt for a project.",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue_research",
            "description": (
                "Queue one research job. Identify the repo by full_name from resolve_projects. "
                "Write a project-specific prompt. Choose an installed preset from list_presets, "
                "or pass a full CLI command you composed (binary, flags, then the prompt). "
                "A prose sentence is never executed as a command."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "full_name": {
                        "type": "string",
                        "description": "owner/repo, for example microsoft/graphrag. Preferred over a guessed id.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Research brief for this repository. Not a shell command.",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Installed CLI preset id from list_presets.",
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra argv flags inserted after the CLI binary, such as a model flag.",
                    },
                    "command": {
                        "type": "string",
                        "description": "Optional full argv you wrote. Must start with a real CLI binary. Otherwise it is treated as the prompt.",
                    },
                    "conversation_id": {"type": "integer"},
                    "allow_skipped": {
                        "type": "boolean",
                        "description": "Queue even if the project is skipped. Only when the user explicitly asks.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_folder",
            "description": (
                "Count and list git checkouts still in the research folder. "
                "on_disk has not been deleted. unreported and reported split that set. "
                "dropped means the clone was removed and the library row remains. "
                "Use this when asked what is still cloned, not reported, or not deleted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string",
                        "enum": ["all", "on_disk", "unreported", "reported", "false_positive", "dropped"],
                        "description": "Which name list to include. Counts are always returned.",
                    },
                    "limit": {"type": "integer", "description": "Max names per list. Default 40."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_projects",
            "description": (
                "Mark stored projects. skipped=true keeps them in the catalog and out of research. "
                "skipped=false unskips. reported and false_positive match the library buttons. "
                "Pass owner/repo names. Do not invent ids."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "projects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "owner/repo names, for example microsoft/graphrag.",
                    },
                    "skipped": {"type": "boolean"},
                    "reported": {"type": "boolean"},
                    "false_positive": {"type": "boolean"},
                },
                "required": ["projects"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_projects",
            "description": (
                "Remove local data for stored projects. mode=clone drops the checkout and keeps the report. "
                "mode=full deletes the project, jobs, and clone, and requires confirm=true. "
                "Use this only when the user asked to drop a clone or delete a project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "projects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "owner/repo names.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["clone", "full"],
                        "description": "clone keeps the library row and report. full wipes the project.",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Required for mode=full.",
                    },
                },
                "required": ["projects"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "continue_research",
            "description": (
                "Reopen a finished CLI session and ask it to continue. "
                "command-code and qoder run `--resume {cli_session_id}` and then exit again. "
                "Pass the job id from get_job_status. If that job is still running, the note waits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer", "description": "Finished or running research job."},
                    "full_name": {
                        "type": "string",
                        "description": "owner/repo. Used to find the latest job when job_id is omitted.",
                    },
                    "message": {
                        "type": "string",
                        "description": "What the CLI should do next in the resumed session.",
                    },
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_org",
            "description": "Discover and score GitHub org/user repositories for research.",
            "parameters": {
                "type": "object",
                "properties": {"org_url": {"type": "string"}},
                "required": ["org_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_skills",
            "description": "Search skills by query string.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_skill",
            "description": "Get skill by slug.",
            "parameters": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_prompts",
            "description": "Search stored prompts.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose_research_plan",
            "description": "Compose a simple JSON research plan for project ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_ids": {"type": "array", "items": {"type": "integer"}},
                    "skill_slug": {"type": "string"},
                    "prompt_slug": {"type": "string"},
                },
                "required": ["project_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue_research_batch",
            "description": (
                "Queue research for several repositories. Pass projects[] with full_name so ids cannot be mixed up. "
                "Each item may have its own prompt, preset, extra_args, and command. "
                "Shared prompt/preset apply only when an item does not set its own."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "projects": {
                        "type": "array",
                        "description": "Preferred. Each item is a full_name string or an object with full_name plus optional prompt, preset, extra_args, and command.",
                        "items": {"type": "object"},
                    },
                    "project_ids": {"type": "array", "items": {"type": "integer"}},
                    "expect_full_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "If set, queueing is refused unless the resolved repos match these owner/repo names exactly.",
                    },
                    "conversation_id": {"type": "integer"},
                    "skill_slug": {"type": "string"},
                    "prompt_slug": {"type": "string"},
                    "prompt": {
                        "type": "string",
                        "description": "Shared research brief. Not a shell command. Per-project prompt overrides this.",
                    },
                    "preset": {
                        "type": "string",
                        "description": "Shared CLI preset id from list_presets. Per-project preset overrides this.",
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Shared extra CLI flags.",
                    },
                    "command": {
                        "type": "string",
                        "description": "Optional shared full CLI argv. Must start with a real binary.",
                    },
                    "allow_skipped": {
                        "type": "boolean",
                        "description": "Include skipped projects. Default false, so skipped repos are ignored.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_projects",
            "description": "Resolve owner/repo names to stored project ids. Call this before queueing. Do not guess ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Full names such as microsoft/graphrag, or a unique repo name.",
                    }
                },
                "required": ["names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_presets",
            "description": "List CLI presets and whether each binary is installed. Choose one before queueing research.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_findings",
            "description": "List findings optionally filtered by project_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_finding_status",
            "description": "Update finding status or severity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "finding_id": {"type": "integer"},
                    "status": {"type": "string"},
                    "severity": {"type": "string"},
                },
                "required": ["finding_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_experiences",
            "description": "List active lessons, optionally for one language domain.",
            "parameters": {
                "type": "object",
                "properties": {"domain": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_harness_edit",
            "description": "Store a candidate harness component. Does not activate it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": ["system_prompt", "guardrails", "tool_guidance", "memory"],
                    },
                    "content": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adopt_harness_edit",
            "description": "Activate a candidate harness component. Only when the user asks.",
            "parameters": {
                "type": "object",
                "properties": {"component_id": {"type": "integer"}},
                "required": ["component_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rollback_harness",
            "description": "Restore the previous active version of a harness component.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": ["system_prompt", "guardrails", "tool_guidance", "memory"],
                    }
                },
                "required": ["name"],
            },
        },
    },
]


def _slim_project(project: dict | None) -> dict | None:
    if not project:
        return None
    description = project.get("description") or ""
    return {
        "id": project.get("id"),
        "full_name": project.get("full_name"),
        "language": project.get("language"),
        "stars": project.get("stars"),
        "research_score": project.get("research_score"),
        "research_status": project.get("research_status"),
        "skipped": bool(project.get("skipped")),
        "reported": bool(project.get("reported")),
        "false_positive": bool(project.get("false_positive")),
        "description": description[:180],
        "html_url": project.get("html_url"),
        "last_job_id": project.get("last_job_id"),
    }


def _slim_job(job: dict | None) -> dict | None:
    if not job:
        return None
    log = job.get("log") or ""
    lines = [line for line in log.splitlines() if line.strip()]
    report = job.get("report") or ""
    return {
        "id": job.get("id"),
        "project_id": job.get("project_id"),
        "status": job.get("status"),
        "error": job.get("error"),
        "error_step": job.get("error_step"),
        "cli_session_id": job.get("cli_session_id"),
        "cli_activity": job.get("cli_activity"),
        "command_preview": (job.get("command") or "")[:240],
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
        "log_lines": len(lines),
        "log_tail": "\n".join(lines[-40:]),
        "has_report": bool(report.strip()),
        "report_preview": report[:2000],
    }


async def _list_projects(args: dict) -> Any:
    from backend.domain.project_actions import list_managed_projects

    return list_managed_projects(
        org=args.get("org"),
        query=args.get("query"),
        language=args.get("language"),
        research_status=args.get("research_status"),
        min_stars=args.get("min_stars"),
        include_skipped=bool(args.get("include_skipped")),
        skipped_only=bool(args.get("skipped_only")),
        reported=_optional_bool(args.get("reported")),
        false_positive=_optional_bool(args.get("false_positive")),
        hide_researched=bool(args.get("hide_researched")),
        limit=int(args.get("limit") or 40),
    )


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


async def _get_project(args: dict) -> Any:
    pid = int(args["project_id"])
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        )
        jobs = conn.execute(
            "SELECT * FROM jobs WHERE project_id = ? ORDER BY id DESC LIMIT 5",
            (pid,),
        ).fetchall()
    if not project:
        return {"error": "not found"}
    return {
        "project": _slim_project(project),
        "jobs": [_slim_job(row_to_dict(j)) for j in jobs],
    }


async def _get_job_status(args: dict) -> Any:
    snap = get_job_snapshot(int(args["job_id"]))
    if not snap:
        return {"error": "not found"}
    project = snap.get("project") or {}
    return {
        "job": _slim_job(snap.get("job")),
        "project": {
            "id": project.get("id"),
            "full_name": project.get("full_name"),
            "research_status": project.get("research_status"),
            "has_report": bool((project.get("last_report") or "").strip()),
        },
    }


async def _suggest_research_prompt(args: dict) -> Any:
    pid = int(args["project_id"])
    with db() as conn:
        project = row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        )
    if not project:
        return {"error": "not found"}
    return await suggest_prompt(project)


async def _workspace_status(_args: dict) -> Any:
    return build_working_memory()


async def _continue_research_tool(args: dict) -> Any:
    from backend.domain.supervisor import queue_followup

    message = str(args.get("message") or "").strip()
    if not message:
        return {"error": "Pass a message describing what the CLI should do next."}
    job_id = args.get("job_id")
    full_name = str(args.get("full_name") or "").strip()
    with db() as conn:
        if not job_id and full_name:
            row = conn.execute(
                """
                SELECT j.id FROM jobs j
                JOIN projects p ON p.id = j.project_id
                WHERE lower(p.full_name) = lower(?)
                ORDER BY j.id DESC LIMIT 1
                """,
                (full_name,),
            ).fetchone()
            if not row:
                return {"error": f"No research job found for {full_name}."}
            job_id = row["id"]
        if not job_id:
            return {"error": "Pass job_id or full_name."}
        job = row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (int(job_id),)).fetchone())
    if not job:
        return {"error": "Job not found."}
    try:
        result = queue_followup(int(job_id), message)
    except ValueError as exc:
        return {"error": str(exc)}
    result["cli_session_id"] = job.get("cli_session_id")
    return result


async def _queue_research_tool(args: dict) -> Any:
    from backend.domain.project_lookup import resolve_research_targets
    from backend.domain.worker_command import WorkerCommandError, compose_worker_command

    conversation_id = args.get("conversation_id")
    prompt_text = args.get("prompt")
    if not prompt_text and args.get("command") and not str(args.get("preset") or ""):
        # Older turns passed the brief in `command`. compose_worker_command
        # keeps real CLIs and rewrites prose into the prompt.
        prompt_text = None
    try:
        cmd, meta = compose_worker_command(
            prompt=prompt_text,
            preset_id=args.get("preset"),
            command=args.get("command"),
            extra_args=list(args.get("extra_args") or []),
        )
    except WorkerCommandError as exc:
        return {"error": str(exc)}

    spec: dict[str, Any] = {}
    if args.get("project_id") not in (None, ""):
        spec["project_id"] = int(args["project_id"])
    if args.get("full_name"):
        spec["full_name"] = args["full_name"]
    resolved = resolve_research_targets(None, [spec] if spec else None)
    if resolved.get("error"):
        return resolved
    target = (resolved.get("targets") or [None])[0]
    if not target:
        return {"error": "Pass project_id or full_name."}
    if target.get("skipped") and not args.get("allow_skipped"):
        return {
            "error": (
                f"{target.get('full_name')} is skipped, so it was not queued. "
                "Unskip it with update_projects, or pass allow_skipped only if the user asked to research it anyway."
            ),
            "full_name": target.get("full_name"),
            "skipped": True,
        }

    with db() as conn:
        job, created = queue_research(
            conn,
            int(target["project_id"]),
            cmd,
            conversation_id=int(conversation_id) if conversation_id else None,
        )
    return {
        "created": created,
        "project_id": target["project_id"],
        "full_name": target["full_name"],
        "job_id": job["id"] if job else None,
        "start": bool(created and job),
        "preset": meta.get("preset"),
        "binary": meta.get("binary"),
        "prompt_source": meta.get("prompt_source"),
        "notes": meta.get("notes"),
        "command_preview": meta.get("command_preview"),
    }


async def _scan_org(args: dict) -> Any:
    from backend.api.orgs import ScanRequest, scan

    org_url = (args.get("org_url") or "").strip()
    if not org_url:
        return {"error": "org_url is required"}
    try:
        result = await scan(ScanRequest(org_url=org_url))
    except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
        return {"error": str(exc)}
    return {
        "org": result.get("organization") or result.get("org"),
        "added": result.get("added_count") or result.get("result_count"),
        "projects": (result.get("projects") or [])[:20],
        "result": {k: result.get(k) for k in ("login", "added_count", "result_count", "exhausted") if k in result},
    }


async def _search_skills(args: dict) -> Any:
    q = (args.get("q") or "").strip()
    with db() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute(
                "SELECT id, slug, name, language, description FROM skills WHERE slug LIKE ? OR name LIKE ?",
                (like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, slug, name, language, description FROM skills ORDER BY name LIMIT 50"
            ).fetchall()
    return {"skills": [dict(r) for r in rows]}


async def _get_skill(args: dict) -> Any:
    slug = args["slug"]
    with db() as conn:
        skill = row_to_dict(
            conn.execute("SELECT * FROM skills WHERE slug = ?", (slug,)).fetchone()
        )
    return {"skill": skill}


async def _search_prompts(args: dict) -> Any:
    q = (args.get("q") or "").strip()
    with db() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute(
                """
                SELECT id, slug, name, language, vuln_class, description
                FROM prompts WHERE slug LIKE ? OR name LIKE ? OR vuln_class LIKE ?
                """,
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, slug, name, language, vuln_class, description FROM prompts ORDER BY name LIMIT 50"
            ).fetchall()
    return {"prompts": [dict(r) for r in rows]}


async def _compose_research_plan(args: dict) -> Any:
    plan: dict[str, Any] = {
        "project_ids": args.get("project_ids") or [],
        "skill_slug": args.get("skill_slug"),
        "prompt_slug": args.get("prompt_slug"),
        "prompt": "",
        "note": "This is a brief, not a shell command. Pass it as prompt when queueing, and choose a preset separately.",
    }
    with db() as conn:
        if plan["prompt_slug"]:
            row = conn.execute(
                "SELECT content FROM prompts WHERE slug = ?", (plan["prompt_slug"],)
            ).fetchone()
            if row:
                plan["prompt"] = row["content"]
        if plan["skill_slug"]:
            row = conn.execute(
                "SELECT content FROM skills WHERE slug = ?", (plan["skill_slug"],)
            ).fetchone()
            if row:
                plan["skill_hint"] = row["content"]
    return {"plan": plan}


async def _queue_research_batch_tool(args: dict) -> Any:
    projects = args.get("projects")
    expect = args.get("expect_full_names")
    project_ids = [int(x) for x in args.get("project_ids") or []]
    if not projects and not expect:
        return {
            "error": (
                "Pass projects with full_name (owner/repo). "
                "Do not queue a batch from project ids alone."
            )
        }
    if projects and project_ids:
        names: list[str] = []
        for item in projects:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict) and item.get("full_name"):
                names.append(str(item["full_name"]))
        if names:
            expect = names
    result = queue_research_batch(
        project_ids or None,
        conversation_id=args.get("conversation_id"),
        skill_slug=args.get("skill_slug"),
        prompt_slug=args.get("prompt_slug"),
        prompt=args.get("prompt"),
        preset_id=args.get("preset"),
        command=args.get("command"),
        extra_args=list(args.get("extra_args") or []),
        projects=projects,
        allow_skipped=bool(args.get("allow_skipped")),
        expect_full_names=expect,
    )
    if result.get("error"):
        return result
    return {
        "run_id": result["run"]["id"],
        "status": result["run"].get("status"),
        "queued": result.get("queued") or [],
        "ignored": result.get("ignored") or [],
        "tasks": [
            {
                "id": task.get("id"),
                "project_id": task.get("project_id"),
                "full_name": task.get("full_name"),
                "job_id": task.get("job_id"),
                "created": task.get("created"),
                "status": task.get("status"),
            }
            for task in result.get("tasks") or []
        ],
    }


async def _list_findings_tool(args: dict) -> Any:
    pid = args.get("project_id")
    limit = int(args.get("limit") or 50)
    return {"findings": list_findings(project_id=pid, limit=limit)}


async def _list_experiences_tool(args: dict) -> Any:
    return {"experiences": list_experiences(domain=args.get("domain"))}


async def _propose_harness_edit(args: dict) -> Any:
    try:
        row = propose_component(args["name"], args.get("content") or "", note=args.get("note") or "")
    except ValueError as exc:
        return {"error": str(exc)}
    return {"candidate": row, "status": "candidate"}


async def _adopt_harness_edit(args: dict) -> Any:
    try:
        row = adopt_component(int(args["component_id"]))
    except ValueError as exc:
        return {"error": str(exc)}
    return {"component": row}


async def _rollback_harness(args: dict) -> Any:
    try:
        row = rollback_component(args["name"])
    except ValueError as exc:
        return {"error": str(exc)}
    return {"component": row}


async def _update_finding_status(args: dict) -> Any:
    fid = int(args["finding_id"])
    fields = {k: args[k] for k in ("status", "severity") if k in args and args[k] is not None}
    finding = patch_finding(fid, **fields)
    return {"finding": finding}


async def _list_presets_tool(_args: dict) -> Any:
    from backend.core.config import list_presets

    presets = list_presets()
    return {
        "presets": [
            {
                "id": item["id"],
                "label": item["label"],
                "binary": item["binary"],
                "available": item["available"],
                "hint": item["hint"],
                "command_preview": (item.get("command") or "")[:180],
            }
            for item in presets
        ],
        "hint": "Pick an available preset. Write the prompt yourself for the target repository.",
    }


async def _research_folder_tool(args: dict) -> Any:
    from backend.domain.library import research_folder_summary

    return research_folder_summary(
        group=str(args.get("group") or "all"),
        limit=int(args.get("limit") or 40),
    )


async def _update_projects_tool(args: dict) -> Any:
    from backend.domain.project_actions import set_project_marks

    return set_project_marks(
        args.get("projects") or args.get("names"),
        skipped=args.get("skipped"),
        reported=args.get("reported"),
        false_positive=args.get("false_positive"),
    )


async def _remove_projects_tool(args: dict) -> Any:
    from backend.domain.project_actions import remove_managed_projects

    return remove_managed_projects(
        args.get("projects") or args.get("names"),
        mode=str(args.get("mode") or "clone"),
        confirm=bool(args.get("confirm")),
    )


async def _resolve_projects_tool(args: dict) -> Any:
    from backend.domain.project_lookup import resolve_project_query

    names = args.get("names") or args.get("projects") or []
    if isinstance(names, str):
        names = [names]
    if not names:
        return {"error": "Pass names, for example ['microsoft/graphrag']."}
    return resolve_project_query([str(name) for name in names])


HANDLERS: dict[str, ToolHandler] = {
    "workspace_status": _workspace_status,
    "list_projects": _list_projects,
    "research_folder": _research_folder_tool,
    "update_projects": _update_projects_tool,
    "remove_projects": _remove_projects_tool,
    "get_project": _get_project,
    "get_job_status": _get_job_status,
    "suggest_research_prompt": _suggest_research_prompt,
    "queue_research": _queue_research_tool,
    "continue_research": _continue_research_tool,
    "scan_org": _scan_org,
    "search_skills": _search_skills,
    "get_skill": _get_skill,
    "search_prompts": _search_prompts,
    "compose_research_plan": _compose_research_plan,
    "queue_research_batch": _queue_research_batch_tool,
    "list_findings": _list_findings_tool,
    "update_finding_status": _update_finding_status,
    "list_experiences": _list_experiences_tool,
    "list_presets": _list_presets_tool,
    "resolve_projects": _resolve_projects_tool,
    "propose_harness_edit": _propose_harness_edit,
    "adopt_harness_edit": _adopt_harness_edit,
    "rollback_harness": _rollback_harness,
}


async def dispatch_tool(name: str, arguments_json: str) -> str:
    handler = HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        args = {}
    try:
        result = await handler(args)
    except Exception as exc:  # noqa: BLE001 — return tool failures to the model
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, default=str)
