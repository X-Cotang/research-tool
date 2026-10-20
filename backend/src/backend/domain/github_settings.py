from __future__ import annotations

import os
from typing import Any

from backend.core.config import GITHUB_TOKEN as ENV_GITHUB_TOKEN
from backend.core.db import get_setting, set_setting

SETTING_KEY = "github_token"


def _mask(secret: str) -> str:
    text = (secret or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "••••" + text[-2:]
    return text[:4] + "••••" + text[-4:]


def get_github_token() -> str:
    """Prefer the token saved in Settings; fall back to GITHUB_TOKEN env."""
    saved = get_setting(SETTING_KEY, "").strip()
    if saved:
        return saved
    env = (ENV_GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")).strip()
    return env


def load_github_settings() -> dict[str, Any]:
    token = get_github_token()
    source = "none"
    if get_setting(SETTING_KEY, "").strip():
        source = "settings"
    elif (ENV_GITHUB_TOKEN or os.getenv("GITHUB_TOKEN", "")).strip():
        source = "env"
    return {
        "has_github_token": bool(token),
        "github_token_preview": _mask(token),
        "github_token_source": source,
    }


def save_github_settings(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("clear_github_token"):
        set_setting(SETTING_KEY, "")
        return load_github_settings()
    if "github_token" in payload:
        value = payload.get("github_token")
        if value is None:
            return load_github_settings()
        text = str(value).strip()
        if text:
            set_setting(SETTING_KEY, text)
    return load_github_settings()
