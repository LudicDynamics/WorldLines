"""pct's rules referee: the same one-shot JSON ruling as rpg's (``[referee 玩家想做的事]``), but the check it asks for
is a percentile one — ``{"skill": "<skill or attribute>", "modifier": <points, optional>}`` — rolled by the engine
(d100 ≤ the player's value + modifier); the referee never rolls and never writes a DC."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def ruling(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    from neonrp import prompts
    from neonrp.core import modes, sdk
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.turn_v3 import _adapter, _chat
    from neonrp.packs.pct import rules as _r
    from neonrp.packs.rpg.i18n import t as _t
    from neonrp.packs.rpg.referee import _json

    question = str(op.get("question") or " ".join(op.get("args") or []) or "").strip()
    if not question:
        return {"ok": False, "why": _t(root, "ref_need_q")}
    lang = prompt_lang(root)
    S = prompts.strings("pct", lang)
    spec = modes.spec_of(root, "referee") or {}
    system = modes.layer_system(root, reg, "referee", lang)
    pk = sdk.render_pack(sdk.pack(root, registry=reg))
    user = "\n\n".join(x for x in (pk, modes.reads_block(root, reg, spec), _t(root, "ref_q_head") + "\n" + question, S["ref_json"]) if x)
    text, ms, _usage = _chat(_adapter(root, None, "adv"), system, user)
    d = _json(text)
    if not d:
        return {"ok": False, "why": _t(root, "ref_no_json"), "raw": text[:300], "ms": ms}
    line = _t(root, "ref_ruling", r=d.get("ruling") or "?")
    if d.get("reason"):
        line += f"({d['reason']})"
    chk = d.get("check") if isinstance(d.get("check"), dict) else None
    if chk and (chk.get("skill") or chk.get("attribute")):
        R = _r.rules(root)
        hit = _r.find_target(R, reg.entries.get("player"), f"{chk.get('skill') or ''} {chk.get('attribute') or ''}", lang=lang)
        if hit is not None:
            label, target = hit
            try:
                target = max(1, min(99, target + int(chk.get("modifier") or 0)))
            except (TypeError, ValueError):
                pass
            r = _r.roll_d100(root, reg, "player", target, question[:120], seed=seed, key=f"referee:{question[:40]}", source="referee")
            lv = str(r.get("level") or "fail")
            chk.update({"label": label, "target": target, "roll": r.get("total"), "level": lv, "result": "success" if _r.passed(lv) else "fail"})
            line += f" · {label} " + S["check_text"].format(roll=r.get("total"), op="≤" if int(r.get("total") or 0) <= target else ">", target=target, result=S[lv])
            cons = d.get("consequences") if isinstance(d.get("consequences"), dict) else {}
            pick = cons.get("on_critical_success" if lv == "crit" else "on_critical_fail" if lv == "fumble" else "on_success" if _r.passed(lv) else "on_fail") \
                or cons.get("on_success" if _r.passed(lv) else "on_fail")
            if pick:
                line += _t(root, "ref_result", t=pick)
    if d.get("narrative_hint"):
        line += _t(root, "ref_hint", t=d["narrative_hint"])
    return {"ok": True, "text": line, "ruling": d, "ms": ms}
