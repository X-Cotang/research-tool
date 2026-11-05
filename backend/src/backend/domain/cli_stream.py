"""Turn a CLI's machine-readable events into short progress lines.

command-code `--output-format json` writes one JSON object per line:
an `event` frame while it works, then a final `result` frame that carries
the session id. The process still exits. A later turn uses `--resume`.

qoder `--output-format stream-json` writes the same kind of line stream:
`system` / `assistant` / `user` frames while it works, then a `result`
frame whose `result` text is the answer and whose `session_id` reopens
with `--resume`.
"""

from __future__ import annotations

import json
from typing import Any


def _preview_result(value: Any, limit: int = 180) -> str:
    if isinstance(value, list):
        bits: list[str] = []
        for item in value:
            if isinstance(item, dict) and item.get("text"):
                bits.append(str(item["text"]))
            elif isinstance(item, str):
                bits.append(item)
        if bits:
            return _short("\n".join(bits), limit)
    if isinstance(value, dict) and value.get("text"):
        return _short(value.get("text"), limit)
    return _short(value, limit)


def _short(value: Any, limit: int = 140) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except TypeError:
            value = str(value)
    text = " ".join(value.split())
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _session_id(payload: dict[str, Any]) -> str | None:
    session_id = payload.get("sessionId") or payload.get("session_id")
    data = payload.get("data")
    if not session_id and isinstance(data, dict):
        session_id = data.get("sessionId") or data.get("session_id")
    return str(session_id) if session_id else None


def _content_blocks(payload: dict[str, Any]) -> list[Any]:
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            return content
        if isinstance(content, str) and content.strip():
            return [{"type": "text", "text": content}]
    content = payload.get("content")
    if isinstance(content, list):
        return content
    if isinstance(content, str) and content.strip():
        return [{"type": "text", "text": content}]
    return []


