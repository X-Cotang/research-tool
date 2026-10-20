"""Wake the Master when a linked research job settles."""

from __future__ import annotations

import asyncio

from backend.core.db import db, utcnow
from backend.master.agent import run_agent_stream
from backend.master.experience import reflect_on_job

_inflight: set[int] = set()


def schedule_wake(
    conversation_id: int,
    observation: str,
    *,
    job_id: int | None = None,
    run_id: int | None = None,
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(
        resume_master(
            conversation_id,
            observation,
            job_id=job_id,
            run_id=run_id,
        )
    )


async def resume_master(
    conversation_id: int,
    observation: str,
    *,
    job_id: int | None = None,
    run_id: int | None = None,
) -> None:
    if conversation_id in _inflight:
        return
    _inflight.add(conversation_id)
    try:
        now = utcnow()
        with db() as conn:
            exists = conn.execute(
                "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if not exists:
                return
            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, type, content, created_at)
                VALUES (?, 'user', 'observation', ?, ?)
                """,
                (conversation_id, observation.strip(), now),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        if job_id:
            await reflect_on_job(job_id, run_id=run_id)
        try:
            with db() as conn:
                history = conn.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC LIMIT 24
                    """,
                    (conversation_id,),
                ).fetchall()
            prior = [
                {
                    "role": "user" if row["role"] == "user" else "assistant",
                    "content": row["content"],
                }
                for row in reversed(history)
                if row["role"] in {"user", "assistant"}
            ]
            parts: list[str] = []
            async for event in run_agent_stream(prior, conversation_id=conversation_id):
                if event.get("type") == "token":
                    parts.append(event.get("content") or "")
                if event.get("type") in {"done", "error"}:
                    if event.get("type") == "error" and not parts:
                        parts.append(event.get("message") or "Master wake failed.")
                    break
            text = "".join(parts).strip()
        except ValueError as exc:
            text = f"Job update recorded. AI Master is not configured ({exc})."
        if text:
            finished = utcnow()
            with db() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (conversation_id, role, type, content, created_at)
                    VALUES (?, 'assistant', 'text', ?, ?)
                    """,
                    (conversation_id, text, finished),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (finished, conversation_id),
                )
    finally:
        _inflight.discard(conversation_id)
