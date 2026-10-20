from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.domain.findings import get_finding, list_findings, parse_project_findings, patch_finding

router = APIRouter()


class FindingPatch(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    severity: str | None = Field(default=None, max_length=32)
    cwe: str | None = Field(default=None, max_length=32)
    file_path: str | None = Field(default=None, max_length=500)
    line_start: int | None = None
    description: str | None = Field(default=None, max_length=8000)
    status: str | None = Field(default=None, max_length=32)
    evidence: str | None = Field(default=None, max_length=12000)


@router.get("/findings")
def findings_list(project_id: int | None = None, limit: int = 200) -> dict:
    return {"findings": list_findings(project_id=project_id, limit=limit)}


@router.get("/findings/{finding_id}")
def findings_show(finding_id: int) -> dict:
    finding = get_finding(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"finding": finding}


@router.patch("/findings/{finding_id}")
def findings_patch(finding_id: int, body: FindingPatch) -> dict:
    finding = patch_finding(finding_id, **body.model_dump(exclude_unset=True))
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"finding": finding}


@router.post("/projects/{project_id}/findings/parse")
def findings_parse(project_id: int) -> dict:
    try:
        return parse_project_findings(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
