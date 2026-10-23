"""What the player can do right now, for a front end's `/` `@` `#` completion and its quick bar (10-14, the standard
front end §5.11) — everything read from the run, nothing a world has to declare twice.

    GET /api/v1/play/engine/actions
    → {lang,
       actions: [{name, label, help, args_hint, prompt, cmd, common}],    the world's play actions (game/meta/actions.json)
       verbs:   [{kind, label, help, cmd?}],                               the engine's own structured actions (skill / inspect / pick)
       skills:  [{key, name, label, value, desc, check?, cmd, common}],   the sheet (core/sheet), highest first
       items:   [{id, name, cls, held, cmd}],                             carried (held) + loose things where the player stands
       places:  [{id, name, here, near, cmd}],                            known places on the player's level; near = one step away
       people:  [{id, sid?, name, cls, companion, cmd}],                  named people where the player stands
       quick:   [{kind, text, label}]}                                     the quick bar: people (@) · common skills (/) · held items (#)

The world's action table (``game/meta/actions.json`` ``actions``: ``[{name, help, args_hint, prompt}]``, the run's
language layer already applied) may mark rows ``"common": true`` and give a ``label``; with no row marked, the first
``COMMON_ACTIONS`` in authored order are the common ones. The same table drives the TUI's `/` commands
(tui/commands.py) and, sent as text (「/go 3车」), the engine's own expansion (core/player_action).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

COMMON_ACTIONS = 4
COMMON_SKILLS = 4
NAME_RE = re.compile(r"^[\w][\w\-]{0,31}$")


def _label(raw: Any, name: str, lang: str, defaults: dict[str, Any]) -> str:
    """A row's ``label`` (a string, or {zh, en, ja, ko}); none → the engine's word for a common verb in this run's
    language (go → 前往 / Go / 移動 / 이동, player_action strings ``action_labels``); else the name."""
    if isinstance(raw, dict):
        raw = raw.get(lang) or raw.get("en") or ""
    return str(raw or "").strip() or str(defaults.get(name.casefold()) or "") or name


def world_actions(root: Path) -> list[dict[str, Any]]:
    """The world's play actions, validated (bad rows skipped, never fatal): [{name, label, help, args_hint, prompt, common}]."""
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.paths import get_data_dir_name

    lang = prompt_lang(Path(root))
    defaults = _T(Path(root)).get("action_labels") or {}

    try:
        raw = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "actions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = raw.get("actions") if isinstance(raw, dict) else raw
    out: list[dict[str, Any]] = []
    for e in rows if isinstance(rows, list) else []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip().lstrip("/")
        prompt = str(e.get("prompt") or "").strip()
        if not name or not prompt or not NAME_RE.match(name) or any(r["name"] == name for r in out):
            continue
        out.append({"name": name, "label": _label(e.get("label"), name, lang, defaults), "help": str(e.get("help") or "").strip() or prompt,
                    "args_hint": str(e.get("args_hint") or "").strip(), "prompt": prompt, "common": bool(e.get("common"))})
    if out and not any(r["common"] for r in out):
        for r in out[:COMMON_ACTIONS]:
            r["common"] = True
    return out


def expand(row: dict[str, Any], args: str) -> str:
    """A world action's prompt with its arguments (``{args}``; nothing given → the placeholder goes, the line stays)."""
    p = str(row.get("prompt") or "")
    a = str(args or "").strip()
    return p.replace("{args}", a).strip() if "{args}" in p else (f"{p} {a}".strip() if a else p)


def _T(root: Path) -> dict[str, Any]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.prompts import strings

    return strings("player_action", prompt_lang(root))


def _people(root: Path, reg: Any) -> list[dict[str, Any]]:
    from neonrp.core import holdings

    here = reg.player_location
    party = holdings.members(root)
    roles = holdings._souls(root)
    out = []
    for e in reg.entries.values():
        if e.id == "player" or not here or e.parent != here or not reg.is_person(e.cls):
            continue
        st = e.props.get("state") if isinstance(e.props.get("state"), dict) else {}
        if e.cls == "npc" and not (e.props.get("met") or st.get("met")):
            continue  # someone you have not met has no name to call yet
        name = str(e.name or "")
        if not name or name == e.id:
            continue
        sid = str(e.props.get("sid") or "")
        out.append({"id": e.id, **({"sid": sid} if sid else {}), "name": name, "cls": e.cls,
                    "companion": (e.id in party) if party is not None else roles.get(e.id, {}).get("role") == "companion", "cmd": f"@{name}"})
    return out


