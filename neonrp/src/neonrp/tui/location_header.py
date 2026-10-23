"""Pinned location header for the play/mcp transcript pane.

Reads ``game/meta/run_state.json`` to find the player's current location,
then resolves a display name + ambient hint from the matching
``game/location/<id>.json`` (or ``game/locations/<id>.json`` — older
templates use the plural). Renders a single-line label at the top of the
conversation pane that fades into the WorldLines art style: thin
divider, accent-colored name, dimmed ambient parenthetical.

The widget polls the run-state file mtime on an interval (cheap stat
call) and only re-reads when it changes. Empty / missing run-state →
panel collapses to a placeholder line so the layout doesn't pop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.widgets import Static


_LOCATION_DIRS = ("location", "locations")
_RUN_STATE_REL = ("game", "meta", "run_state.json")


def _read_run_state(root: Path) -> dict[str, Any] | None:
    p = root.joinpath(*_RUN_STATE_REL)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _resolve_location_node(root: Path, location_field: Any) -> dict[str, Any] | None:
    """Return the location JSON document, or None if not resolvable.

    Accepts the modern run_state shape (``{"node": "<id>", ...}``) and
    the older flat-string shape (just ``"north-gate"``).
    """
    if not location_field:
        return None
    node_id: str | None = None
    display: str | None = None
    if isinstance(location_field, dict):
        node_id = (
            location_field.get("node")
            or location_field.get("subnode_id")
            or location_field.get("node_id")
        )
        display = location_field.get("display")
    elif isinstance(location_field, str):
        node_id = location_field

    if not node_id:
        return {"name": display} if display else None

    for d in _LOCATION_DIRS:
        folder = root / "game" / d / node_id / "location.json"  # 任务 B2 folder form
        if folder.is_file():
            try:
                payload = json.loads(folder.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    return payload
            except (OSError, ValueError):
                pass
        cand = root / "game" / d / f"{node_id}.json"
        if cand.is_file():
            try:
                payload = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    if display and not payload.get("name"):
                        payload["name"] = display
                    return payload
            except Exception:
                pass

    # Fall back to whatever the run_state already says — at least name it.
    return {"name": display or node_id, "id": node_id}


def _ambient_hint(node: dict[str, Any]) -> str:
    """One-line ambient hint from a location node.

    Priority: ``summary`` → first entry of ``ambient_events`` → ``tags``
    joined with middle-dot. Returns empty string if nothing usable.
    """
    summary = str(node.get("summary") or "").strip()
    if summary:
        # Compress: take only the first sentence so the line stays single.
        for sep in ("。", ". ", ".\n", "\n"):
            if sep in summary:
                summary = summary.split(sep, 1)[0]
                break
        return summary

    ambient = node.get("ambient_events")
    if isinstance(ambient, list) and ambient:
        first = str(ambient[0] or "").strip()
        if first:
            return first.replace("-", " ")

    tags = node.get("tags")
    if isinstance(tags, list) and tags:
        return " · ".join(str(t) for t in tags[:4] if t)
    return ""


def _format_time(time_field: Any) -> str:
    if not isinstance(time_field, dict):
        return ""
    day = time_field.get("day")
    clock = str(time_field.get("clock") or "").strip()
    if day in {None, ""} and not clock:
        return ""
    if day in {None, ""}:
        return clock
    if clock:
        return f"D{day} · {clock}"
    return f"D{day}"


class LocationHeader(Static):
    """Single-line pinned location label for the play stage.

    Mounted above the ``#play-stage`` Horizontal. The widget owns its own
    interval timer — the rest of the app doesn't need to know it exists.
    """

    DEFAULT_INTERVAL = 2.0

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("", **kwargs)
        self._root: Path | None = None
        self._last_mtime: float = 0.0
        self._last_payload: str = ""
        # Set by the host app: called with the resolved location node dict
        # whenever the player moves to a *different* location. Used to
        # fire a scene text-to-image.
        self.on_change: Any | None = None
        self._last_location_key: str | None = None
        self._mode: str = ""  # 10-08: the mode layer the world is in (combat / dungeon …), shown as a standing tag

    def set_root(self, root: Path | None) -> None:
        self._root = Path(root) if root else None
        self._last_mtime = 0.0
        self._last_payload = ""
        self._last_location_key = None
        self.refresh_location(force=True)

    def on_mount(self) -> None:
        self.set_interval(self.DEFAULT_INTERVAL, self.refresh_location)

    def refresh_location(self, force: bool = False) -> None:
        """Re-read run_state.json if its mtime changed; update the label."""
        if self._root is None:
            return
        rs_path = self._root.joinpath(*_RUN_STATE_REL)
        try:
            mtime = rs_path.stat().st_mtime if rs_path.exists() else 0.0
        except OSError:
            mtime = 0.0
        if not force and mtime == self._last_mtime:
            return
        self._last_mtime = mtime

        state = _read_run_state(self._root) or {}
        node = _resolve_location_node(self._root, state.get("location")) or {}
        name = str(node.get("name") or "").strip()
        ambient = _ambient_hint(node)
        when = _format_time(state.get("time"))

        # Fire the on_change hook when the player moved to a new location.
        # Keyed on id-or-name so it survives a missing id field.
        location_key = str(node.get("id") or name or "").strip()
        if location_key and location_key != self._last_location_key:
            first_seen = self._last_location_key is None
            self._last_location_key = location_key
            # Skip the very first resolution (force=True at mount) — the
            # cover image is kicked separately by the host.
            if not first_seen and callable(self.on_change):
                try:
                    self.on_change(node)
                except Exception:
                    pass

        # No location info at all → keep the bar empty (one-line spacer).
        if not name and not when:
            new_payload = ""
            if new_payload == self._last_payload:
                return
            self._last_payload = new_payload
            self.update(Text(""))
            return

        payload_key = f"{name}|{when}|{ambient}|{self._mode}"
        if payload_key == self._last_payload:
            return
        self._last_payload = payload_key
        self.update(self._build_card(name, when, ambient))

    def set_mode(self, label: str | None) -> None:
        """The mode layer the world is in, as a standing tag after the place (``⚔ 战斗裁判``); None / "" clears it."""
        label = str(label or "")
        if label == self._mode:
            return
        self._mode = label
        self.refresh_location(force=True)

    def _build_card(self, name: str, when: str, ambient: str):
        """One line: `D1 · 08:30   石津镇 · 北门   ◇ ambient`.

        「中间这个像素大字有点多余」— the block-font scene
        card (bigtext.render_scene_card) is gone; the same three facts fit
        on one row and give the transcript the rows back."""
        line = Text()
        if when:
            line.append(f" {when}", style="bold #18FF82")
            line.append("   ")
        line.append("▍ ", style="#18FF82")
        line.append(name or "?", style="bold #eafdf1")
        if ambient:
            line.append("   ◇ ", style="#18FF82")
            line.append(ambient, style="dim #9BE89B italic")
        if self._mode:
            line.append("   ⚔ ", style="bold #fbbf24")
            line.append(self._mode, style="bold #fbbf24")
        return line
