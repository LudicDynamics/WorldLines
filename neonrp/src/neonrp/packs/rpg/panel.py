"""The rule panel — the numbers a check reads, one reader for the player, a soul and an NPC
(「soul 的面板会更复杂,不过作为规则面板,其实是和 npc 一样的」).

A value is never refused for being missing. It is looked up down a chain, and wherever it was found below the
character's own sheet it is written into the run's character state (``game/states/<id>.json`` → ``panel``), so the
same character reads the same number next time and the player can see where it came from:

    sheet      the character's own record (player/stats.json · a soul's character/stats.json · its row in npcs.json)
    run        a value filled earlier in this run (the state file) — reports the layer it was first filled from
    role:<r>   the world's panel for the character's role (rules ``role_panels``, written by the template's author)
    baseline   the rulebook's plain person (rules ``baseline``)

The pack's rules table is the rulebook (packs/<pack>/data/rules.json < the world's game/rules/rules.json). Nothing here
knows a particular attribute, skill or role: they are the table's.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neonrp.packs.rpg import character_state as cs
from neonrp.packs.rpg import data


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _attr_map(raw: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in (raw.items() if isinstance(raw, dict) else []):
        n = _int(v)
        if n is not None:
            out[str(k).lower()] = n
    return out


def _skill_map(raw: Any) -> dict[str, int | None]:
    """A list of {name, value} (or bare names), or a {name: value} map → {name: value or None}."""
    out: dict[str, int | None] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = _int(v)
    elif isinstance(raw, list):
        for x in raw:
            if isinstance(x, dict) and x.get("name"):
                out[str(x["name"])] = _int(x.get("value"))
            elif isinstance(x, str) and x.strip():
                out[x.strip()] = None
    return out


def sheet(root: Path, reg: Any, eid: str) -> dict[str, Any]:
    """The character's own rule panel as written by its author: {attributes, skills, role}."""
    e = reg.entries.get(eid)
    if e is None:
        return {"attributes": {}, "skills": {}, "role": ""}
    out = _own(root, e)
    for key, row in (data.rules(root).get("attrs") or {}).items():  # a sheet that wrote an alias (an older name) for it
        if isinstance(row, dict) and key not in out["attributes"]:
            hit = next((out["attributes"][str(a).lower()] for a in row.get("aliases") or [] if str(a).lower() in out["attributes"]), None)
            if hit is not None:
                out["attributes"][key] = hit
    return out


