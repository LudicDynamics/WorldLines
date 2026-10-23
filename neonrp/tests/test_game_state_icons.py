"""任务 A3: the right status column shows icons for
well-known keys, and never drops the label when it has no icon."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from neonrp.tui.game_state_panel import STATE_ICONS, GameStatePanel, state_icon
from neonrp.tui.jsonview import render_json_doc


def _plain(renderable) -> str:
    console = Console(width=60, record=True, force_terminal=False, color_system=None)
    with console.capture() as cap:
        console.print(renderable)
    return cap.get()


def test_known_keys_have_icons():
    assert state_icon("hp") == "❤"
    assert state_icon("Health") == "❤"
    assert state_icon("money") == "💰" and state_icon("gold") == "💰"
    assert state_icon("inventory") == "🎒" and state_icon("items") == "🎒"
    assert state_icon("location") == "📍"
    assert state_icon("turn") == "⏱" and state_icon("time") == "🕒"
    assert state_icon("relationships") == "👥"
    assert state_icon("quest") == "📜" and state_icon("weather") == "🌤"
    assert state_icon("energy") == "⚡" and state_icon("mood") == "🙂"


def test_unknown_key_has_no_icon_but_keeps_its_label():
    assert state_icon("favourite_colour") == ""
    out = _plain(render_json_doc({"favourite_colour": "green", "hp": 7}, glyphs=STATE_ICONS))
    assert "Favourite colour" in out and "green" in out
    assert "❤ Hp" in out


def test_default_glyphs_are_unchanged_for_other_callers():
    out = _plain(render_json_doc({"hp": 7, "location": "gate"}))
    assert "♥ Hp" in out and "⌖ Location" in out


def test_panel_doc_uses_icons(tmp_path: Path):
    root = tmp_path / "w"
    (root / "game" / "meta").mkdir(parents=True)
    (root / "game" / "meta" / "run_state.json").write_text(json.dumps({"turn_count": 4, "time": {"day": 2}}), encoding="utf-8")
    (root / "game" / "player").mkdir()
    (root / "game" / "player" / "wallet.json").write_text(json.dumps({"gold": 12, "odd_thing": 1}), encoding="utf-8")
    (root / "game" / "player" / "inventory.json").write_text(json.dumps({"items": [{"name": "钥匙"}]}), encoding="utf-8")
    panel = GameStatePanel()
    panel._root = root
    out = _plain(panel._build_doc())
    assert "⏱ Turn" in out
    assert "🕒 Time" in out
    assert "💰 Gold" in out
    assert "Odd thing" in out, "labels survive without an icon"
    assert "🎒 Items" in out and "钥匙" in out
