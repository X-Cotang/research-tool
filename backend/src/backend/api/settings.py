from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core import config
from backend.domain.ai_settings import load_ai_settings, save_ai_settings
from backend.domain.github_client import GitHubError, github_get
from backend.domain.github_settings import get_github_token, load_github_settings, save_github_settings
from backend.domain.prompt_suggest import test_ai_connection
from backend.domain.research import ResearchError, save_research_settings, saved_research_command, saved_research_preset
from backend.domain.sast_scan import load_sast_settings, save_sast_settings

router = APIRouter()


class SettingsRequest(BaseModel):
    research_command: str = Field(min_length=1, max_length=32000)
    research_preset: str | None = Field(default=None, max_length=64)


class AiSettingsRequest(BaseModel):
    ai_base_url: str | None = Field(default=None, max_length=500)
    ai_api_key: str | None = Field(default=None, max_length=500)
    ai_model: str | None = Field(default=None, max_length=200)
    typesafe_api_key: str | None = Field(default=None, max_length=500)
    text_model_api_key: str | None = Field(default=None, max_length=500)
    text_model_base_url: str | None = Field(default=None, max_length=500)
    text_model_id: str | None = Field(default=None, max_length=200)


class SastSettingsRequest(BaseModel):
    sast_enabled: bool | None = None
    sast_tool: str | None = Field(default=None, max_length=32)
    sast_timeout: int | None = Field(default=None, ge=30, le=900)


class GithubSettingsRequest(BaseModel):
    github_token: str | None = Field(default=None, max_length=500)
    clear_github_token: bool | None = None


@router.get("/settings")
def read_settings() -> dict:
    command = saved_research_command()
    preset = saved_research_preset()
    presets = config.list_presets()
    preset_default = config.default_research_command(
        preset if preset != "custom" else config.DEFAULT_PRESET_ID
    )
    return {
        "research_command": command,
        "research_preset": preset,
        "default_research_command": preset_default,
        "presets": presets,
        "is_custom": preset == "custom" or command.strip() != preset_default.strip(),
    }


@router.put("/settings")
def update_settings(body: SettingsRequest) -> dict:
    try:
        save_research_settings(body.research_command, body.research_preset)
    except ResearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return read_settings()


@router.get("/settings/ai")
def read_ai_settings() -> dict:
    return load_ai_settings()


@router.put("/settings/ai")
def update_ai_settings(body: AiSettingsRequest) -> dict:
    return save_ai_settings(body.model_dump(exclude_unset=True))


@router.post("/settings/ai/test")
async def test_ai_settings() -> dict:
    try:
        return await test_ai_connection()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/settings/sast")
def read_sast_settings_route() -> dict:
    return load_sast_settings()


@router.put("/settings/sast")
def update_sast_settings_route(body: SastSettingsRequest) -> dict:
    try:
        return save_sast_settings(body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/settings/github")
def read_github_settings_route() -> dict:
    return load_github_settings()


@router.put("/settings/github")
def update_github_settings_route(body: GithubSettingsRequest) -> dict:
    return save_github_settings(body.model_dump(exclude_unset=True))


@router.post("/settings/github/test")
async def test_github_settings_route() -> dict:
    if not get_github_token():
        raise HTTPException(
            status_code=400,
            detail="No GitHub token configured. Paste a PAT under Settings and save.",
        )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await github_get(client, "/rate_limit")
            payload = response.json()
    except GitHubError as exc:
        raise HTTPException(status_code=exc.status_code or 400, detail=str(exc)) from exc
    core = (payload.get("resources") or {}).get("core") or {}
    search = (payload.get("resources") or {}).get("search") or {}
    return {
        "ok": True,
        "authenticated": True,
        "core_remaining": core.get("remaining"),
        "core_limit": core.get("limit"),
        "search_remaining": search.get("remaining"),
        "search_limit": search.get("limit"),
        "message": (
            f"Authenticated. Core API {core.get('remaining')}/{core.get('limit')} remaining; "
            f"search {search.get('remaining')}/{search.get('limit')} remaining."
        ),
    }
