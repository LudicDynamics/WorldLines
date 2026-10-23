"""The player's sheet for a front end (10-14, the standard front end §5.9): every attribute / skill with its name in this
run's language, a one-line description and its value — the 跑团 numbers readable at a glance.

    GET /api/v1/play/engine/sheet
    → {lang, name, hp?: {current, max}, system?,
       attrs:  [{key, label, value, desc, check?}],
       skills: [{key, name, label, value, desc, check?}]}

The values are the player's own (``game/player/stats.json`` → the registry's ``player`` entry: ``attributes`` a
{key: value} map, ``skills`` a {name: value} map or a [{name, value}] list — keys stay as authored). The engine alone
knows no labels: without a pack the label is the key and the description is empty. A pack names them through the
``sheet`` seam (core/mechanics): ``fn(root, reg, sheet, lang) -> sheet`` — rpg / pct read their rule table's rows
(``attrs`` / ``skills``: ``{zh, en, ja, ko, desc: {lang: line}}``, a world adds or overrides rows in
``game/rules/rules.json``), pct adds ``check`` (the percentage a roll must come under).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _num(v: Any) -> Any:
    if isinstance(v, dict):  # {current, max} meters on a sheet
        return v.get("current", v.get("value"))
    return v


def raw(reg: Any) -> dict[str, Any]:
    """The player's numbers as the engine knows them, labels = keys."""
    e = reg.entries.get("player")
    props = (e.props if e is not None else None) or {}
    attrs = [{"key": str(k), "label": str(k), "value": _num(v), "desc": ""}
             for k, v in (props.get("attributes") or {}).items()] if isinstance(props.get("attributes"), dict) else []
    sk = props.get("skills") or []
    # a skill written as a list item may carry its own line (a builder's origin grants {"name": "骇入", "desc": "…"})
    items = ((n, v, "") for n, v in sk.items()) if isinstance(sk, dict) else \
        ((x.get("name"), x.get("value"), x.get("desc") or "") for x in sk if isinstance(x, dict))
    skills = [{"key": str(n), "name": str(n), "label": str(n), "value": _num(v), "desc": str(d)} for n, v, d in items if n]
    out: dict[str, Any] = {"name": str((e.name if e is not None else "") or ""), "attrs": attrs, "skills": skills}
    if props.get("hp") is not None:
        out["hp"] = {"current": props.get("hp"), "max": props.get("max_hp")}
    return out


def sheet(root: Path, lang: str | None = None, reg: Any = None) -> dict[str, Any]:
    from neonrp.core import mechanics
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    reg = reg if reg is not None else load_registry(root)
    out = {"lang": lang, **raw(reg)}
    try:
        named = mechanics.get(root, "sheet")(root, reg, out, lang)
        if isinstance(named, dict):
            out = named
    except Exception:  # noqa: BLE001 — a pack's labels never break the sheet
        logger.warning("sheet seam failed; raw keys", exc_info=True)
    return out


def find(sh: dict[str, Any], token: str) -> dict[str, Any] | None:
    """A skill (first) or an attribute row by any of its names — key, name, label (case-insensitive) — or None."""
    t = str(token or "").strip().casefold()
    if not t:
        return None
    for kind in ("skills", "attrs"):
        for row in sh.get(kind) or []:
            names = {str(row.get(f) or "").casefold() for f in ("key", "name", "label")} | {str(a).casefold() for a in row.get("aliases") or []}
            if t in names:
                return {**row, "kind": "skill" if kind == "skills" else "attr"}
    return None
