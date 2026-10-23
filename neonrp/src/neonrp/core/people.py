"""The people the player knows, as the player knows them (10-15, the standard front end §5.14 / §5.17).

    GET /api/v1/play/engine/people
    → {lang, people: [{id, sid?, kind: soul|npc, name, role_label, met, here, companion, addr, place, where,
                       portrait_slot, portrait_fallback (core/fallback_art), last_seen?: {addr, turn}, mood_label?, trust?: {value, min, max, label},
                       relation?: {label}}]}

Who is listed: everyone standing where the player stands, and every character the player has met. A soul is met once
she has shared a place with the player (``mark_met`` writes ``status.met_player`` into her ``run_state.json`` after
every apply, with ``last_seen``); an NPC is met when the world says so (``state.met`` in ``npcs.json``). Someone here
but not met yet has no name (``name: ""``) — only what they look like they are (``role_label``). Nothing the host
alone may know leaves here: no persona, no rules, no goals, no relationship truths.

``play_props`` is the same line for the play-side ``entities?cls=soul|npc`` read: a short list of fields the screen may
show; everything else stays for the debug read (``/api/v1/play/engine/debug/entities``).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLAY_PROPS = ("name", "name_en", "sid", "role", "title", "hp", "max_hp", "mood", "trust", "active", "down", "dead", "stable")


def _T(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("people", lang)


def _soul_dirs(root: Path) -> dict[str, Path]:
    """instance id → souls/<dir> (read off each folder's run_state.json, else the folder name)."""
    out: dict[str, Path] = {}
    sdir = Path(root) / "souls"
    for d in sorted(sdir.iterdir()) if sdir.is_dir() else []:
        if not d.is_dir():
            continue
        iid = ""
        try:
            iid = str(json.loads((d / "run_state.json").read_text(encoding="utf-8")).get("instance_id") or "")
        except (OSError, ValueError):
            pass
        out[iid or (d.name.split("-", 1)[1] if "-" in d.name else d.name)] = d
    return out


def _state(d: Path | None) -> dict[str, Any]:
    if d is None:
        return {}
    try:
        rs = json.loads((d / "run_state.json").read_text(encoding="utf-8"))
        return rs if isinstance(rs, dict) else {}
    except (OSError, ValueError):
        return {}


def mark_met(root: Path, reg: Any, *, turn: int | None = None, before: dict[str, Any] | None = None) -> list[str]:
    """After an apply: every soul standing where the player stands — now, or before this apply (``before`` = the
    holdings snapshot: the beat they shared ends with the player walking off) — is met (``status.met_player``) and last
    seen there. Returns the souls met for the first time."""
    here = reg.player_location
    p0, stood0 = (before or {}).get("player"), (before or {}).get("people") or {}
    dirs = _soul_dirs(root)
    first: list[str] = []
    for e in reg.of_class("soul"):
        if e.id not in dirs:
            continue
        if here and e.parent == here:
            at = here
        elif p0 and stood0.get(e.id) == p0:
            at = p0
        else:
            continue
        p = dirs[e.id] / "run_state.json"
        rs = _state(dirs[e.id])
        st = rs.get("status") if isinstance(rs.get("status"), dict) else {}
        seen = {"addr": at, **({"turn": int(turn)} if turn is not None else {})}
        if st.get("met_player") and st.get("last_seen") == seen:
            continue
        if not st.get("met_player"):
            first.append(e.id)
        rs["status"] = {**st, "met_player": True, "last_seen": seen}
        try:
            p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("met_player not written for %s", e.id, exc_info=True)
    return first


def _seen_path(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta" / "seen.json"


def seen(root: Path) -> set[str]:
    """Entries the player has come across (things, places): ``<data>/meta/seen.json`` ``{"entries": [...]}``."""
    try:
        d = json.loads(_seen_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(x) for x in (d.get("entries") or [])} if isinstance(d, dict) else set()


def visible_now(reg: Any) -> set[str]:
    """What the player has in view right now: where they stand, what lies there, what they and the people there carry."""
    here = reg.player_location
    out: set[str] = {here} if here else set()
    for e in reg.entries.values():
        if e.id == "player":
            continue
        if reg.owner_of(e) == "player" or (here and e.parent == here):
            out.add(e.id)
    return out


def mark_seen(root: Path, reg: Any, *, before: dict[str, Any] | None = None, narration: str = "") -> list[str]:
    """After an apply: what was in view (before or after it) and what the prose named is seen — kept so a thing's name stays
    on the player's lists once found. Returns the entries seen for the first time."""
    from neonrp.core import mentions

    got = visible_now(reg)
    p0 = (before or {}).get("player")
    if p0:
        got.add(p0)
        got |= {i for i, t in ((before or {}).get("things") or {}).items() if t.get("owner") == "player" or t.get("parent") == p0}
    if narration:
        try:
            got |= {str(m["id"]) for m in mentions.find(reg, narration)}
        except Exception:  # noqa: BLE001
            pass
    have = seen(root)
    new = sorted(x for x in got if x not in have and x in reg.entries)
    if new:
        _write_seen(root, entries=sorted(have | set(new)))
    return new


def _write_seen(root: Path, **kw: Any) -> None:
    p = _seen_path(root)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        d = {}
    d = {**(d if isinstance(d, dict) else {}), **kw}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def discovered(root: Path, reg: Any, *, newly_seen: list[str], created: list[dict[str, Any]], turn: int | None = None,
               moved: bool = False) -> list[dict[str, Any]]:
    """Places the player learned of in this apply — ``place.discovered {turn, addr, name, parent, by}``: ``grow`` (the
    engine made it), ``arrive`` (walked into it), ``reveal`` (it came onto their map / the prose named it). The first
    look at a run (no ``mapped`` record yet) only notes what is known — no flood of events — except where they walked."""
    from neonrp.core.holdings import PLACE_CLASSES

    try:
        from neonrp.core import worldmap

        tree = worldmap.build_map_tree(root)
        mapped = {a for a, n in tree["nodes"].items() if worldmap._known(n) and a in reg.entries and reg.entries[a].cls in PLACE_CLASSES
                  and reg.entries[a].cls not in ("world", "level")}
    except Exception:  # noqa: BLE001
        mapped = set()
    try:
        prev_raw = json.loads(_seen_path(root).read_text(encoding="utf-8")).get("mapped")
    except (OSError, ValueError, AttributeError):
        prev_raw = None
    first = prev_raw is None
    prev = set(prev_raw or [])
    grown = {str(c.get("id")) for c in created or [] if isinstance(c, dict)}
    here = reg.player_location
    cand = (mapped - prev) | {x for x in newly_seen if x in reg.entries and reg.entries[x].cls in PLACE_CLASSES
                              and reg.entries[x].cls not in ("world", "level")}
    if first:
        cand = {here} if moved and here in cand else set()
    cand |= {a for a in grown if a in reg.entries and reg.entries[a].cls in PLACE_CLASSES}  # the engine made it: always told
    out = []
    for a in sorted(cand):
        e = reg.entries.get(a)
        if e is None:
            continue
        by = "grow" if a in grown else "arrive" if a == here else "reveal"
        out.append({**({"turn": int(turn)} if turn is not None else {}), "addr": a, "name": str(e.name or ""), "parent": e.parent, "by": by})
    if first or mapped - prev:
        _write_seen(root, mapped=sorted(prev | mapped))
    return out


def play_props(props: dict[str, Any], *, root: Path | None = None, lang: str = "zh") -> dict[str, Any]:
    """A person's props as the play side may show them (the debug read keeps all of them)."""
    out = {k: props[k] for k in PLAY_PROPS if k in props}
    if root is not None:
        from neonrp.core import labels

        if props.get("mood"):
            out["mood_label"] = labels.label(root, "mood", props.get("mood"), lang)
        if props.get("role"):
            out["role_label"] = labels.label(root, "role", props.get("role"), lang)
    return out


def _npc_record(root: Path, e: Any) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    town = str(e.props.get("town") or "")
    try:
        d = json.loads((Path(root) / get_data_dir_name(root) / "towns" / town / "npcs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = d.get("npcs") if isinstance(d, dict) else d
    nid = e.id.rsplit("/", 1)[-1]
    return next((r for r in rows or [] if isinstance(r, dict) and str(r.get("id")) == nid), {})


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or "")
    return str(v or "")


def people(root: Path, lang: str | None = None) -> dict[str, Any]:
    from neonrp.core import fallback_art, holdings, labels
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    reg = load_registry(root)
    T = _T(lang)
    tbl = labels.table(root)
    here = reg.player_location
    dirs = _soul_dirs(root)
    party = holdings.members(root)
    roles = holdings._souls(root)
    out: list[dict[str, Any]] = []

    def where(addr: str | None, is_here: bool) -> tuple[str, str]:
        place = str(reg.entries[addr].name or "") if addr and addr in reg.entries else ""
        if is_here:
            return place, str(T["here"])
        return place, (str(T["at"]).format(place=place) if place else str(T["unknown"]))

    for e in reg.of_class("soul"):
        rs = _state(dirs.get(e.id))
        st = rs.get("status") if isinstance(rs.get("status"), dict) else {}
        is_here = bool(here) and e.parent == here
        met = bool(st.get("met_player")) or is_here
        if not met:
            continue
        sid = str(e.props.get("sid") or (roles.get(e.id) or {}).get("sid") or "")
        companion = (e.id in party) if party is not None else (roles.get(e.id) or {}).get("role") == "companion"
        place, line = where(e.parent, is_here)
        role = str(e.props.get("role") or "")
        role_label = str(T["companion"]) if companion else ("" if role in ("", "npc", "companion") else labels.label(root, "role", role, lang, tbl))
        row: dict[str, Any] = {"id": e.id, **({"sid": sid} if sid else {}), "kind": "soul", "name": str(e.name or ""), "role_label": role_label,
                               "met": met, "here": is_here, "companion": companion, "addr": e.parent, "place": place, "where": line,
                               "portrait_slot": f"soul.portrait:{sid or e.id}", "portrait_fallback": fallback_art.soul_dir(dirs.get(e.id), e.props)}
        if isinstance(st.get("last_seen"), dict):
            row["last_seen"] = st["last_seen"]
        mood = st.get("mood") or e.props.get("mood")
        if mood:
            row["mood_label"] = labels.label(root, "mood", mood, lang, tbl)
        tv = reg.variables.get(f"trust.{sid}") if sid else None
        if tv is not None and isinstance(tv.value, (int, float)):
            row["trust"] = {"value": tv.value, "min": tv.min, "max": tv.max, "label": str(T["trust"])}
        elif isinstance(e.props.get("trust"), (int, float)) and not isinstance(e.props.get("trust"), bool):
            row["trust"] = {"value": e.props["trust"], "min": None, "max": None, "label": str(T["trust"])}
        rel = (e.props.get("relationships") or {}).get("player") if isinstance(e.props.get("relationships"), dict) else None
        if isinstance(rel, dict) and rel.get("disposition"):
            row["relation"] = {"label": labels.label(root, "disposition", rel["disposition"], lang, tbl)}
        out.append(row)
    for e in reg.of_class("npc"):
        st = e.props.get("state") if isinstance(e.props.get("state"), dict) else {}
        is_here = bool(here) and e.parent == here
        met = bool(st.get("met"))
        if not (met or is_here):
            continue
        rec = _npc_record(root, e)
        role = _pick(rec.get("title"), lang) or labels.label(root, "role", e.props.get("role"), lang, tbl)
        place, line = where(e.parent, is_here)
        out.append({"id": e.id, "kind": "npc", "name": str(e.name or "") if met else "", "role_label": role, "met": met,
                    "here": is_here, "companion": False, "addr": e.parent, "place": place, "where": line,
                    "portrait_slot": f"npc.portrait:{e.id.rsplit('/', 1)[-1]}", "portrait_fallback": fallback_art.portrait(rec, e.props),
                    **({"mood_label": labels.label(root, "mood", st.get("mood"), lang, tbl)} if st.get("mood") else {})})
    out.sort(key=lambda r: (not r["here"], not r["companion"], r["kind"] != "soul"))
    return {"lang": lang, "people": out}