def _own(root: Path, e: Any) -> dict[str, Any]:
    attrs, skills = _attr_map(e.props.get("attributes")), _skill_map(e.props.get("skills"))
    sp = str(e.props.get("sheet") or "")
    if sp and sp.endswith(".json"):  # a soul: her sheet is a file of her own (the registry entry carries only its path)
        try:
            d = json.loads((Path(root) / sp).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        if isinstance(d, dict):
            attrs = {**_attr_map(d.get("attributes")), **attrs}
            skills = {**_skill_map(d.get("skills")), **skills}
    return {"attributes": attrs, "skills": skills, "role": str(e.props.get("role") or e.props.get("class") or "")}


def _filled(root: Path, eid: str) -> dict[str, Any]:
    p = cs.read(root, eid).get("panel")
    return p if isinstance(p, dict) else {}


def _fill(root: Path, eid: str, kind: str, key: str, value: int, source: str) -> None:
    p = _filled(root, eid)
    p.setdefault(kind, {})[key] = value
    p.setdefault("source", {})[f"{kind}.{key}"] = source
    cs.write(root, eid, panel=p)


def _role_panel(R: dict[str, Any], role: str) -> tuple[str, dict[str, Any]] | None:
    """The world's panel for this role: an exact key, else the longest key the role contains (「北门守门人」 → 守门人)."""
    panels = R.get("role_panels") if isinstance(R.get("role_panels"), dict) else {}
    if not role or not panels:
        return None
    if isinstance(panels.get(role), dict):
        return role, panels[role]
    for k in sorted(panels, key=len, reverse=True):
        if k and k in role and isinstance(panels[k], dict):
            return k, panels[k]
    return None


def attr(root: Path, reg: Any, eid: str, key: str, *, fill: bool = True) -> tuple[int, str]:
    """(value, source) of attribute ``key`` — always a number."""
    key = str(key or "").lower()
    R = data.rules(root)
    own = sheet(root, reg, eid)
    if key in own["attributes"]:
        return own["attributes"][key], "sheet"
    run = _filled(root, eid)
    if key in (run.get("attributes") or {}):
        return int(run["attributes"][key]), str((run.get("source") or {}).get(f"attributes.{key}") or "run")
    hit = _role_panel(R, own["role"])
    v = _int(((hit[1].get("attributes") or {}) if hit else {}).get(key))
    if v is not None:
        src = f"role:{hit[0]}"
    else:
        v = _int(((R.get("baseline") or {}).get("attributes") or {}).get(key))
        src = "baseline"
    if v is None:  # an attribute the rulebook never names: the plain person's middle value, still recorded
        vals = [x for x in ((R.get("baseline") or {}).get("attributes") or {}).values() if _int(x) is not None]
        v, src = (sorted(int(x) for x in vals)[len(vals) // 2] if vals else 0), "baseline"
    if fill:
        _fill(root, eid, "attributes", key, v, src)
    return v, src


def _names(row: dict[str, Any], key: str) -> list[str]:
    return [n for n in [key, *(str(row.get(k) or "") for k in ("zh", "en", "ja", "ko")), *(str(a) for a in row.get("aliases") or [])] if n]


def find(table: dict[str, Any], text: str) -> tuple[str, str] | None:
    """(row key, the name that matched) of the table row a check's text names — the longest name wins, matched in the
    check's own words (the caller leaves the reason out: 「为了侦查书房」 must not pick 侦查 for a 说服 check)."""
    t = str(text or "").lower()
    best: tuple[int, str, str] | None = None
    for key, row in (table or {}).items():
        if not isinstance(row, dict):
            continue
        for n in _names(row, key):
            nl = n.lower()
            ascii_word = re.fullmatch(r"[a-z_ ]+", nl) is not None
            ok = re.search(rf"(?<![a-z]){re.escape(nl)}(?![a-z])", t) if ascii_word else nl in t
            if ok and (best is None or len(n) > best[0]):
                best = (len(n), key, n)
    return (best[1], best[2]) if best else None


def skill(root: Path, reg: Any, eid: str, text: str, *, fill: bool = True) -> dict[str, Any]:
    """A percentile skill named in ``text``: {label, value, source, key?, via?}. The character's own skill by any of the
    row's names; else a run fill / its role panel; else the row's base (a number, or ``<attr>*n`` from the attribute's
    own chain); a name no row knows → the rulebook's ``fallback_attr`` × ``attr_x`` (via says so)."""
    R = data.rules(root)
    table = R.get("skills") if isinstance(R.get("skills"), dict) else {}
    own = sheet(root, reg, eid)
    hit = find(table, text)
    own_hit = None
    for n in sorted(own["skills"], key=len, reverse=True):  # a skill only she has (not in the table)
        if n and n.lower() in str(text or "").lower() and own["skills"][n] is not None:
            own_hit = n
            break
    if hit is None and own_hit:
        return {"label": own_hit, "value": own["skills"][own_hit], "source": "sheet"}
    if hit is None:
        a = str(R.get("fallback_attr") or "int")
        v, src = attr(root, reg, eid, a, fill=fill)
        return {"label": _attr_label(R, a, root), "value": v * int(R.get("attr_x", 5)), "source": src, "via": f"fallback_attr:{a}",
                "unknown": str(text or "")[:40]}
    key, said = hit
    row = table[key]
    names = _names(row, key)
    label = _label(row, root) or said
    for n in names:
        if own["skills"].get(n) is not None:
            return {"key": key, "label": label, "value": int(own["skills"][n]), "source": "sheet"}
    run = _filled(root, eid)
    if key in (run.get("skills") or {}):
        return {"key": key, "label": label, "value": int(run["skills"][key]), "source": str((run.get("source") or {}).get(f"skills.{key}") or "run")}
    rp = _role_panel(R, own["role"])
    rv = None
    if rp:
        rs = _skill_map(rp[1].get("skills"))
        rv = next((rs[n] for n in names if rs.get(n) is not None), None)
    if rv is not None:
        v, src = rv, f"role:{rp[0]}"
    else:
        base = row.get("base")
        m = re.match(r"^\s*([a-z]{3})\s*\*\s*(\d+)\s*$", str(base or ""))
        if m:
            av, asrc = attr(root, reg, eid, m.group(1), fill=fill)
            v, src = av * int(m.group(2)), ("baseline" if asrc == "baseline" else f"base({asrc})")
        else:
            v, src = int(_int(base) or 0), "baseline"
    if fill:
        _fill(root, eid, "skills", key, v, src)
    return {"key": key, "label": label, "value": v, "source": src}


def action_attr(root: Path, text: str) -> tuple[str, str]:
    """The attribute a d20 check rolls on, from what it names: (attr key, how) — an attribute named outright, else the
    rulebook's ``actions`` row, else ``fallback_attr``."""
    R = data.rules(root)
    hit = find(R.get("actions") if isinstance(R.get("actions"), dict) else {}, text)
    if hit:
        return str(R["actions"][hit[0]].get("attr") or R.get("fallback_attr") or "int").lower(), f"action:{hit[0]}"
    return str(R.get("fallback_attr") or "int").lower(), "fallback_attr"


def _lang(root: Path | None) -> str:
    try:
        from neonrp.core.output_lang import prompt_lang

        return prompt_lang(root)
    except Exception:  # noqa: BLE001
        return "zh"


def _label(row: dict[str, Any], root: Path | None) -> str:
    return str(row.get(_lang(root)) or row.get("zh") or row.get("en") or "")


def _attr_label(R: dict[str, Any], key: str, root: Path | None) -> str:
    row = (R.get("attrs") or {}).get(key) or {}
    return str(row.get(_lang(root)) or row.get("en") or key.upper())


def source_text(src: str, lang: str = "zh") -> str:
    """The source as the player reads it next to the number (prompts/rpg_pack.<lang>.json ``panel_src_*``)."""
    from neonrp import prompts

    S = prompts.strings("rpg_pack", lang) or {}
    head = str(src or "").split(":", 1)[0].split("(", 1)[0]
    word = str(S.get(f"panel_src_{head}") or head)
    return f"{word}·{src.split(':', 1)[1]}" if head == "role" and ":" in src else word


def head(check: dict[str, Any]) -> str:
    """A check's own words without its reason — what the roll is named by (「玩家 说服 为了侦查书房」 → 「玩家 说服」)."""
    t, why = str(check.get("text") or ""), str(check.get("why") or "")
    if why and why in t and why.strip() != t.strip():
        t = t.replace(why, " ")
    return t


def status_mod(root: Path, reg: Any, who: str, check: dict[str, Any] | None) -> tuple[int, list[str]]:
    """The check modifier from the effects sitting on ``who`` — the numbers are the rule lines' own (引擎加).
    Which effects count is the host's call when it named them in the check (「-20(重伤)」: the name counts, the
    number it wrote does not); a check that names none takes every effect with a modifier, as before."""
    from neonrp.core import effect_rules, effects

    named = str((check or {}).get("adj_why") or "")
    total, used = 0, []
    for e in effects.instances(reg, who):
        n = _int(e.props.get("check")) or effect_rules.check_of(root, e)  # an explicit ``check`` prop, else the rule line's
        if not n:
            continue
        if named and str(e.name or "") not in named:
            continue
        total += n
        used.append(f"{e.name}{n:+d}")
    return total, used


def nearest_tier(tiers: dict[str, Any], n: int) -> tuple[str, int]:
    """A DC number read as the tier it is closest to (rulebook ``dc_numbers: tier``); halfway between two, the harder —
    reading the host's number never makes the task easier than it asked."""
    vals = [(k, int(v)) for k, v in tiers.items() if _int(v) is not None]
    if not vals:
        return "", n
    k, v = min(vals, key=lambda kv: (abs(kv[1] - n), -kv[1]))
    return k, v
