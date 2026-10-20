from __future__ import annotations

from fastapi import APIRouter

from backend.core import config
from backend.domain.github_settings import load_github_settings
from backend.domain.research import saved_research_command, saved_research_preset
from backend.domain.sast_scan import load_sast_settings

router = APIRouter()


@router.get("/status")
def status() -> dict:
    github = load_github_settings()
    return {
        "github_token": bool(github.get("has_github_token")),
        "github_token_source": github.get("github_token_source"),
        "research_dir": str(config.RESEARCH_DIR),
        "command_code_model": config.COMMAND_CODE_MODEL,
        "db_path": str(config.DB_PATH),
        "research_command": saved_research_command(),
        "research_preset": saved_research_preset(),
        "research_presets": config.list_presets(),
        "default_research_command": config.default_research_command(saved_research_preset()),
        "sast": load_sast_settings(),
    }
