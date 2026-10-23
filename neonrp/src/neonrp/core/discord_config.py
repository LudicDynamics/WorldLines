"""Discord bootstrap config helpers (L14 Phase 0).

Phase 0: we only *store* Discord connection info in the user config.
No gateway client, no actual relay. Phase 1 (tracked in ../buddy-bot)
will add the runtime bridge that reads this same config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

USER_CONFIG_PATH = Path.home() / ".neonrp" / "config.json"

DEFAULT_RELAY_MODE = "mirror"
VALID_RELAY_MODES = ("mirror", "input-only", "bidirectional")


def _read_config() -> dict[str, Any]:
    if not USER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_config(data: dict[str, Any]) -> None:
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_discord_settings() -> dict[str, Any]:
    data = _read_config()
    raw = data.get("discord")
    return raw if isinstance(raw, dict) else {}


def set_discord_settings(
    *,
    application_id: str | None = None,
    bot_token: str | None = None,
    channel_id: str | None = None,
    guild_id: str | None = None,
    relay_mode: str | None = None,
    autostart: bool | None = None,
    connected: bool | None = None,
) -> dict[str, Any]:
    data = _read_config()
    current = data.get("discord") if isinstance(data.get("discord"), dict) else {}

    if application_id is not None:
        current["application_id"] = application_id.strip()
    if bot_token is not None:
        current["bot_token"] = bot_token.strip()
    if channel_id is not None:
        current["channel_id"] = channel_id.strip()
    if guild_id is not None:
        current["guild_id"] = guild_id.strip()
    if relay_mode is not None:
        rm = relay_mode.strip().lower()
        if rm not in VALID_RELAY_MODES:
            rm = DEFAULT_RELAY_MODE
        current["relay_mode"] = rm
    if autostart is not None:
        current["autostart"] = bool(autostart)
    if connected is not None:
        current["connected"] = bool(connected)

    current.setdefault("relay_mode", DEFAULT_RELAY_MODE)
    current.setdefault("connected", False)
    current.setdefault("autostart", False)
    current.setdefault("last_check", None)

    data["discord"] = current
    _write_config(data)
    return current


def clear_discord_settings() -> None:
    data = _read_config()
    if "discord" in data:
        del data["discord"]
        _write_config(data)


def get_discord_inline_status() -> str:
    """Return the status fragment shown in TUI inline metadata."""
    settings = get_discord_settings()
    if not settings.get("bot_token"):
        return "off"
    if settings.get("connected"):
        return "on"
    return "pending"


def _looks_like_snowflake(value: str) -> bool:
    """Discord snowflake IDs are 17–20 digit integers."""
    v = str(value or "").strip()
    return v.isdigit() and 15 <= len(v) <= 22


def extract_client_id(application_id: str, bot_token: str) -> str | None:
    """Return the numeric client_id (Application ID) for OAuth URLs.

    Priority:
    1. If `application_id` is set and looks like a snowflake → use it.
    2. Else try to decode it from the bot token's first segment. Bot tokens
       are formatted as `<b64(application_id)>.<b64(timestamp)>.<hmac>`;
       base64-decoding the first segment gives the numeric ID.
    3. Return None if neither works — caller should ask user for the
       Application ID explicitly.
    """
    import base64

    app_id = str(application_id or "").strip()
    if _looks_like_snowflake(app_id):
        return app_id

    token = str(bot_token or "").strip()
    if not token:
        return None
    first = token.split(".", 1)[0]
    if not first:
        return None
    # Standard base64 needs padding to a multiple of 4.
    padded = first + "=" * (-len(first) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii", "ignore")
    except Exception:
        return None
    if _looks_like_snowflake(decoded):
        return decoded
    return None


def discord_oauth_invite_url(application_id: str = "", bot_token: str = "") -> str | None:
    """Build a Discord OAuth invite URL, or None if client_id can't be resolved.

    Required: either a valid `application_id` (numeric) OR a bot token
    whose first segment decodes to a valid snowflake id.
    """
    client_id = extract_client_id(application_id, bot_token)
    if not client_id:
        return None
    scope = "bot"
    permissions = "2147534848"  # Read Messages + Send Messages + View Channel
    return (
        f"https://discord.com/api/oauth2/authorize?client_id={client_id}"
        f"&scope={scope}&permissions={permissions}"
    )
