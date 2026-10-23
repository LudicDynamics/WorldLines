"""WorldLines player profile management.

Player profiles are stored in ``~/.worldlines/players/``.
Each profile is a JSON file with customizable character info
that gets merged into the template's ``player.json`` at game start.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import click

logger = logging.getLogger(__name__)

PLAYERS_HOME = Path.home() / ".worldlines" / "players"

# v0.2.2 — the 分身 (player avatar) library. A 分身 is a *lightweight,
# local-only* player profile, deliberately SEPARATE from the soul library
# (`~/.worldlines/souls/`): a character (soul) cannot be a 分身, and a 分身 is
# never published. The avatar store IS this player-profile store; these names
# are the avatar-facing vocabulary for it.
AVATAR_HOME = PLAYERS_HOME

# Minimal fields a player profile must have
_REQUIRED = ("name",)

# Fields the user can customize (others come from template)
_EDITABLE_FIELDS = {
    "name": "角色名",
    "summary": "角色简介",
    "gender": "性别",
    "personality": "性格特征",
    "appearance": "外貌描述",
    "backstory": "背景故事",
}


def _ensure_dir() -> None:
    PLAYERS_HOME.mkdir(parents=True, exist_ok=True)


def list_players() -> list[dict[str, Any]]:
    """Return saved player profiles sorted by mtime (newest first)."""
    _ensure_dir()
    cur = current_avatar()
    profiles: list[dict[str, Any]] = []
    for f in PLAYERS_HOME.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles.append({
                "path": f,
                "file": f.stem,
                "name": data.get("name", f.stem),
                "summary": data.get("summary", ""),
                "data": data,
                "current": f.stem == cur,
                "portrait_url": portrait_url(f.stem) if portrait_path(f.stem) else None,
            })
        except Exception:
            continue
    profiles.sort(key=lambda p: p["path"].stat().st_mtime, reverse=True)
    return profiles


# 10-15 (Hub「我的」): one 分身 is the *current* one — the front end opens a run with it as the player
# (``avatar`` on POST /api/v1/play/session). Its portrait sits next to it: ``<file>.portrait.<ext>``.
_CURRENT = ".current"
PORTRAIT_EXTS = (".png", ".jpg", ".webp")


def _safe_stem(file_stem: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in str(file_stem)).strip("-")


def current_avatar() -> str | None:
    """The current 分身's file stem: the one set, else the only one there is; None when none is saved."""
    try:
        cur = (PLAYERS_HOME / _CURRENT).read_text(encoding="utf-8").strip()
    except OSError:
        cur = ""
    if cur and (PLAYERS_HOME / f"{cur}.json").is_file():
        return cur
    files = sorted(PLAYERS_HOME.glob("*.json")) if PLAYERS_HOME.is_dir() else []
    return files[0].stem if len(files) == 1 else None


def set_current_avatar(file_stem: str) -> bool:
    stem = _safe_stem(file_stem)
    if not stem or not (PLAYERS_HOME / f"{stem}.json").is_file():
        return False
    (PLAYERS_HOME / _CURRENT).write_text(stem, encoding="utf-8")
    return True


def portrait_url(file_stem: str) -> str:
    from urllib.parse import quote

    return f"/api/v1/local/avatar/portrait?file={quote(file_stem)}"


def portrait_path(file_stem: str) -> Path | None:
    stem = _safe_stem(file_stem)
    return next((p for e in PORTRAIT_EXTS if (p := PLAYERS_HOME / f"{stem}.portrait{e}").is_file()), None) if stem else None


def save_portrait(file_stem: str, data: bytes) -> Path | None:
    """The 分身's portrait (png / jpg / webp by its bytes); None when no such 分身 or not an image."""
    stem = _safe_stem(file_stem)
    if not stem or not (PLAYERS_HOME / f"{stem}.json").is_file():
        return None
    ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg" if data[:3] == b"\xff\xd8\xff" else ".webp" if data[8:12] == b"WEBP" else ""
    if not ext:
        return None
    for e in PORTRAIT_EXTS:
        (PLAYERS_HOME / f"{stem}.portrait{e}").unlink(missing_ok=True)
    p = PLAYERS_HOME / f"{stem}.portrait{ext}"
    p.write_bytes(data)
    return p


