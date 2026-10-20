from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from backend.core.db import db, row_to_dict
from backend.domain.findings import list_findings, patch_finding
from backend.domain.jobs import get_job_snapshot, queue_research
from backend.domain.prompt_suggest import suggest_prompt
from backend.domain.research import saved_research_command
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
            "description": "List projects, optionally filtered by org login.",
            "parameters": {
                "type": "object",
                "properties": {"org": {"type": "string"}},
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
            "description": "Queue a single research job for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer"},
                    "command": {"type": "string"},
                    "conversation_id": {"type": "integer"},
                },
                "required": ["project_id"],
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
            "description": "Create a run and queue research jobs for multiple projects.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_ids": {"type": "array", "items": {"type": "integer"}},
                    "conversation_id": {"type": "integer"},
                    "skill_slug": {"type": "string"},
                    "prompt_slug": {"type": "string"},
                    "command": {"type": "string"},
                },
                "required": ["project_ids"],
            },
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


async def _list_projects(args: dict) -> Any:
    org = args.get("org")
    with db() as conn:
        if org:
            from backend.core.db import load_org_projects

            _, projects = load_org_projects(conn, org)
        else:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY research_score DESC LIMIT 50"
            ).fetchall()
            projects = [row_to_dict(r) for r in rows]
    return {"projects": projects}


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
    return {"project": project, "jobs": [row_to_dict(j) for j in jobs]}


async def _get_job_status(args: dict) -> Any:
    snap = get_job_snapshot(int(args["job_id"]))
    return snap or {"error": "not found"}


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


async def _queue_research_tool(args: dict) -> Any:
    pid = int(args["project_id"])
    cmd = (args.get("command") or saved_research_command()).strip()
    conversation_id = args.get("conversation_id")
    with db() as conn:
        job, created = queue_research(
            conn,
            pid,
            cmd,
            conversation_id=int(conversation_id) if conversation_id else None,
        )
    return {
        "job": job,
        "created": created,
        "project_id": pid,
        "job_id": job["id"] if job else None,
        "start": bool(created and job),
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
    plan = {
        "project_ids": args.get("project_ids") or [],
        "skill_slug": args.get("skill_slug"),
        "prompt_slug": args.get("prompt_slug"),
        "command": saved_research_command(),
    }
    with db() as conn:
        if plan["prompt_slug"]:
            row = conn.execute(
                "SELECT content FROM prompts WHERE slug = ?", (plan["prompt_slug"],)
            ).fetchone()
            if row:
                plan["command"] = row["content"]
        if plan["skill_slug"]:
            row = conn.execute(
                "SELECT content FROM skills WHERE slug = ?", (plan["skill_slug"],)
            ).fetchone()
            if row:
                plan["skill_hint"] = row["content"]
    return {"plan": plan}


async def _queue_research_batch_tool(args: dict) -> Any:
    ids = [int(x) for x in args.get("project_ids") or []]
    result = queue_research_batch(
        ids,
        conversation_id=args.get("conversation_id"),
        skill_slug=args.get("skill_slug"),
        prompt_slug=args.get("prompt_slug"),
        command=args.get("command"),
    )
    return {"run_id": result["run"]["id"], "run": result["run"], "tasks": result["tasks"]}


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


HANDLERS: dict[str, ToolHandler] = {
    "workspace_status": _workspace_status,
    "list_projects": _list_projects,
    "get_project": _get_project,
    "get_job_status": _get_job_status,
    "suggest_research_prompt": _suggest_research_prompt,
    "queue_research": _queue_research_tool,
    "scan_org": _scan_org,
    "search_skills": _search_skills,
    "get_skill": _get_skill,
    "search_prompts": _search_prompts,
    "compose_research_plan": _compose_research_plan,
    "queue_research_batch": _queue_research_batch_tool,
    "list_findings": _list_findings_tool,
    "update_finding_status": _update_finding_status,
    "list_experiences": _list_experiences_tool,
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
    result = await handler(args)
    return json.dumps(result, default=str)
