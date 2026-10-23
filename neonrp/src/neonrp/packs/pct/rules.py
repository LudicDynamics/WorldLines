"""Percentile investigation rules (pct — the BRP pack: Basic Roleplaying, Chaosium, ORC License; see NOTICE.md).

The pack's own numbers live in ``packs/pct/data/rules.json`` (a world overrides key by key in ``game/rules/rules.json``):

- attributes STR CON SIZ INT POW DEX CHA (+ EDU) (3–18); an attribute check is d100 ≤ attribute × ``attr_x`` (5);
  a sheet's old ``app`` reads as ``cha``;
- skills are percentages; a skill check is d100 ≤ skill; a character's own value wins over the table's ``base``
  (a number, or an expression on attributes like ``dex*2``);
- levels (BRP): ≤ 1/20 of the target a critical, ≤ 1/5 a special, ≤ the target a success (fractions round up, at
  least 1); 99 / 00 a fumble (``crit_div`` / ``special_div`` / ``fumble_min``); a difficulty multiplies the target
  (easy ×2 · normal · hard ×½);
- a contest: both roll; the better level wins, the same successful level goes to the larger margin (target − roll);
- hp = (CON + SIZ) / 2 rounded up; sanity starts at POW × 5 (max 99); the damage bonus is looked up by STR + SIZ.

Every roll goes through the dice tool (``tools.dice``: one random-number backend, the ledger, the dice line).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

LEVELS = ("fumble", "fail", "success", "special", "crit")


def rules(root: Path | None) -> dict[str, Any]:
    from neonrp.packs.rpg import data

    return data.rules(root)


def level(roll: int, target: int, R: dict[str, Any]) -> str:
    fum = int(R.get("fumble_min", 99))
    if roll >= fum and (roll >= 100 or target < fum):  # a skill of 99+ only fumbles on 00
        return "fumble"
    if roll <= max(1, -(-target // int(R.get("crit_div", 20)))):
        return "crit"
    if roll <= max(1, -(-target // int(R.get("special_div", 5)))):
        return "special"
    return "success" if roll <= target else "fail"


def bands(target: int, R: dict[str, Any]) -> dict[str, int]:
    """Why a roll lands on its tier, for a renderer: a critical at or under ``crit_max`` (BRP: 1/20 of the target, at
    least 1), a fumble at or over ``fumble_min``."""
    return {"crit_max": max(1, -(-int(target) // int(R.get("crit_div", 20)))), "fumble_min": int(R.get("fumble_min", 99))}


def passed(lv: str) -> bool:
    return lv in ("success", "special", "crit")


def better(a: tuple[str, int], b: tuple[str, int]) -> bool:
    """(level, margin) a beats b."""
    ra, rb = LEVELS.index(a[0]), LEVELS.index(b[0])
    if ra != rb:
        return ra > rb
    return passed(a[0]) and a[1] > b[1]


def _attrs(e: Any) -> dict[str, int]:
    raw = (e.props.get("attributes") if e is not None else None) or {}
    out = {}
    for k, v in raw.items():
        try:
            out[str(k).lower()] = int(v)
        except (TypeError, ValueError):
            continue
    if "app" in out and "cha" not in out:  # sheets written before the BRP names (10-14): APP is read as CHA
        out["cha"] = out["app"]
    return out


def _skills(e: Any) -> dict[str, int]:
    """A character's own skills: a list of {name, value} or a {name: value} map."""
    raw = (e.props.get("skills") if e is not None else None) or []
    out: dict[str, int] = {}
    items = raw.items() if isinstance(raw, dict) else ((x.get("name"), x.get("value")) for x in raw if isinstance(x, dict))
    for k, v in items:
        try:
            if k and v is not None:
                out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _base(expr: Any, attrs: dict[str, int]) -> int:
    if isinstance(expr, (int, float)):
        return int(expr)
    m = re.match(r"^\s*([a-z]{3})\s*\*\s*(\d+)\s*$", str(expr or ""))
    if m:
        return attrs.get(m.group(1), 10) * int(m.group(2))
    return 0


def attr_label(R: dict[str, Any], key: str, lang: str) -> str:
    row = (R.get("attrs") or {}).get(key) or {}
    return str(row.get(lang) or row.get("en") or key.upper())


def skill_value(R: dict[str, Any], e: Any, name: str) -> int | None:
    """A skill by any of its names (own sheet first, then the table's base)."""
    own = _skills(e)
    if name in own:
        return own[name]
    for key, row in (R.get("skills") or {}).items():
        names = {key, *(str(v) for k, v in row.items() if k in ("zh", "en", "ja", "ko")), *(str(a) for a in row.get("aliases") or [])}
        if name in names:
            for n in names:
                if n in own:
                    return own[n]
            return _base(row.get("base"), _attrs(e))
    return None


