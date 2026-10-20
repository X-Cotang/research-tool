from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.db import db, row_to_dict, utcnow

router = APIRouter()


class SkillCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    language: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=4000)
    content: str = Field(min_length=1, max_length=64000)


class SkillUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=4000)
    content: str | None = Field(default=None, max_length=64000)


@router.get("/skills")
def list_skills(q: str | None = None) -> dict:
    with db() as conn:
        if q:
            like = f"%{q.strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM skills
                WHERE slug LIKE ? OR name LIKE ? OR description LIKE ?
                ORDER BY name
                """,
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
    return {"skills": [row_to_dict(r) for r in rows if row_to_dict(r)]}


@router.post("/skills")
def create_skill(body: SkillCreate) -> dict:
    now = utcnow()
    with db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO skills (slug, name, language, description, content, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'user', ?, ?)
                """,
                (body.slug, body.name, body.language, body.description, body.content, now, now),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        skill = row_to_dict(
            conn.execute("SELECT * FROM skills WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    return {"skill": skill}


@router.get("/skills/{skill_id}")
def get_skill(skill_id: int) -> dict:
    with db() as conn:
        skill = row_to_dict(conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone())
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"skill": skill}


@router.put("/skills/{skill_id}")
def update_skill(skill_id: int, body: SkillUpdate) -> dict:
    with db() as conn:
        existing = row_to_dict(
            conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Skill not found")
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            return {"skill": existing}
        fields["updated_at"] = utcnow()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(
            f"UPDATE skills SET {assignments} WHERE id = ?",
            list(fields.values()) + [skill_id],
        )
        skill = row_to_dict(
            conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        )
    return {"skill": skill}


@router.delete("/skills/{skill_id}")
def delete_skill(skill_id: int) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Skill not found")
        if row["source"] == "builtin":
            raise HTTPException(status_code=400, detail="Cannot delete builtin skills")
        conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
    return {"ok": True}
