"""rpg rules-referee — v2's ``task(rules-referee)`` as a one-shot request ``[referee 问题]``: the sub-agent's own
system.md (JSON ruling contract kept), the engine packs what its READ contract allowed, the engine throws the die
the ruling asks for, and the narrator gets ``<referee>…</referee>`` back before it continues (对抗:先裁后写)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neonrp.packs.rpg import data
from neonrp.packs.rpg.i18n import t as _t

_ATTR_RE = re.compile(r"(STR|DEX|INT|VIT|CHA)", re.IGNORECASE)
_DICE_RE = re.compile(r"(\d*)d(\d+)")


def _mod(v: Any, base: int = 5) -> int:
    try:
        return int(v) - base  # v2's 修正值速查: 3→-2 … 10→+5 (base from the rules table)
    except (TypeError, ValueError):
        return 0


def _json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def ruling(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    question = str(op.get("question") or " ".join(op.get("args") or []) or "").strip()
    if not question:
        return {"ok": False, "why": _t(root, "ref_need_q")}
    from neonrp.core import modes, sdk
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.turn_v3 import _adapter, _chat

    lang = prompt_lang(root)
    spec = modes.spec_of(root, "referee") or {}
    system = modes.layer_system(root, reg, "referee", lang)
    pk = sdk.render_pack(sdk.pack(root, registry=reg))
    from neonrp.packs.rpg import travel

    scene = []
    j = travel.journey(root)
    if j and j.get("pending"):
        scene.append(_t(root, "ref_scene_road", to=j["to"], d=j["day"], days=j["days"], text=j["pending"].get("text")))
    from neonrp.packs.rpg import combat as _combat

    for fid, f in _combat.standing(_combat.read(root)).items():
        scene.append(_t(root, "ref_scene_foe", fid=fid, name=f.get("name"), hp=f.get("hp"), max=f.get("max_hp"), df=f.get("def"), atk=f.get("atk")))
    tiers = dict(data.rules(root).get("referee_difficulty") or {})
    user = "\n\n".join(x for x in (pk, modes.reads_block(root, reg, spec), (_t(root, "ref_scene_head") + "\n" + "\n".join(scene)) if scene else "",
                                  _t(root, "ref_q_head") + "\n" + question, _t(root, "ref_json", tiers=" | ".join(f"{k}={v}" for k, v in tiers.items()))) if x)
    adapter = _adapter(root, None, "adv")
    text, ms, usage = _chat(adapter, system, user)
    d = _json(text)
    if not d:
        return {"ok": False, "why": _t(root, "ref_no_json"), "raw": text[:300], "ms": ms}
    chk = d.get("check") if isinstance(d.get("check"), dict) else None
    line = _t(root, "ref_ruling", r=d.get("ruling") or "?")
    if d.get("reason"):
        line += f"({d['reason']})"
    if chk and (chk.get("dc") is not None or chk.get("formula") or chk.get("attribute") or chk.get("difficulty")):
        formula = str(chk.get("formula") or "d20")
        attrs = (reg.entries.get("player").props.get("attributes") if reg.entries.get("player") else {}) or {}
        names = _ATTR_RE.findall(str(chk.get("attribute") or "")) or _ATTR_RE.findall(formula)
        base = int(data.rules(root).get("attr_mod_base", 5))
        mod = sum(_mod(attrs.get(a.lower()), base) for a in names) if names else 0  # the sheet decides, never the referee's own number
        try:
            sit = int(chk.get("situation_mod") or 0)
        except (TypeError, ValueError):
            sit = 0
        if not sit:
            m2 = re.search(r"情境[^+-]*([+-]\d+)|situation[^+-]*([+-]\d+)", formula)
            sit = int(m2.group(1) or m2.group(2)) if m2 else 0
        mod += sit
        from neonrp.core import effects as _effects

        eff = _effects.check_mod(reg, "player")  # the player's open-schema effects (whatever the world named them)
        mod += eff
        chk["effects_mod"] = eff
        chk["attribute"] = "+".join(n.upper() for n in names) if names else chk.get("attribute")
        chk["situation_mod"] = sit
        formula = f"d20 + {chk['attribute'] or '0'}" + (f" {sit:+d}" if sit else "") + (f" 状态{eff:+d}" if eff else "")
        dm = _DICE_RE.search(str(chk.get("formula") or "d20"))
        n, sides = (int(dm.group(1) or 1), int(dm.group(2))) if dm else (1, 20)
        tier = str(chk.get("difficulty") or "").strip().lower().replace(" ", "_")
        dc = int(tiers[tier]) if tier in tiers else int(chk.get("dc") or tiers.get("normal") or 12)  # a named difficulty comes from the table
        chk["dc"] = dc
        # the referee (an LLM) decides what is rolled; the roll is the [dice] tool (10-03) — watched, one random backend
        from neonrp.core import tool_watch

        r = tool_watch.call(root, reg, "dice", "neonrp.packs.rpg.tools:dice",
                            {"dice": f"{max(1, min(n, 10))}d{sides}{mod:+d}", "vs": dc, "reason": question[:120], "source": "referee",
                             "who": "player", "attr": chk.get("attribute") or "", "seed_key": f"referee:{question[:40]}"}, res, seed=seed, source="referee")
        rolls = list(r.get("rolls") or [])
        total = int(r.get("total") or (sum(rolls) + mod))
        passed = total >= dc
        chk.update({"roll": sum(rolls), "mod": mod, "total": total, "result": "success" if passed else "fail"})
        line += _t(root, "ref_check", type=chk.get("type") or "", formula=formula, rolls="+".join(map(str, rolls)), mod=f"{mod:+d}", total=total, dc=dc,
                   res=_t(root, "pass" if passed else "fail"))
        cons = d.get("consequences") if isinstance(d.get("consequences"), dict) else {}
        pick = cons.get("on_success" if passed else "on_fail")
        if pick:
            line += _t(root, "ref_result", t=pick)
    if d.get("narrative_hint"):
        line += _t(root, "ref_hint", t=d["narrative_hint"])
    # a pending journey stop is settled by the ruling (the narrator asked the referee about the player's response to it)
    j = travel.journey(root)
    if j and j.get("pending"):
        verdict = str(d.get("ruling") or "")
        passed = (chk.get("result") == "success") if chk and chk.get("result") else verdict in ("allowed", "allowed_with_consequences", "allowed_but_hostile")
        settled = travel.resolve(root, reg, total=6 if passed else 0)
        if settled:
            line += _t(root, "ref_road", t=settled)
    return {"ok": True, "text": line, "ruling": d, "ms": ms}


_ZH_ATTR = {"力量": "STR", "敏捷": "DEX", "智力": "INT", "体质": "VIT", "魅力": "CHA", "交涉": "CHA", "口才": "CHA", "方向感": "INT"}


def roll_check(root: Path, reg: Any, check: dict[str, Any], *, seed: str = "") -> dict[str, Any]:
    """The ``roll_check`` seam (10-03, the planning seam): a check agreed while talking is rolled here, by the rule
    panel (packs/rpg/panel.py, 10-14) — d20 + the roller's attribute modifier + the effects' modifiers, against the
    difficulty tier. The attribute is the one the check names, else the rulebook's ``actions`` row for what it names,
    else ``fallback_attr``; a missing value is completed (role panel → baseline) and kept, never a silent +0. A DC
    number the host wrote reads as the nearest tier unless the world keeps numbers (``dc_numbers: keep``).
    A contest (``vs``) rolls both sides on the same attribute. Seeded: the same plan rolls the same numbers."""
    from neonrp.core import tool_watch
    from neonrp.packs.rpg import panel

    R = data.rules(root)
    base = int(R.get("attr_mod_base", 5))
    tiers = dict(R.get("referee_difficulty") or {})
    named = str(check.get("attr") or "").lower()
    attr, how = (named, "named") if named else panel.action_attr(root, panel.head(check))

    def side(who: str, tag: str) -> dict[str, Any]:
        v, src = panel.attr(root, reg, who, attr)
        smod, used = panel.status_mod(root, reg, who, check if tag == "a" else None)
        mod = v - base + smod
        vs_dc = None if check.get("vs") else dc_of()[0]
        d = tool_watch.call(root, reg, "dice", "neonrp.packs.rpg.tools:dice",
                            {"dice": f"1d20{mod:+d}", **({"vs": vs_dc} if vs_dc is not None else {}), "reason": str(check.get("why") or ""),
                             "source": "plan", "who": who, "attr": attr.upper(), "seed_key": f"check:{tag}:{who}:{check.get('why', '')[:30]}"},
                            None, seed=seed, source="plan")
        r = int((d.get("rolls") or [1])[0])
        return {"who": who, "roll": r, "mod": mod, "total": r + mod, "attr": attr.upper(), "value": v, "source": src, "effects": used}

    def dc_of() -> tuple[int, str]:
        raw = str(check.get("dc") or "").strip().lower()
        if raw in tiers:
            return int(tiers[raw]), raw
        if raw.isdigit():
            if str(R.get("dc_numbers") or "tier") == "keep":
                return int(raw), "number"
            k, v = panel.nearest_tier(tiers, int(raw))
            return v, f"{k}<-{raw}"
        return int(tiers.get("normal") or 12), "normal"

    a = side(str(check.get("who") or "player"), "a")
    out: dict[str, Any] = {**check, "a": a, "attr": check.get("attr") or attr.upper(), "attr_how": how}
    if check.get("adj") not in (None, ""):
        out["host_adj"] = check["adj"]  # recorded; the effects' own numbers are what counted
    if check.get("vs"):
        b = side(str(check["vs"]), "b")
        out.update({"b": b, "result": "success" if a["total"] >= b["total"] else "fail"})
    else:
        dc, tier = dc_of()
        out.update({"dc": dc, "tier": tier, "result": "success" if a["total"] >= dc else "fail"})
    return out
