from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.db import db, row_to_dict, utcnow
from backend.domain.supervisor import schedule_job
from backend.master.agent import run_agent_stream

router = APIRouter(prefix="/chat")


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=32000)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _insert_message(
    conversation_id: int,
    *,
    role: str,
    type_: str,
    content: str,
    created_at: str | None = None,
) -> None:
    stamp = created_at or utcnow()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, type, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (conversation_id, role, type_, content, stamp),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (stamp, conversation_id),
        )


def _history_for_model(conversation_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT role, type, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
    prior: list[dict] = []
    for row in rows:
        role = row["role"]
        type_ = row["type"] or "text"
        if type_ in {"text", "observation"} and role in {"user", "assistant"}:
            prior.append({"role": "user" if role == "user" else "assistant", "content": row["content"]})
    return prior


@router.get("/conversations")
def list_conversations() -> dict:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    return {"conversations": [row_to_dict(r) for r in rows if row_to_dict(r)]}


@router.post("/conversations")
def create_conversation(body: ConversationCreate | None = None) -> dict:
    now = utcnow()
    title = (body.title if body and body.title else None) or "New chat"
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO conversations (title, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (title, now, now),
        )
        conv = row_to_dict(
            conn.execute("SELECT * FROM conversations WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return {"conversation": conv}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int) -> dict:
    with db() as conn:
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.execute(
            "UPDATE runs SET conversation_id = NULL WHERE conversation_id = ?",
            (conversation_id,),
        )
        conn.execute(
            "UPDATE jobs SET conversation_id = NULL WHERE conversation_id = ?",
            (conversation_id,),
        )
    return {"ok": True, "id": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: int) -> dict:
    with db() as conn:
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        rows = conn.execute(
            """
            SELECT * FROM messages WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()
    return {"messages": [row_to_dict(r) for r in rows if row_to_dict(r)]}


@router.post("/conversations/{conversation_id}/messages")
async def post_message(
    conversation_id: int,
    body: MessageCreate,
) -> StreamingResponse:
    now = utcnow()
    with db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, type, content, created_at)
            VALUES (?, 'user', 'text', ?, ?)
            """,
            (conversation_id, body.content, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
    prior = _history_for_model(conversation_id)

    async def events():
        assistant_parts: list[str] = []
        thinking_parts: list[str] = []
        try:
            async for event in run_agent_stream(prior, conversation_id=conversation_id):
                etype = event.get("type")
                if etype == "token":
                    assistant_parts.append(event.get("content") or "")
                elif etype == "thinking":
                    thinking_parts.append(event.get("content") or "")
                elif etype == "tool_call":
                    if thinking_parts:
                        _insert_message(
                            conversation_id,
                            role="assistant",
                            type_="thinking",
                            content="".join(thinking_parts).strip(),
                        )
                        thinking_parts.clear()
                    if assistant_parts:
                        text = "".join(assistant_parts).strip()
                        if text:
                            _insert_message(
                                conversation_id,
                                role="assistant",
                                type_="text",
                                content=text,
                            )
                        assistant_parts.clear()
                    payload = {
                        "name": event.get("name") or "tool",
                        "arguments": event.get("arguments") or "",
                    }
                    _insert_message(
                        conversation_id,
                        role="assistant",
                        type_="tool_call",
                        content=json.dumps(payload, ensure_ascii=False),
                    )
                elif etype == "tool_result":
                    payload = {
                        "name": event.get("name") or "tool",
                        "result": event.get("result") or "",
                    }
                    _insert_message(
                        conversation_id,
                        role="tool",
                        type_="tool_result",
                        content=json.dumps(payload, ensure_ascii=False),
                    )
                    if event.get("name") in {"queue_research_batch", "queue_research"}:
                        try:
                            result = json.loads(event.get("result") or "{}")
                            if event.get("name") == "queue_research":
                                if (
                                    result.get("start")
                                    and result.get("job_id")
                                    and result.get("project_id")
                                ):
                                    schedule_job(
                                        int(result["job_id"]),
                                        int(result["project_id"]),
                                    )
                            else:
                                entries = result.get("jobs") or result.get("queued") or []
                                if not entries:
                                    entries = [
                                        item
                                        for item in (result.get("tasks") or [])
                                        if item.get("created")
                                    ]
                                for entry in entries:
                                    if entry.get("created") is False:
                                        continue
                                    job = entry.get("job") or entry
                                    jid = job.get("id") or job.get("job_id") or entry.get("job_id")
                                    pid = job.get("project_id") or entry.get("project_id")
                                    if jid and pid and entry.get("created", True):
                                        schedule_job(int(jid), int(pid))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                yield _sse(event)
                if etype in {"done", "error"}:
                    break
        except ValueError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            yield _sse({"type": "done", "content": ""})
            return

        if thinking_parts:
            think = "".join(thinking_parts).strip()
            if think:
                _insert_message(
                    conversation_id,
                    role="assistant",
                    type_="thinking",
                    content=think,
                )
        assistant = "".join(assistant_parts).strip()
        if assistant:
            _insert_message(
                conversation_id,
                role="assistant",
                type_="text",
                content=assistant,
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
