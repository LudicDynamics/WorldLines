"""Adaptive game-state panel — sits beside the scene image.

Aggregates the player's state files (``game/player/*.json``) plus the
run-state summary into one readable doc, rendered via
:mod:`neonrp.tui.jsonview` so it's never raw JSON. The panel owns its
own poll timer: it re-reads when any source file's mtime changes, so
state edits made by the engine show up without turn-event plumbing.

Source files are not schema-fixed — whatever ``player/`` carries gets
rendered. New state files a world ships are picked up automatically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from neonrp.tui.i18n import get_message
from neonrp.tui.jsonview import render_json_doc

# 任务 A3: icons instead of words where a word has a
# well-known icon. The label text is always kept next to the icon — an
# unknown key just gets no icon, never a dropped label — so a terminal
# without emoji fonts still reads.
STATE_ICONS: dict[str, str] = {
    "turn": "⏱", "turn_count": "⏱",
    "time": "🕒", "clock": "🕒", "day": "📅", "date": "📅",
    "location": "📍", "place": "📍", "position": "📍",
    "hp": "❤", "health": "❤", "life": "❤",
    "mp": "✦", "mana": "✦",
    "energy": "⚡", "stamina": "⚡", "ap": "⚡",
    "san": "◈", "sanity": "◈",
    "money": "💰", "gold": "💰", "coins": "💰", "wallet": "💰", "silver": "○", "copper": "•",
    "items": "🎒", "inventory": "🎒", "bag": "🎒",
    "equipment": "⛨", "weapon": "⚔", "skills": "⚔",
    "relationships": "👥", "relations": "👥", "friends": "👥", "party": "👥",
    "mood": "🙂", "emotion": "🙂", "feeling": "🙂",
    "weather": "🌤", "climate": "🌤",
    "quest": "📜", "quests": "📜", "task": "📜", "tasks": "📜", "goal": "📜", "goals": "📜",
    "level": "▲", "xp": "▲", "exp": "▲",
    "flags": "⚑", "status_effects": "✷", "stats": "▦", "attributes": "▦",
    "last_action": "➤", "notes": "📝", "memo": "📝",
}


def state_icon(key: str) -> str:
    """Icon for a state key (empty string when we have none)."""
    return STATE_ICONS.get(str(key).strip().lower(), "")

# Player-state files surfaced in the panel, in display order. Anything
# present is shown; anything missing is silently skipped. The second
# element is the i18n key for the section label.
_PLAYER_FILES: tuple[tuple[str, str], ...] = (
    ("stats.json", "game_state.stats"),
    ("wallet.json", "game_state.wallet"),
    ("equipment.json", "game_state.equipment"),
    ("inventory.json", "game_state.inventory"),
    ("flags.json", "game_state.flags"),
)
_RUN_STATE_REL = ("game", "meta", "run_state.json")


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class GameStatePanel(Static):
    """Right-of-image panel rendering player state as an adaptive doc."""

    DEFAULT_INTERVAL = 2.0

    @property
    def is_scrollable(self) -> bool:
        """Yes — even though this is a leaf widget.

        Textual gates scrolling on ``styles.layout is not None or
        self._nodes``, and a ``Static`` that renders one doc has neither, so
        ``_refresh_scrollbars`` returns before it ever looks at
        ``overflow-y``. The CSS said the panel scrolled; it did not.

        The content is whatever ``game/player/`` happens to carry, so it
        routinely outgrows the 20-row stage band — the panel has to scroll
        or the bottom of the player's own state is simply unreachable.
        """
        return True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._root: Path | None = None
        self._sig: tuple = ()

    def set_root(self, root: Path | None) -> None:
        self._root = Path(root) if root else None
        self._sig = ()
        self.refresh_state(force=True)

    def on_mount(self) -> None:
        self.set_interval(self.DEFAULT_INTERVAL, self.refresh_state)

    def _source_paths(self) -> list[Path]:
        if self._root is None:
            return []
        paths = [self._root.joinpath(*_RUN_STATE_REL)]
        player_dir = self._root / "game" / "player"
        for fname, _ in _PLAYER_FILES:
            paths.append(player_dir / fname)
        return paths

    def _mtime_sig(self) -> tuple:
        """Cheap change signature — mtimes of every source file."""
        sig: list[float] = []
        for p in self._source_paths():
            try:
                sig.append(p.stat().st_mtime if p.exists() else 0.0)
            except OSError:
                sig.append(0.0)
        return tuple(sig)

    def refresh_state(self, force: bool = False) -> None:
        """Re-read + repaint when any source file changed."""
        if self._root is None:
            return
        sig = self._mtime_sig()
        if not force and sig == self._sig:
            return
        self._sig = sig
        self.update(self._build_doc())

    def _locale(self) -> str:
        try:
            return getattr(self.app, "ui_locale", None) or getattr(self.app, "locale", "en")
        except Exception:
            return "en"

    def _build_doc(self) -> Group:
        """Merge run-state + player files into one rendered doc."""
        rows: list[Any] = []
        locale = self._locale()

        title = Text()
        title.append("▍ ", style="#18FF82")
        title.append(get_message(locale, "game_state.title"), style="bold #18FF82")
        rows.append(title)
        rows.append(Text(""))

        run = _read_json(self._root.joinpath(*_RUN_STATE_REL))
        if isinstance(run, dict):
            summary: dict[str, Any] = {}
            if run.get("turn_count") is not None:
                summary["turn"] = run.get("turn_count")
            if isinstance(run.get("time"), dict):
                summary["time"] = run["time"]
            if run.get("last_action"):
                summary["last_action"] = run["last_action"]
            if summary:
                rows.append(render_json_doc(summary, glyphs=STATE_ICONS))
                rows.append(Text(""))

        player_dir = self._root / "game" / "player"
        any_player = False
        for fname, label_key in _PLAYER_FILES:
            data = _read_json(player_dir / fname)
            if data in (None, {}, []):
                continue
            any_player = True
            rows.append(render_json_doc(data, title=get_message(locale, label_key), glyphs=STATE_ICONS))
            rows.append(Text(""))

        if not any_player and not isinstance(run, dict):
            rows.append(Text(f"  {get_message(locale, 'game_state.empty')}", style="#4a4458"))

        return Group(*rows)
