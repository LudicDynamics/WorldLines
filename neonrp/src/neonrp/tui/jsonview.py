"""Adaptive JSON → readable doc renderer.

Turns an arbitrary JSON-shaped value into a markdown-ish Rich renderable
so a state file can be shown to a player without dumping raw JSON:

* dict        → each key is a row; nested dicts become indented sections
* list        → bullet rows; a list of dicts is rendered compactly
* scalar      → ``key  value``

It is deliberately structure-driven (no schema): whatever keys the game
state files carry render automatically. Key names are humanized
(``hp`` → ``Hp``, ``status_effects`` → ``Status effects``) and a few
common keys get a glyph.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.text import Text

# Accent palette — WorldLines green family, kept consistent with theme.py.
_SECTION = "#18FF82"
_KEY = "#7f9a86"
_VALUE = "#d8d2c0"
_NUM = "#9BE89B"
_BULLET = "#3FB36A"
_DIM = "#4a4458"

# A glyph for a few well-known keys; everything else just indents.
_KEY_GLYPH: dict[str, str] = {
    "hp": "♥", "mp": "✦", "san": "◈", "sanity": "◈",
    "gold": "⬤", "silver": "○", "copper": "•",
    "level": "▲", "skills": "⚔", "inventory": "▣", "items": "▣",
    "stats": "▦", "attributes": "▦", "wallet": "⬤", "equipment": "⛨",
    "flags": "⚑", "status_effects": "✷", "location": "⌖", "time": "⏲",
}


def _humanize(key: str) -> str:
    """``status_effects`` → ``Status effects``."""
    return str(key).replace("_", " ").replace("-", " ").strip().capitalize()


def _fmt_scalar(value: Any) -> tuple[str, str]:
    """Return (text, style) for a leaf value."""
    if isinstance(value, bool):
        return ("✓" if value else "✗", _NUM if value else _DIM)
    if isinstance(value, (int, float)):
        return (str(value), _NUM)
    s = str(value).strip()
    return (s or "—", _VALUE)


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _compact_dict(d: dict[str, Any]) -> str | None:
    """If every value in ``d`` is scalar, render it as one inline row
    (``a 1 · b 2``); else None so the caller recurses."""
    if not d or not all(_is_scalar(v) for v in d.values()):
        return None
    parts = []
    for k, v in d.items():
        txt, _ = _fmt_scalar(v)
        parts.append(f"{_humanize(k).lower()} {txt}")
    return "  ·  ".join(parts)


def _walk(value: Any, depth: int, rows: list[Text], glyphs: dict[str, str] | None = None) -> None:
    indent = "  " * depth
    table = glyphs if glyphs is not None else _KEY_GLYPH
    if isinstance(value, dict):
        for key, val in value.items():
            glyph = table.get(str(key).lower(), "")
            label = _humanize(key)
            if _is_scalar(val):
                txt, vstyle = _fmt_scalar(val)
                row = Text(indent)
                if glyph:
                    row.append(f"{glyph} ", style=_SECTION)
                row.append(f"{label}  ", style=_KEY)
                row.append(txt, style=vstyle)
                rows.append(row)
            elif isinstance(val, dict):
                inline = _compact_dict(val)
                row = Text(indent)
                if glyph:
                    row.append(f"{glyph} ", style=_SECTION)
                row.append(label, style=f"bold {_SECTION}")
                if inline is not None:
                    row.append("  ", style="")
                    row.append(inline, style=_VALUE)
                    rows.append(row)
                else:
                    rows.append(row)
                    _walk(val, depth + 1, rows, glyphs)
            elif isinstance(val, list):
                row = Text(indent)
                if glyph:
                    row.append(f"{glyph} ", style=_SECTION)
                row.append(label, style=f"bold {_SECTION}")
                row.append(f"  ({len(val)})", style=_DIM)
                rows.append(row)
                _walk(val, depth + 1, rows, glyphs)
    elif isinstance(value, list):
        if not value:
            rows.append(Text(f"{indent}—", style=_DIM))
            return
        for item in value:
            if isinstance(item, dict):
                # A dict item: prefer name/id as the headline, rest inline.
                head = (
                    item.get("name")
                    or item.get("id")
                    or item.get("label")
                    or ""
                )
                rest = {
                    k: v for k, v in item.items()
                    if k not in ("name", "id", "label") and _is_scalar(v)
                }
                row = Text(indent)
                row.append("• ", style=_BULLET)
                if head:
                    row.append(str(head), style=_VALUE)
                tail = _compact_dict(rest) if rest else None
                if tail:
                    row.append(f"   {tail}", style=_KEY)
                rows.append(row)
                # Any nested non-scalar fields recurse one level deeper.
                nested = {
                    k: v for k, v in item.items()
                    if not _is_scalar(v)
                }
                if nested:
                    _walk(nested, depth + 1, rows, glyphs)
            else:
                txt, vstyle = _fmt_scalar(item)
                row = Text(indent)
                row.append("• ", style=_BULLET)
                row.append(txt, style=vstyle)
                rows.append(row)
    else:
        txt, vstyle = _fmt_scalar(value)
        rows.append(Text(f"{indent}{txt}", style=vstyle))


def render_json_doc(data: Any, *, title: str | None = None, glyphs: dict[str, str] | None = None) -> Group:
    """Render ``data`` as an adaptive, readable Rich document.

    ``glyphs`` replaces the default key→glyph table (the play status column
    passes its icon set); the humanized key text is always kept, so an
    unknown key simply renders without an icon."""
    rows: list[Text] = []
    if title:
        head = Text()
        head.append("▍ ", style=_SECTION)
        head.append(str(title), style=f"bold {_SECTION}")
        rows.append(head)
        rows.append(Text(""))
    if data in (None, {}, []):
        rows.append(Text("  (no state yet)", style=_DIM))
    else:
        _walk(data, 0, rows, glyphs)
    return Group(*rows)
