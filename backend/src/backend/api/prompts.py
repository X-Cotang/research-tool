from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.db import db, row_to_dict, utcnow

router = APIRouter()


class PromptCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    language: str | None = Field(default=None, max_length=80)
    vuln_class: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=4000)
    content: str = Field(min_length=1, max_length=64000)


class PromptUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=80)
    vuln_class: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    content: str | None = Field(default=None, max_length=64000)


@router.get("/prompts")
def list_prompts(q: str | None = None) -> dict:
    with db() as conn:
        if q:
            like = f"%{q.strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM prompts
                WHERE slug LIKE ? OR name LIKE ? OR description LIKE ? OR vuln_class LIKE ?
                ORDER BY name
                """,
                (like, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM prompts ORDER BY name").fetchall()
    return {"prompts": [row_to_dict(r) for r in rows if row_to_dict(r)]}


@router.post("/prompts")
def create_prompt(body: PromptCreate) -> dict:
    now = utcnow()
    with db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO prompts (slug, name, language, vuln_class, description, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    body.slug,
                    body.name,
                    body.language,
                    body.vuln_class,
                    body.description,
                    body.content,
                    now,
                    now,
                ),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        prompt = row_to_dict(
            conn.execute("SELECT * FROM prompts WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return {"prompt": prompt}


@router.get("/prompts/{prompt_id}")
def get_prompt(prompt_id: int) -> dict:
    with db() as conn:
        prompt = row_to_dict(
            conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"prompt": prompt}


@router.put("/prompts/{prompt_id}")
def update_prompt(prompt_id: int, body: PromptUpdate) -> dict:
    with db() as conn:
        existing = row_to_dict(
            conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Prompt not found")
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            return {"prompt": existing}
        fields["updated_at"] = utcnow()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE prompts SET {assignments} WHERE id = ?",
            list(fields.values()) + [prompt_id],
        )
        prompt = row_to_dict(
            conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        )
    return {"prompt": prompt}


@router.delete("/prompts/{prompt_id}")
def delete_prompt(prompt_id: int) -> dict:
    with db() as conn:
        if not conn.execute("SELECT id FROM prompts WHERE id = ?", (prompt_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Prompt not found")
        conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    return {"ok": True}