def apply_avatar_to_run(root: Path, file_stem: str) -> bool:
    """Open a fresh run with this 分身 as the player: its fields over the world's player profile (a 分身 is written in
    one language, so a field it sets drops the world's per-language copies of it) and its portrait as the player's.
    Worlds without ``game/player/profile.json`` take the TUI's merge (cli._apply_player_profile). True = applied."""
    from neonrp.core.paths import get_data_dir_name

    stem = _safe_stem(file_stem)
    if not stem or not (PLAYERS_HOME / f"{stem}.json").is_file():
        return False
    prof = load_player(stem)
    game = Path(root) / get_data_dir_name(Path(root))
    pf = game / "player" / "profile.json"
    if not pf.is_file():
        from neonrp.cli import _apply_player_profile

        _apply_player_profile(Path(root), prof)
        return True
    cur = json.loads(pf.read_text(encoding="utf-8"))
    for k in _EDITABLE_FIELDS:
        if isinstance(prof.get(k), str) and prof[k].strip():
            cur[k] = prof[k].strip()
            cur.pop({"name": "name_i18n", "summary": "intro_i18n"}.get(k, f"{k}_i18n"), None)
    pf.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding="utf-8")
    pic = portrait_path(stem)
    if pic is not None:
        adir = game / "player" / "assets"
        adir.mkdir(parents=True, exist_ok=True)
        for e in (*PORTRAIT_EXTS, ".jpeg"):
            (adir / f"portrait{e}").unlink(missing_ok=True)
        (adir / f"portrait{pic.suffix}").write_bytes(pic.read_bytes())
    return True


def builder_prefill(t: Any, file_stem: str) -> dict[str, Any]:
    """The builder screen's draft prefilled from this 分身: every text field the template writes to one of the player
    profile's fields a 分身 has (``to: player/profile.json:<name|summary|appearance|…>``) → ``{"fields": {id: value}}``."""
    from neonrp.template import builder

    stem = _safe_stem(file_stem)
    if not stem or not (PLAYERS_HOME / f"{stem}.json").is_file() or not builder.declared(t):
        return {"fields": {}}
    prof = load_player(stem)
    out: dict[str, Any] = {}
    for f in builder._fields(builder.raw(t)):
        to = str(f.get("to") or "")
        key = to.split(":", 1)[1] if to.startswith("player/profile.json:") else ""
        if f.get("kind", "text") == "text" and key in _EDITABLE_FIELDS and isinstance(prof.get(key), str) and prof[key].strip():
            v = prof[key].strip()
            out[str(f.get("id"))] = v[: int(f["max"])] if isinstance(f.get("max"), int) else v
    return {"fields": out}


