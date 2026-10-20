from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.domain.library import list_library

router = APIRouter()


@router.get("/library")
def library(view: str = "all") -> dict:
    normalized = (view or "all").strip().lower()
    if normalized not in {"all", "active", "history"}:
        raise HTTPException(status_code=400, detail="view must be all, active, or history")
    return list_library(view=normalized)