def _items(reg: Any) -> list[dict[str, Any]]:
    from neonrp.core import player_action

    out = []
    for e in reg.things_of("player"):
        spec = reg.classes.get(e.cls)
        if spec is not None and getattr(spec, "effect", False):
            continue
        out.append({"id": e.id, "name": str(e.name or e.id), "cls": e.cls, "held": True, "cmd": f"#{e.name or e.id}"})
    for e in reg.entries.values():
        if e.id == "player" or any(x["id"] == e.id for x in out):
            continue
        if player_action.reach(reg, "pick", e.id) is None:  # loose where the player stands and takeable
            out.append({"id": e.id, "name": str(e.name or e.id), "cls": e.cls, "held": False, "cmd": f"#{e.name or e.id}"})
    return out


def _places(root: Path, reg: Any) -> list[dict[str, Any]]:
    from neonrp.core.holdings import PLACE_CLASSES

    here = reg.player_location
    cur = reg.entries.get(here or "")
    if cur is None:
        return []
    known: set[str] | None = None
    try:  # what the player's map shows (core/worldmap: an undiscovered node has no name there)
        from neonrp.core import worldmap

        tree = worldmap.build_map_tree(root)
        known = {a for a, n in tree["nodes"].items() if worldmap._known(n)}
    except Exception:  # noqa: BLE001
        known = None
    near = {x.id for x in reg.exits(cur.id)}
    out = []
    for e in reg.entries.values():
        if e.cls not in PLACE_CLASSES or e.cls in ("world", "level"):
            continue
        if not (e.id == here or e.id in near or (e.parent and e.parent == cur.parent)):
            continue
        if known is not None and e.id not in known and e.id not in near and e.id != here:
            continue
        name = str(e.name or "")
        if not name:
            continue
        out.append({"id": e.id, "name": name, "here": e.id == here, "near": e.id in near, "cmd": f"#{name}"})
    out.sort(key=lambda r: (not r["here"], not r["near"]))
    return out


def catalog(root: Path, lang: str | None = None) -> dict[str, Any]:
    from neonrp.core import sheet as _sheet
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    reg = load_registry(root)
    T = _T(root)
    acts = [{**r, "cmd": f"/{r['name']}"} for r in world_actions(root)]
    sh = _sheet.sheet(root, lang, reg=reg)
    skills = sorted(({**r, "cmd": f"/{r.get('label') or r.get('name')}"} for r in sh.get("skills") or []),
                    key=lambda r: -(r.get("value") if isinstance(r.get("value"), (int, float)) else -1))
    for k, r in enumerate(skills):
        r["common"] = k < COMMON_SKILLS
    verbs = [{"kind": k, "label": str(T.get(f"verb_{k}") or k), "help": str(T.get(f"verb_{k}_help") or "")} for k in ("skill", "inspect", "pick")]
    out: dict[str, Any] = {"lang": lang, "actions": acts, "verbs": verbs, "skills": skills, "attrs": sh.get("attrs") or []}
    for key, fn in (("items", lambda: _items(reg)), ("places", lambda: _places(root, reg)), ("people", lambda: _people(root, reg))):
        try:
            out[key] = fn()
        except Exception:  # noqa: BLE001 — one list failing leaves the others
            logger.warning("play menu: %s skipped", key, exc_info=True)
            out[key] = []
    out["quick"] = ([{"kind": "person", "text": p["cmd"], "label": p["name"]} for p in out["people"]]
                    + [{"kind": "skill", "text": s["cmd"], "label": " ".join(str(x) for x in (s.get("label"), s.get("value")) if x not in (None, ""))}
                       for s in skills if s["common"]]
                    + [{"kind": "item", "text": i["cmd"], "label": i["name"]} for i in out["items"] if i["held"]])
    return out
