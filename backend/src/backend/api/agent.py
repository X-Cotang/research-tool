from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.master.experience import list_experiences
from backend.master.harness import (
    adopt_component,
    list_components,
    rollback_component,
)
from backend.master.memory import build_working_memory, render_working_memory

router = APIRouter(prefix="/agent")


@router.get("/memory")
def memory() -> dict:
    snapshot = build_working_memory()
    return {"snapshot": snapshot, "text": render_working_memory(snapshot)}


@router.get("/experiences")
def experiences(domain: str | None = None) -> dict:
    return {"experiences": list_experiences(domain=domain)}


@router.get("/harness")
def harness() -> dict:
    return {"components": list_components()}


@router.post("/harness/{component_id}/adopt")
def adopt(component_id: int) -> dict:
    try:
        component = adopt_component(component_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"component": component}


@router.post("/harness/{name}/rollback")
def rollback(name: str) -> dict:
    try:
        component = rollback_component(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"component": component}