def save_avatar_fields(fields: dict[str, Any], file_stem: str | None = None) -> Path:
    """Write a 分身 from the 「我的」 page form (the editable fields only) — into ``file_stem`` when editing one, else a
    new file named after it — and make it the current one."""
    data = {k: str(fields[k]).strip() for k in _EDITABLE_FIELDS if isinstance(fields.get(k), str) and str(fields[k]).strip()}
    stem = _safe_stem(file_stem or "")
    editing = bool(stem and (PLAYERS_HOME / f"{stem}.json").is_file())
    if not data.get("name") and not editing:
        raise ValueError("name required")
    if editing:
        old = json.loads((PLAYERS_HOME / f"{stem}.json").read_text(encoding="utf-8"))
        path = PLAYERS_HOME / f"{stem}.json"
        path.write_text(json.dumps({**old, **data}, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path = save_player(data)
    set_current_avatar(path.stem)
    return path


def list_avatars() -> list[dict[str, Any]]:
    """List saved 分身 (player avatars), newest first. Alias of
    :func:`list_players` — the avatar store and the player-profile store are
    the same local directory; this is the avatar-facing name."""
    return list_players()


def save_avatar(data: dict[str, Any]) -> Path:
    """Save a 分身 (player avatar) profile. Alias of :func:`save_player`."""
    return save_player(data)


def load_player(file_stem: str) -> dict[str, Any]:
    """Load a player profile by filename (without .json)."""
    path = PLAYERS_HOME / f"{file_stem}.json"
    if not path.exists():
        raise FileNotFoundError(f"Player profile not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_player(data: dict[str, Any]) -> Path:
    """Save a player profile. Uses sanitized name as filename."""
    _ensure_dir()
    name = data.get("name", "player")
    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-")
    if not safe_name:
        safe_name = "player"
    path = PLAYERS_HOME / f"{safe_name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def merge_player_into_template(template_player: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Merge user's player profile into the template player entity.

    Profile fields override template fields. Template-specific fields
    (hp, location, inventory, special_abilities, etc.) are preserved.
    """
    merged = dict(template_player)
    # Override customizable fields from profile
    for key in _EDITABLE_FIELDS:
        if key in profile and profile[key]:
            merged[key] = profile[key]
    # Always preserve id and kind
    merged["id"] = "player"
    merged["kind"] = "player"
    return merged


def prompt_create_player() -> dict[str, Any] | None:
    """Interactive CLI prompt to create a new player profile.

    Returns the profile dict, or None if user cancels.
    """
    click.echo()
    click.echo("  创建新角色")
    click.echo()

    data: dict[str, Any] = {}
    for field, label in _EDITABLE_FIELDS.items():
        required = field in _REQUIRED
        hint = "（必填）" if required else "（可选，回车跳过）"
        while True:
            value = click.prompt(f"    {label} {hint}", default="", show_default=False).strip()
            if required and not value:
                click.echo("    请输入角色名。")
                continue
            if value:
                data[field] = value
            break

    if "name" not in data:
        return None

    # Save
    path = save_player(data)
    click.echo(f"\n  角色已保存: {path.name}")
    return data


def prompt_edit_player(profile: dict[str, Any]) -> dict[str, Any]:
    """Interactive CLI prompt to edit an existing player profile."""
    click.echo()
    click.echo(f"  编辑角色: {profile.get('name', '???')}")
    click.echo("  （回车保持原值）")
    click.echo()

    data = dict(profile)
    for field, label in _EDITABLE_FIELDS.items():
        current = data.get(field, "")
        display = current if current else "(空)"
        value = click.prompt(f"    {label} [{display}]", default="", show_default=False).strip()
        if value:
            data[field] = value

    save_player(data)
    click.echo("\n  已保存。")
    return data


# ---------------------------------------------------------------------------
# AI-powered player creation
# ---------------------------------------------------------------------------

_AI_GENERATE_PROMPT = """\
根据用户的一句话描述，生成一个RPG角色资料。返回纯JSON，不要markdown代码块。

JSON字段：
- name: 角色名（有创意的名字）
- summary: 一句话角色简介
- gender: 性别
- personality: 性格特征（2-3句）
- appearance: 外貌描述（2-3句）
- backstory: 背景故事（3-5句）

用户描述：{description}
"""


def _build_adapter_from_preset(preset_id: str) -> Any:
    """Build an LLM adapter directly from a preset ID (no game dir needed)."""
    from dataclasses import fields as dc_fields
    from neonrp.presets import build_config_dict
    from neonrp.core.config import ProviderConfig
    from neonrp.core.llm import get_adapter_from_config

    config_dict = build_config_dict(preset_id)
    model_ref = config_dict.get("llm", {}).get("model_ref", "")
    models = config_dict.get("models", {})
    model_data = models.get(model_ref, {})

    if not model_data or model_data.get("provider") == "stub":
        return None

    # Build ProviderConfig from model_data
    valid_fields = {f.name for f in dc_fields(ProviderConfig)}
    filtered = {k: v for k, v in model_data.items() if k in valid_fields}
    provider_config = ProviderConfig(**filtered)
    return get_adapter_from_config(provider_config)


def generate_player_from_description(preset_id: str, description: str) -> dict[str, Any] | None:
    """Use the selected LLM to generate a player profile from a one-line description.

    Returns the generated profile dict, or None on failure.
    """
    from neonrp.core.llm import Message

    adapter = _build_adapter_from_preset(preset_id)
    if adapter is None:
        return None

    try:
        result = adapter.chat([
            Message(role="system", content="你是一个RPG角色生成器。只返回JSON，不要其他文字。"),
            Message(role="user", content=_AI_GENERATE_PROMPT.format(description=description)),
        ])
        if result.message and result.message.content:
            text = result.message.content.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            return json.loads(text)
    except Exception as exc:
        logger.warning("AI player generation failed: %s", exc)
    return None


def _display_profile(data: dict[str, Any]) -> None:
    """Display a generated player profile for review."""
    click.echo()
    for field, label in _EDITABLE_FIELDS.items():
        value = data.get(field, "")
        if value:
            click.echo(f"    {label}: {value}")
    click.echo()


def prompt_ai_create_player(preset_id: str) -> dict[str, Any] | None:
    """AI-powered player creation: user gives a one-line description,
    LLM generates the full profile, user confirms/edits/regenerates.

    Returns the profile dict, or None if user cancels.
    """
    click.echo()
    description = click.prompt(
        "  请用一句话描述你的角色", default="", show_default=False
    ).strip()
    if not description:
        return None

    click.echo("\n  AI 生成中...")
    data = generate_player_from_description(preset_id, description)

    if data is None:
        click.echo("  生成失败，请重试或手动创建。")
        return None

    while True:
        _display_profile(data)

        click.echo("  1. 确认使用")
        click.echo("  2. 编辑后使用")
        click.echo("  3. 重新生成")
        click.echo("  4. 取消")
        click.echo()

        choice = click.prompt(">", type=str, default="1").strip()

        if choice == "1":
            path = save_player(data)
            click.echo(f"\n  角色已保存: {path.name}")
            return data

        if choice == "2":
            edited = prompt_edit_player(data)
            return edited

        if choice == "3":
            click.echo("\n  重新生成中...")
            new_data = generate_player_from_description(preset_id, description)
            if new_data is None:
                click.echo("  生成失败，保留当前结果。")
            else:
                data = new_data
            continue

        if choice == "4":
            return None
