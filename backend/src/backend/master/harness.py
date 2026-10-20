"""Versioned harness components. Active rows are what the Master actually runs."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.core.db import db, row_to_dict, utcnow
from backend.master.system_prompt import GUARDRAILS, SYSTEM_PROMPT, TOOL_GUIDANCE

COMPONENT_NAMES = ("system_prompt", "guardrails", "tool_guidance", "memory")

SEED_CONTENT = {
    "system_prompt": SYSTEM_PROMPT.strip(),
    "guardrails": GUARDRAILS.strip(),
    "tool_guidance": TOOL_GUIDANCE.strip(),
    "memory": "No durable facts yet. Add only general research patterns, never a specific target's answer.",
}


def seed_harness(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) AS c FROM harness_components").fetchone()["c"]
    if existing:
        return
    now = utcnow()
    for name, content in SEED_CONTENT.items():
        conn.execute(
            """
            INSERT INTO harness_components (name, version, content, status, note, created_at)
            VALUES (?, 1, ?, 'active', 'seed', ?)
            """,
            (name, content, now),
        )


def active_components() -> dict[str, str]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT name, content, note FROM harness_components
            WHERE status = 'active'
            ORDER BY version DESC
            """
        ).fetchall()
    found: dict[str, str] = {}
    for row in rows:
        # If it's a default seed, use the latest upgraded SEED_CONTENT definition
        if row["note"] == "seed" and row["name"] in SEED_CONTENT:
            found.setdefault(row["name"], SEED_CONTENT[row["name"]])
        else:
            found.setdefault(row["name"], row["content"])
    for name, content in SEED_CONTENT.items():
        found.setdefault(name, content)
    return found


def list_components() -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM harness_components ORDER BY name, version DESC"
        ).fetchall()
    return [row_to_dict(r) for r in rows if row_to_dict(r)]


def propose_component(name: str, content: str, *, note: str = "") -> dict[str, Any]:
    if name not in COMPONENT_NAMES:
        raise ValueError(f"Unknown harness component {name}")
    text = (content or "").strip()
    if len(text) < 20:
        raise ValueError("Harness edit is too short to adopt later.")
    now = utcnow()
    with db() as conn:
        current = conn.execute(
            """
            SELECT id, version FROM harness_components
            WHERE name = ? AND status = 'active'
            ORDER BY version DESC LIMIT 1
            """,
            (name,),
        ).fetchone()
        version = int(current["version"]) + 1 if current else 1
        parent_id = current["id"] if current else None
        cur = conn.execute(
            """
            INSERT INTO harness_components
                (name, version, content, status, parent_id, note, created_at)
            VALUES (?, ?, ?, 'candidate', ?, ?, ?)
            """,
            (name, version, text, parent_id, note[:500], now),
        )
        row = row_to_dict(
            conn.execute(
                "SELECT * FROM harness_components WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        )
    return row or {}


def adopt_component(component_id: int) -> dict[str, Any]:
    now = utcnow()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM harness_components WHERE id = ?", (component_id,)
        ).fetchone()
        if not row:
            raise ValueError("Harness component not found")
        if row["status"] == "active":
            return row_to_dict(row) or {}
        conn.execute(
            """
            UPDATE harness_components
            SET status = 'retired'
            WHERE name = ? AND status = 'active'
            """,
            (row["name"],),
        )
        conn.execute(
            "UPDATE harness_components SET status = 'active', note = ? WHERE id = ?",
            (f"adopted {now}", component_id),
        )
        updated = row_to_dict(
            conn.execute(
                "SELECT * FROM harness_components WHERE id = ?", (component_id,)
            ).fetchone()
        )
    return updated or {}


def rollback_component(name: str) -> dict[str, Any]:
    if name not in COMPONENT_NAMES:
        raise ValueError(f"Unknown harness component {name}")
    now = utcnow()
    with db() as conn:
        active = conn.execute(
            """
            SELECT * FROM harness_components
            WHERE name = ? AND status = 'active'
            ORDER BY version DESC LIMIT 1
            """,
            (name,),
        ).fetchone()
        previous = conn.execute(
            """
            SELECT * FROM harness_components
            WHERE name = ? AND status = 'retired'
            ORDER BY version DESC LIMIT 1
            """,
            (name,),
        ).fetchone()
        if not active or not previous:
            raise ValueError(f"No previous {name} version to restore")
        conn.execute(
            "UPDATE harness_components SET status = 'retired', note = ? WHERE id = ?",
            (f"rolled back {now}", active["id"]),
        )
        conn.execute(
            "UPDATE harness_components SET status = 'active' WHERE id = ?",
            (previous["id"],),
        )
        restored = row_to_dict(
            conn.execute(
                "SELECT * FROM harness_components WHERE id = ?", (previous["id"],)
            ).fetchone()
        )
    return restored or {}
