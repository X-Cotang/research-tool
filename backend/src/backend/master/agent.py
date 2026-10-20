from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from backend.domain.ai_settings import get_ai_setting
from backend.master.experience import render_lessons
from backend.master.harness import active_components
from backend.master.memory import build_working_memory, render_working_memory
from backend.master.tools import TOOL_DEFINITIONS, dispatch_tool

MAX_TOOL_ROUNDS = 8


def _ai_config() -> dict[str, str]:
    base_url = get_ai_setting("ai_base_url").rstrip("/")
    api_key = get_ai_setting("ai_api_key")
    model = get_ai_setting("ai_model")
    if not base_url or not api_key or not model:
        raise ValueError(
            "AI settings incomplete. Configure base URL, API key, and model under Settings."
        )
    return {"base_url": base_url, "api_key": api_key, "model": model}


async def run_agent_stream(
    messages: list[dict[str, Any]],
    *,
    conversation_id: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """OpenAI-compatible tool-calling loop; yields SSE-style event dicts."""
    cfg = _ai_config()
    url = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    system = assemble_system(conversation_id)
    convo = [{"role": "system", "content": system}, *messages]

    async with httpx.AsyncClient(timeout=120.0) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            body: dict[str, Any] = {
                "model": cfg["model"],
                "messages": convo,
                "tools": TOOL_DEFINITIONS,
                "stream": True,
            }
            assistant_text = ""
            tool_calls: dict[int, dict[str, Any]] = {}

            try:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        text = await response.aread()
                        yield {"type": "error", "message": text.decode()[:800]}
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        thinking = (
                            delta.get("reasoning_content")
                            or delta.get("reasoning")
                            or delta.get("thinking")
                        )
                        if thinking:
                            yield {"type": "thinking", "content": thinking}
                        if delta.get("content"):
                            piece = delta["content"]
                            assistant_text += piece
                            yield {"type": "token", "content": piece}
                        for tc in delta.get("tool_calls") or []:
                            idx = int(tc.get("index") or 0)
                            entry = tool_calls.setdefault(
                                idx,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                entry["name"] = fn["name"]
                            if fn.get("arguments"):
                                entry["arguments"] += fn["arguments"]
            except httpx.HTTPError as exc:
                yield {"type": "error", "message": str(exc)}
                return

            if not tool_calls:
                yield {"type": "done", "content": assistant_text}
                return

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": [
                    {
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for i, tc in sorted(tool_calls.items())
                ],
            }
            convo.append(assistant_msg)

            for i, tc in sorted(tool_calls.items()):
                name = tc["name"]
                args = tc.get("arguments") or "{}"
                if conversation_id is not None and name in {"queue_research_batch", "queue_research"}:
                    try:
                        parsed_args = json.loads(args or "{}")
                        if not parsed_args.get("conversation_id"):
                            parsed_args["conversation_id"] = conversation_id
                            args = json.dumps(parsed_args)
                    except json.JSONDecodeError:
                        pass
                yield {"type": "tool_call", "name": name, "arguments": args}
                result = await dispatch_tool(name, args)
                yield {"type": "tool_result", "name": name, "result": result}
                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"] or f"call_{i}",
                        "content": result,
                    }
                )

        yield {"type": "error", "message": "Max tool rounds exceeded"}
        yield {"type": "done", "content": ""}


def assemble_system(conversation_id: int | None = None) -> str:
    parts = active_components()
    snapshot = build_working_memory()
    languages = list(snapshot.get("languages") or [])
    blocks = [
        parts.get("system_prompt", ""),
        "# Guardrails\n" + parts.get("guardrails", ""),
        "# Tool guidance\n" + parts.get("tool_guidance", ""),
        "# Durable memory\n" + parts.get("memory", ""),
        render_working_memory(snapshot),
        render_lessons(languages),
    ]
    if conversation_id is not None:
        blocks.append(
            f"Current conversation_id={conversation_id}. "
            "Pass it to queue_research and queue_research_batch."
        )
    return "\n\n".join(block.strip() for block in blocks if block and block.strip())
