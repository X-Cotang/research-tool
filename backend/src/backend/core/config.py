from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

CORE_DIR = Path(__file__).resolve().parent
# Monorepo app root: research-tool/ (parent of the backend/ project folder)
ROOT_DIR = Path(os.getenv("ROOT_DIR", str(CORE_DIR.parents[3]))).resolve()

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data")).resolve()
RESEARCH_DIR = Path(os.getenv("RESEARCH_DIR", ROOT_DIR / "research")).resolve()
SKILLS_DIR = Path(os.getenv("SKILLS_DIR", ROOT_DIR / "skills")).resolve()
DB_PATH = DATA_DIR / "research.db"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_API = "https://api.github.com"

COMMAND_CODE_BIN = os.getenv("COMMAND_CODE_BIN", "command-code").strip() or "command-code"
COMMAND_CODE_MODEL = os.getenv("COMMAND_CODE_MODEL", "z-ai/glm-5.3-flash").strip()
OPENCODE_BIN = os.getenv("OPENCODE_BIN", "opencode").strip() or "opencode"
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "").strip()
FREEBUFF_BIN = os.getenv("FREEBUFF_BIN", "freebuff").strip() or "freebuff"
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude").strip() or "claude"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "").strip()
CODEX_BIN = os.getenv("CODEX_BIN", "codex").strip() or "codex"
RESEARCH_TIMEOUT = int(
    os.getenv("RESEARCH_TIMEOUT", os.getenv("COMMAND_CODE_TIMEOUT", str(45 * 60)))
)
COMMAND_CODE_TIMEOUT = RESEARCH_TIMEOUT

RESEARCH_PROMPT = os.getenv(
    "COMMAND_CODE_PROMPT",
    (
        "Help me analyze this project's source code and identify critical 0-day "
        "vulnerabilities to report for CVEs, credit, and bounties. Assist me in "
        "conducting a thorough analysis to uncover genuine, high-value security "
        "flaws—avoiding issues stemming merely from user error or misconfiguration—"
        "with a specific focus on RCE, deserialization, path traversal, SSRF, SQLi, "
        "XXE, and XSS."
    ),
).strip()
COMMAND_CODE_PROMPT = RESEARCH_PROMPT

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))

DEFAULT_PRESET_ID = "command-code"


def quote_prompt(prompt: str | None = None) -> str:
    text = (prompt or RESEARCH_PROMPT).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _command_code_command() -> str:
    return (
        "command-code --yolo --skip-onboarding --print --tools-all "
        f"--model {COMMAND_CODE_MODEL} {quote_prompt()}"
    )


def _opencode_command() -> str:
    model = f"--model {OPENCODE_MODEL} " if OPENCODE_MODEL else ""
    return f"opencode run --auto {model}{quote_prompt()}".replace("  ", " ").strip()


def _freebuff_command() -> str:
    return f"freebuff {quote_prompt()}"


def _claude_command() -> str:
    model = f"--model {CLAUDE_MODEL} " if CLAUDE_MODEL else ""
    return (
        f"claude --print --permission-mode dontAsk --verbose {model}{quote_prompt()}"
    ).replace("  ", " ").strip()


def _codex_command() -> str:
    return f"codex exec --full-auto {quote_prompt()}"


RESEARCH_PRESETS: list[dict[str, Any]] = [
    {
        "id": "command-code",
        "label": "command-code",
        "binary": "command-code",
        "bin_env": "COMMAND_CODE_BIN",
        "default_bin": COMMAND_CODE_BIN,
        "build": _command_code_command,
        "required_groups": (
            ("--skip-onboarding",),
            ("--print",),
            ("--tools-all",),
        ),
        "hint": "Default. Keep --print so the browser can stream logs.",
    },
    {
        "id": "opencode",
        "label": "opencode",
        "binary": "opencode",
        "bin_env": "OPENCODE_BIN",
        "default_bin": OPENCODE_BIN,
        "build": _opencode_command,
        "required_groups": (("run",), ("--auto",)),
        "hint": "Uses `opencode run --auto` for non-interactive analysis.",
    },
    {
        "id": "freebuff",
        "label": "freebuff",
        "binary": "freebuff",
        "bin_env": "FREEBUFF_BIN",
        "default_bin": FREEBUFF_BIN,
        "build": _freebuff_command,
        "required_groups": (),
        "hint": "Freebuff CLI. Edit flags if your install needs different headless options.",
    },
    {
        "id": "claude",
        "label": "claude",
        "binary": "claude",
        "bin_env": "CLAUDE_BIN",
        "default_bin": CLAUDE_BIN,
        "build": _claude_command,
        "required_groups": (
            ("--print",),
            ("--permission-mode", "dontAsk"),
            ("--verbose",),
        ),
        "hint": "Claude Code print mode. Prefer --permission-mode dontAsk for headless runs.",
    },
    {
        "id": "codex",
        "label": "codex",
        "binary": "codex",
        "bin_env": "CODEX_BIN",
        "default_bin": CODEX_BIN,
        "build": _codex_command,
        "required_groups": (("exec",), ("--full-auto",)),
        "hint": "OpenAI Codex CLI non-interactive exec mode.",
    },
]


def get_preset(preset_id: str | None) -> dict[str, Any] | None:
    if not preset_id:
        return None
    for preset in RESEARCH_PRESETS:
        if preset["id"] == preset_id:
            return preset
    return None


def default_research_command(preset_id: str | None = None) -> str:
    preset = get_preset(preset_id) or get_preset(DEFAULT_PRESET_ID)
    assert preset is not None
    return preset["build"]()


def resolve_binary_path(name: str, configured: str | None = None) -> str | None:
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    candidates.append(name)
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.exists():
            return str(path)
        found = shutil.which(candidate)
        if found:
            return found
    if name in {"command-code", "commandcode"}:
        fnm_root = Path.home() / ".local/share/fnm/node-versions"
        if fnm_root.exists():
            matches = sorted(fnm_root.glob("*/installation/bin/command-code"), reverse=True)
            if matches:
                return str(matches[0])
    if name == "opencode":
        local = Path.home() / ".opencode/bin/opencode"
        if local.exists():
            return str(local)
    return None


def binary_available(preset: dict[str, Any]) -> bool:
    return resolve_binary_path(preset["binary"], preset.get("default_bin")) is not None


def infer_preset_id(command: str) -> str:
    text = command.strip()
    if not text:
        return "custom"
    try:
        import shlex

        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts:
        return "custom"
    binary = Path(parts[0]).name.lower()
    aliases = {
        "command-code": "command-code",
        "commandcode": "command-code",
        "cmdc": "command-code",
        "opencode": "opencode",
        "freebuff": "freebuff",
        "claude": "claude",
        "codex": "codex",
    }
    return aliases.get(binary, "custom")


def list_presets() -> list[dict[str, Any]]:
    items = []
    for preset in RESEARCH_PRESETS:
        items.append(
            {
                "id": preset["id"],
                "label": preset["label"],
                "binary": preset["binary"],
                "hint": preset["hint"],
                "command": preset["build"](),
                "available": binary_available(preset),
            }
        )
    items.append(
        {
            "id": "custom",
            "label": "Custom",
            "binary": "",
            "hint": "Write any shell-free argv command. First token is the binary.",
            "command": "",
            "available": True,
        }
    )
    return items


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
