"""User-level config (~/.neonrp/config.json) helpers.

User config stores preferences that apply across all neonrp projects:
- `ui.language` — preferred TUI locale (auto | en | zh | ja | ko)
- `updates.*`   — auto-update channel/mode (see core/updater.py)
- `models.*`    — saved model presets (see presets.py)
- `discord.*`   — Discord bridge config (see core/discord_config.py)

Project-level `.neonrp/config.json` can override any of these keys for
a specific game directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

USER_CONFIG_PATH = Path.home() / ".neonrp" / "config.json"


def load_user_config() -> dict[str, Any]:
    if not USER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_user_config(data: dict[str, Any]) -> None:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_user_locale() -> str:
    data = load_user_config()
    ui = data.get("ui")
    if isinstance(ui, dict):
        value = str(ui.get("language", "") or "").strip().lower()
        if value:
            return value
    return "auto"


def set_user_locale(locale: str) -> None:
    data = load_user_config()
    ui = data.get("ui") if isinstance(data.get("ui"), dict) else {}
    ui["language"] = locale
    data["ui"] = ui
    save_user_config(data)
