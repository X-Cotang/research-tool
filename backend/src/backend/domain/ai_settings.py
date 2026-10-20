from __future__ import annotations

import os
from typing import Any

from backend.core.db import get_setting, set_setting

AI_KEYS = (
    "ai_base_url",
    "ai_api_key",
    "ai_model",
    "typesafe_api_key",
    "text_model_api_key",
    "text_model_base_url",
    "text_model_id",
)

SECRET_KEYS = frozenset({"ai_api_key", "typesafe_api_key", "text_model_api_key"})

ENV_BOOTSTRAP = {
    "ai_base_url": ("AI_BASE_URL", "OPENAI_BASE_URL"),
    "ai_api_key": ("AI_API_KEY", "OPENAI_API_KEY"),
    "ai_model": ("AI_MODEL", "OPENAI_MODEL"),
    "typesafe_api_key": ("TYPESAFE_API_KEY",),
    "text_model_api_key": ("TEXT_MODEL_API_KEY",),
    "text_model_base_url": ("TEXT_MODEL_BASE_URL",),
    "text_model_id": ("TEXT_MODEL_ID",),
}


def _env_default(key: str) -> str:
    for env_name in ENV_BOOTSTRAP.get(key, ()):
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def _mask(secret: str) -> str:
    text = (secret or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "••••" + text[-2:]
    return text[:3] + "••••" + text[-4:]


def get_ai_setting(key: str) -> str:
    saved = get_setting(key, "").strip()
    if saved:
        return saved
    return _env_default(key)


def load_ai_settings(*, reveal_secrets: bool = False) -> dict[str, Any]:
    raw = {key: get_ai_setting(key) for key in AI_KEYS}
    public: dict[str, Any] = {
        "ai_base_url": raw["ai_base_url"],
        "ai_model": raw["ai_model"],
        "text_model_base_url": raw["text_model_base_url"],
        "text_model_id": raw["text_model_id"],
        "has_ai_api_key": bool(raw["ai_api_key"]),
        "has_typesafe_api_key": bool(raw["typesafe_api_key"]),
        "has_text_model_api_key": bool(raw["text_model_api_key"]),
        "ai_api_key_preview": _mask(raw["ai_api_key"]),
        "typesafe_api_key_preview": _mask(raw["typesafe_api_key"]),
        "text_model_api_key_preview": _mask(raw["text_model_api_key"]),
    }
    if reveal_secrets:
        public.update({key: raw[key] for key in SECRET_KEYS})
    return public


def save_ai_settings(payload: dict[str, Any]) -> dict[str, Any]:
    for key in AI_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if key in SECRET_KEYS and not text:
            # Empty secret field means keep the existing value.
            continue
        set_setting(key, text)
    return load_ai_settings()


def require_prompt_settings() -> dict[str, str]:
    base_url = get_ai_setting("ai_base_url").rstrip("/")
    api_key = get_ai_setting("ai_api_key")
    model = get_ai_setting("ai_model")
    missing = []
    if not base_url:
        missing.append("Base URL")
    if not api_key:
        missing.append("API key")
    if not model:
        missing.append("Model")
    if missing:
        raise ValueError(
            "Prompt suggestion is not configured. Set "
            + ", ".join(missing)
            + " under Settings."
        )
    return {"base_url": base_url, "api_key": api_key, "model": model}


def require_report_settings() -> dict[str, str]:
    typesafe = get_ai_setting("typesafe_api_key")
    text_key = get_ai_setting("text_model_api_key")
    missing = []
    if not typesafe:
        missing.append("TYPESAFE_API_KEY")
    if not text_key:
        missing.append("TEXT_MODEL_API_KEY")
    if missing:
        raise ValueError(
            "Report automation is not configured. Set "
            + ", ".join(missing)
            + " under Settings."
        )
    return {
        "typesafe_api_key": typesafe,
        "text_model_api_key": text_key,
        "text_model_base_url": get_ai_setting("text_model_base_url"),
        "text_model_id": get_ai_setting("text_model_id"),
    }