def skill_label(R: dict[str, Any], name: str, lang: str) -> str:
    """How a skill is shown in ``lang``: a sheet's skill names are its keys (as authored); one the table knows (by its
    key or any language's name, else by an old name in ``aliases`` — 「侦查」 shows as today's BRP 「察觉」) shows the
    table's name in the run's language."""
    rows = list((R.get("skills") or {}).items())
    for key, row in rows:
        if name == key or name in {str(v) for k, v in row.items() if k in ("zh", "en", "ja", "ko")}:
            return str(row.get(lang) or row.get("en") or name)
    n = str(name or "").casefold()
    for key, row in rows:
        if n in {str(a).casefold() for a in row.get("aliases") or []}:
            return str(row.get(lang) or row.get("en") or name)
    return name


def find_target(R: dict[str, Any], e: Any, text: str, attr: str = "", lang: str = "zh") -> tuple[str, int] | None:
    """(label, target %) for what a check names: a skill of hers or of the table (longest name in the text first), else
    an attribute (by name, key or the parsed ``attr``) × attr_x. None when nothing is named."""
    t = str(text or "")
    cands: list[tuple[str, str, int]] = [(n, skill_label(R, n, lang), v) for n, v in _skills(e).items()]  # (name to find, label in the run's language, value)
    for key, row in (R.get("skills") or {}).items():
        label = str(row.get(lang) or row.get("zh") or row.get("en") or key)
        for n in [*(str(row.get(k) or "") for k in ("zh", "en", "ja", "ko")), *(str(a) for a in row.get("aliases") or [])]:
            if n:
                v = skill_value(R, e, n)
                if v is not None:
                    cands.append((n, label, v))  # an old name (an alias) finds the skill; it shows by today's name
    for n, label, v in sorted(cands, key=lambda x: -len(x[0])):
        if n and n.lower() in t.lower():
            return label, max(1, min(99, v))
    attrs = _attrs(e)
    x = int(R.get("attr_x", 5))
    for key, row in (R.get("attrs") or {}).items():
        names = [str(row.get(k) or "") for k in ("zh", "en", "ja", "ko")] + [str(a) for a in row.get("aliases") or []] + [key.upper()]
        hit = any(n and re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", t, re.IGNORECASE) for n in names)
        if hit or (attr and attr.lower() in {key, *(a.lower() for a in row.get("aliases") or [])}):
            return attr_label(R, key, lang), max(1, min(99, attrs.get(key, 10) * x))
    return None


def damage_bonus(R: dict[str, Any], e: Any) -> str:
    a = _attrs(e)
    total = a.get("str", 10) + a.get("siz", 10)
    for row in R.get("damage_bonus") or []:
        if total <= int(row.get("max", 99)):
            return str(row.get("db") or "0")
    return "0"


def hp_of(e: Any) -> int:
    a = _attrs(e)
    return max(1, -(-(a.get("con", 10) + a.get("siz", 10)) // 2))  # BRP: rounded up


def roll_d100(root: Path, reg: Any, who: str, target: int, why: str, *, seed: str, key: str, source: str = "plan",
              label: str = "") -> dict[str, Any]:
    """One d100 through the dice tool (ledger / dice line); {roll, target, level, passed}. ``label`` names the skill /
    attribute checked (the world's `check` triggers hear it)."""
    from neonrp.core import tool_watch

    out = tool_watch.call(root, reg, "dice", "neonrp.packs.pct.tools:dice",
                          {"dice": "1d100", "vs": target, "reason": why, "source": source, "who": who, "seed_key": key,
                           **({"label": label} if label else {})},
                          None, seed=seed, source=source)
    return out


def roll_check(root: Path, reg: Any, check: dict[str, Any], *, seed: str = "") -> dict[str, Any] | None:
    """The ``roll_check`` seam for pct: a check agreed while talking (「检定: 玩家 侦查 为了找暗门」) is a d100 under the
    skill / attribute it names, read off the rule panel (packs/rpg/panel.py, 10-14): her own value, else one completed
    for this run (role panel → the table's base → baseline) and kept; a name the table does not know rolls on
    ``fallback_attr``. The reason is not searched for a skill name. A named difficulty (``hard`` / ``extreme``) scales
    the target; the effects' rule lines move it (the host names which apply, the numbers are theirs). A contest
    (``vs``) rolls the other side on the skill the table opposes it with (说服 ↔ 心理学), else the same one."""
    from neonrp.core.output_lang import prompt_lang
    from neonrp.packs.rpg import panel

    R = rules(root)
    lang = prompt_lang(root)
    head = panel.head(check)
    named = str(check.get("attr") or "").lower()
    tier = str(check.get("dc") or "").strip().lower()
    factor = float((R.get("difficulty") or {}).get(tier, 1)) if not tier.isdigit() else 1.0

    def value(who: str, text: str) -> dict[str, Any]:
        akey = next((k for k, row in (R.get("attrs") or {}).items()
                     if named and named in {k, *(str(a).lower() for a in row.get("aliases") or [])}), None)
        if akey:
            v, src = panel.attr(root, reg, who, akey)
            return {"label": attr_label(R, akey, lang), "value": v * int(R.get("attr_x", 5)), "source": src}
        return panel.skill(root, reg, who, text)

    def side(who: str, tag: str, text: str) -> dict[str, Any]:
        sk = value(who, text)
        smod, used = panel.status_mod(root, reg, who, check if tag == "a" else None)
        target = max(1, min(99, int(sk["value"] * factor) + smod))
        r = roll_d100(root, reg, who, target, str(check.get("why") or ""), seed=seed, key=f"check:{tag}:{who}:{str(check.get('why', ''))[:30]}",
                      label=sk["label"])
        roll = int(r.get("total") or 0)
        return {"who": who, "roll": roll, "mod": 0, "total": roll, "target": target, "label": sk["label"], "value": sk["value"],
                "source": sk["source"], **({"via": sk["via"]} if sk.get("via") else {}), "effects": used,
                "level": r.get("level") or level(roll, target, R)}

    a = side(str(check.get("who") or "player"), "a", head)
    out: dict[str, Any] = {**check, "system": "pct", "a": a, "attr": a["label"], **({"tier": tier} if factor != 1 else {})}
    if check.get("adj") not in (None, ""):
        out["host_adj"] = check["adj"]
    if check.get("vs"):
        row = (R.get("skills") or {}).get(str(panel.skill(root, reg, str(check.get("who") or "player"), head, fill=False).get("key") or ""), {})
        opp = (R.get("skills") or {}).get(str(row.get("opposed") or ""))
        b = side(str(check["vs"]), "b", str((opp or {}).get(lang) or (opp or {}).get("zh") or "") if opp else head)
        out["b"] = b
        win = better((a["level"], a["target"] - a["roll"]), (b["level"], b["target"] - b["roll"]))
        out["result"] = "success" if win else "fail"
        out["dc"] = b["target"]
    else:
        out["dc"] = a["target"]
        out["result"] = "success" if passed(a["level"]) else "fail"
    return out


def sheet(root: Path, reg: Any, sh: dict[str, Any], lang: str) -> dict[str, Any]:
    """The ``sheet`` seam: rpg's names and lines, plus ``check`` — the percentage a roll must come under (a skill is
    its value, an attribute its value × ``attr_x``)."""
    from neonrp.packs.rpg import sheet as _sheet

    R = rules(root)
    out = _sheet.sheet(root, reg, sh, lang)
    x = int(R.get("attr_x", 5))

    def pct(v: Any, k: int) -> int | None:
        try:
            return max(1, min(99, int(v) * k))
        except (TypeError, ValueError):
            return None

    out["attrs"] = [{**r, "check": pct(r.get("value"), x)} for r in out.get("attrs") or []]
    out["skills"] = [{**r, "check": pct(r.get("value"), 1)} for r in out.get("skills") or []]
    return {**out, "system": "pct"}


def skill_check(root: Path, reg: Any, check: dict[str, Any], *, seed: str = "") -> dict[str, Any] | None:
    """The ``skill_check`` seam: a skill / attribute the player named by command (「/侦查 井口」) is a d100 under its
    value right away — the sheet alone decides the target, so the engine rolls before the host writes. None when the
    name is neither a skill nor an attribute here."""
    from neonrp.core.output_lang import prompt_lang

    R = rules(root)
    who = str(check.get("who") or "player")
    hit = find_target(R, reg.entries.get(who), str(check.get("skill") or ""), lang=prompt_lang(root))
    if hit is None:
        return None
    label, target = hit
    why = " · ".join(x for x in (label, str(check.get("target") or "").strip()) if x)
    r = roll_d100(root, reg, who, target, why, seed=seed, key=f"skill:{label}:{str(check.get('target') or '')[:30]}", source="player",
                  label=label)
    return {**r, "label": label} if isinstance(r, dict) and r.get("ok") else None


def down_roll(root: Path, reg: Any, eid: str, name: str, turn: int) -> tuple[int, int, bool]:
    """The dying check (packs/rpg/downed.py, down_rule=pct): d100 ≤ CON × attr_x."""
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    R = rules(root)
    e = reg.entries.get(eid)
    con = _attrs(e).get("con") or _sheet_attr(root, e, "con") or 10
    target = max(1, min(99, int(con) * int(R.get("attr_x", 5))))
    why = prompts.strings("pct", prompt_lang(root)).get("con_check", "{name}").replace("{name}", name)
    r = roll_d100(root, reg, eid, target, why, seed=f"down:{turn}", key=f"down:{turn}:{eid}", source="rule")
    roll = int(r.get("total") or 0)
    return roll, roll, passed(r.get("level") or level(roll, target, R))


def _sheet_attr(root: Path, e: Any, key: str) -> int | None:
    """A soul's attribute from her own sheet (souls/<id>/character/stats.json) when the registry entry has none."""
    import json

    sheet = str((e.props.get("sheet") if e is not None else "") or "")
    if not sheet:
        return None
    try:
        a = json.loads((Path(root) / sheet).read_text(encoding="utf-8")).get("attributes") or {}
        return int(a.get(key) or a.get(key.upper()))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
