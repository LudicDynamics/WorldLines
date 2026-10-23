"""pct's ``load`` seam: the rpg layout (map, places, people, items, Character State) plus the percentile sheet —
attributes (STR … EDU), skill percentages, sanity (``player.san``), damage bonus — in the one-line sheet the narrator
and the host read. hp falls back to (CON + SIZ) / 2 when the sheet has none."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import Registry, VarSpec


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load(reg: Registry, root: Path) -> None:
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang
    from neonrp.packs.pct import rules as _r
    from neonrp.packs.rpg.loaders import load as rpg_load

    rpg_load(reg, root)
    R = _r.rules(root)
    lang = prompt_lang(root)
    S = prompts.strings("pct", lang)
    g = get_data_dir_name(root)
    stats = _read(Path(root) / g / "player" / "stats.json")
    p = reg.entries.get("player")
    if p is None:
        return
    sk = stats.get("skills")
    if isinstance(sk, dict):
        p.props["skills"] = [{"name": k, "value": v} for k, v in sk.items()]
    if p.props.get("hp") is None and p.props.get("attributes"):
        p.props["hp"] = p.props["max_hp"] = _r.hp_of(p)
    sanity = stats.get("san") if isinstance(stats.get("san"), dict) else ({"current": stats["san"]} if stats.get("san") is not None else None)
    if sanity is not None:
        from neonrp.core.output_lang import pick_lang
        from neonrp.packs.pct.tools import san_names

        p.props["san"] = sanity.get("current")
        gone = pick_lang((R.get("effect_names") or {}).get("insane_perm") or {}, lang, "")  # the world's words, in the run's language
        reg.variables["player.san"] = VarSpec("player.san", "int", f"{g}/player/stats.json", "san.current", sanity.get("current"),
                                               min=0, max=int(R.get("san_max", 99)),
                                               doc=f"{san_names(R, lang, S)['sshort']}: 0 = {gone}" if gone else san_names(R, lang, S)["sshort"])
    attrs = _r._attrs(p)
    own = {n: v for n, v in _r._skills(p).items()}
    dodge = _r.skill_value(R, p, str((R.get("skills") or {}).get("dodge", {}).get(lang) or "Dodge"))
    parts = []
    if attrs:
        parts.append(S["sheet_attrs"] + " " + " ".join(f"{_r.attr_label(R, k, lang)}{v}" for k, v in attrs.items()))
    if own:
        parts.append(S["sheet_skills"] + " " + " · ".join(f"{_r.skill_label(R, n, lang)} {v}%" for n, v in own.items()))
    if dodge is not None and not any(n == S["sheet_dodge"] for n in own):  # the table's dodge (DEX × 2) when the sheet has none
        parts.append(f"{S['sheet_dodge']} {dodge}%")
    if p.props.get("san") is not None:
        from neonrp.packs.pct.tools import san_names

        p.props["san_label"] = san_names(R, lang, S)["sshort"]
        parts.append(f"{p.props['san_label']} {p.props['san']}")
    if attrs:
        parts.append(f"{S['sheet_db']} {_r.damage_bonus(R, p)}")
    w = p.props.get("weapon") or {}
    if w:
        parts.append(f"{w.get('name')}({w.get('skill') or ''} {w.get('damage') or w.get('base_damage') or ''})".replace("( ", "("))
    bag = p.props.get("inventory") or []
    if bag:
        parts.append("· ".join(f"{x.get('name')}×{x.get('qty', 1)}" for x in bag if isinstance(x, dict)))
    p.props["sheet"] = ";".join(x for x in parts if x)