def _interpret_stream_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Qoder/Claude-style stream-json frames. None means try the other parser."""
    kind = str(payload.get("type") or "")
    session_id = _session_id(payload)
    if kind == "system":
        subtype = str(payload.get("subtype") or "")
        if subtype == "init":
            text = "[cli] started"
            if session_id:
                text += f" · session {session_id}"
            return {
                "kind": "line",
                "text": text,
                "session_id": session_id,
                "activity": "started",
                "final_text": None,
            }
        return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
    if kind == "assistant":
        texts: list[str] = []
        tools: list[tuple[str, str]] = []
        for block in _content_blocks(payload):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type == "text" and block.get("text"):
                texts.append(str(block["text"]))
            elif block_type == "tool_use":
                name = str(block.get("name") or "tool")
                tools.append((name, _short(block.get("input") or "")))
        lines: list[str] = []
        for name, detail in tools:
            line = f"[cli] tool {name}"
            if detail:
                line += f" · {detail}"
            lines.append(line)
        if texts:
            preview = _short("\n".join(texts), 400)
            if preview:
                lines.append(f"[cli] {preview}")
        if not lines:
            return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
        activity = f"tool {tools[-1][0]}" if tools else "writing"
        return {
            "kind": "line",
            "text": "\n".join(lines),
            "session_id": session_id,
            "activity": activity,
            "final_text": None,
        }
    if kind == "user":
        previews: list[str] = []
        for block in _content_blocks(payload):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                preview = _preview_result(block.get("content") or "")
                if preview:
                    previews.append(preview)
        if not previews and payload.get("tool_use_result"):
            preview = _preview_result(payload.get("tool_use_result"))
            if preview:
                previews.append(preview)
        if not previews:
            return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
        return {
            "kind": "line",
            "text": f"[cli] tool result · {previews[0]}",
            "session_id": session_id,
            "activity": "tool result",
            "final_text": None,
        }
    if kind == "stream_event":
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
        delta_type = str(delta.get("type") or "")
        if delta_type == "text_delta":
            return {
                "kind": "delta",
                "text": str(delta.get("text") or ""),
                "session_id": session_id,
                "activity": "writing",
                "final_text": None,
            }
        if delta_type == "thinking_delta":
            return {
                "kind": "skip",
                "text": "",
                "session_id": session_id,
                "activity": "thinking",
                "final_text": None,
            }
        block = event.get("content_block") if isinstance(event.get("content_block"), dict) else {}
        if event.get("type") == "content_block_start" and block.get("type") == "tool_use":
            name = str(block.get("name") or "tool")
            return {
                "kind": "line",
                "text": f"[cli] tool {name}",
                "session_id": session_id,
                "activity": f"tool {name}",
                "final_text": None,
            }
        return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
    return None


def interpret_cli_line(line: str) -> dict[str, Any]:
    """Return a display decision for one stdout line.

    Keys: kind (line, delta, skip), text, session_id, activity, final_text.
    """
    raw = (line or "").strip()
    if not raw.startswith("{"):
        return {"kind": "line", "text": raw, "session_id": None, "activity": None, "final_text": None}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"kind": "line", "text": raw[:500], "session_id": None, "activity": None, "final_text": None}
    if not isinstance(payload, dict):
        return {"kind": "skip", "text": "", "session_id": None, "activity": None, "final_text": None}

    if payload.get("type") == "result":
        session_id = _session_id(payload)
        subtype = payload.get("subtype") or "done"
        final_text = payload.get("finalText") or payload.get("final_text") or payload.get("result") or ""
        if not isinstance(final_text, str):
            final_text = ""
        if not final_text and isinstance(payload.get("errors"), list):
            final_text = "\n".join(str(item) for item in payload["errors"] if item)
        activity = f"finished ({subtype})"
        label = f"[cli] {activity}"
        if session_id:
            label += f" · session {session_id}"
        error = payload.get("error")
        if not error and isinstance(payload.get("errors"), list) and payload["errors"]:
            error = "; ".join(str(item) for item in payload["errors"] if item)
        if error:
            label += f" · {_short(error, 240)}"
        return {
            "kind": "line",
            "text": label,
            "session_id": session_id,
            "activity": activity,
            "final_text": final_text,
        }

    streamed = _interpret_stream_message(payload)
    if streamed is not None:
        return streamed

    event = payload.get("event") if payload.get("type") == "event" else payload
    if not isinstance(event, dict):
        return {"kind": "skip", "text": "", "session_id": None, "activity": None, "final_text": None}

    kind = str(event.get("type") or "")
    session_id = event.get("sessionId") or event.get("session_id")
    session_id = str(session_id) if session_id else None

    if kind == "text_delta":
        return {
            "kind": "delta",
            "text": str(event.get("delta") or ""),
            "session_id": session_id,
            "activity": "writing",
            "final_text": None,
        }
    if kind in {"thinking_delta", "thinking_start"}:
        return {
            "kind": "skip",
            "text": "",
            "session_id": session_id,
            "activity": "thinking",
            "final_text": None,
        }
    if kind == "run_start":
        activity = "started"
        text = "[cli] started"
        if session_id:
            text += f" · session {session_id}"
        return {"kind": "line", "text": text, "session_id": session_id, "activity": activity, "final_text": None}
    if kind == "tool_queued":
        name = str(event.get("toolName") or event.get("name") or "tool")
        activity = f"tool {name}"
        detail = _short(event.get("input") or event.get("description") or "")
        text = f"[cli] {activity}"
        if detail:
            text += f" · {detail}"
        return {"kind": "line", "text": text, "session_id": session_id, "activity": activity, "final_text": None}
    if kind in {"tool_running", "tool_update"}:
        name = str(event.get("toolName") or event.get("description") or "tool")
        activity = f"running {name}"
        return {
            "kind": "line",
            "text": f"[cli] {activity}",
            "session_id": session_id,
            "activity": activity,
            "final_text": None,
        }
    if kind in {"tool_completed", "tool_result"}:
        name = str(event.get("toolName") or "tool")
        activity = f"finished {name}"
        preview = _preview_result(event.get("result") or event.get("output") or "")
        text = f"[cli] {activity}"
        if preview:
            text += f" · {preview}"
        return {
            "kind": "line",
            "text": text,
            "session_id": session_id,
            "activity": activity,
            "final_text": None,
        }
    if kind == "run_end":
        result = event.get("result") if isinstance(event.get("result"), dict) else {}
        final_text = result.get("finalText") or result.get("text") or ""
        nested = result.get("sessionId") or result.get("session_id") or session_id
        nested = str(nested) if nested else None
        return {
            "kind": "line",
            "text": "[cli] run finished",
            "session_id": nested,
            "activity": "run finished",
            "final_text": final_text if isinstance(final_text, str) else "",
        }
    if kind in {"turn_start", "message_start"}:
        return {
            "kind": "line",
            "text": "[cli] model turn",
            "session_id": session_id,
            "activity": "model turn",
            "final_text": None,
        }
    if kind in {"turn_end", "message_end", "model_request_end", "model_request_start"}:
        return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
    return {"kind": "skip", "text": "", "session_id": session_id, "activity": None, "final_text": None}
