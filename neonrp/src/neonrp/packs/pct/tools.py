"""pct tools: the d100 check, damage dice, the sanity check.

    [dice 1d100 vs 60]why[/dice]   roll-under: ≤ 60 succeeds (BRP: ≤ 1/20 critical, ≤ 1/5 special, 99 / 00 fumble)
    [dice 察觉]why[/dice]           the player's skill / attribute by name (any language) → the same check
    [dice 1d6+1d4]why[/dice]        damage and other sums: the plain total (several dice terms, + / −)
    [san 0/1d6 看见尸体]            sanity: d100 ≤ current SAN → lose the first amount, else the second; losing half
                                    the SAN the scene began with (``san_insane_ratio``) → temporary insanity (BRP; one
                                    resolve stands for BRP's five minutes)

What the sanity score is called on screen is a world's choice: ``rules.json`` ``san_names`` = ``{"name": {lang: …},
"short": {lang: …}}`` (the word in sentences, the label beside the number); without it, the pack's strings (zh 理智 / en composure).
Only the shown words change — the op stays ``san``, the variable ``player.san``.

Tools run while the narrator writes (before the apply); the sanity loss is the engine's own write into the player's
sheet (like the road's days), and what must land as state (a status, the insane event) is left in the player's
Character State for the pack's tick (packs/pct/tick.py) to create inside the apply.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from neonrp.packs.pct import rules as _r

_TERM = re.compile(r"([+-]?)\s*(?:(\d*)d(\d+)|(\d+))", re.IGNORECASE)


def _S(root: Path) -> dict[str, str]:
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("pct", prompt_lang(root))


def san_names(R: dict[str, Any], lang: str, S: dict[str, str] | None = None) -> dict[str, str]:
    """{"sname", "sshort"}: the sanity score's word and its label in ``lang`` (the world's ``san_names``, else the pack's)."""
    from neonrp import prompts
    from neonrp.core.output_lang import pick_lang

    S = S if S is not None else prompts.strings("pct", lang)
    names = R.get("san_names") if isinstance(R.get("san_names"), dict) else {}
    out = {}
    for key, dflt in (("name", "san_name"), ("short", "san_short")):
        v = names.get(key)
        out["s" + key] = (pick_lang(v, lang, "") if isinstance(v, dict) else str(v or "")) or str(S.get(dflt) or "SAN")
    return out


def roll_sum(spec: str, *, seed_key: str) -> tuple[int, list[int]] | None:
    """「1d6+1d4」「2d6-1」「1d10+2」 → (total, every die). None when it does not read as dice."""
    from neonrp.core import dice as _dice

    s = str(spec or "").replace(" ", "")
    if not s or not re.fullmatch(r"([+-]?(\d*d\d+|\d+))+", s, re.IGNORECASE):
        return None
    rng = _dice.rng_for(seed_key)
    total, rolls = 0, []
    for k, m in enumerate(_TERM.finditer(s)):
        sign = -1 if m.group(1) == "-" else 1
        if m.group(3):
            n, sides = int(m.group(2) or 1), int(m.group(3))
            r = _dice.roll_expr(f"{n}d{sides}", rng=rng) or {"rolls": [1] * n, "total": n}
            rolls += r["rolls"]
            total += sign * int(r["total"])
        else:
            total += sign * int(m.group(4))
    return total, rolls


def _d100(seed: str, key: str) -> int:
    from neonrp.core import dice as _dice

    r = _dice.roll_expr("1d100", rng=_dice.rng_for(f"{seed}:{key}")) or {"total": 50}
    return int(r["total"])


def dice(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    S = _S(root)
    R = _r.rules(root)
    args = [str(a) for a in (op.get("args") or [])]
    spec = str(op.get("dice") or (args[0] if args else "") or "1d100").strip()
    if "]" in spec:
        spec, tail = spec.split("]", 1)
        op["reason"] = (tail.strip("] ") + " " + str(op.get("reason") or "")).strip()
    vs = op.get("vs")
    if vs is None and "vs" in args:
        i = args.index("vs")
        vs = args[i + 1] if i + 1 < len(args) else None
    key = str(op.get("seed_key") or spec)
    label = str(op.get("label") or "")  # the caller named the check (a skill command, a talk's check)
    target: int | None = None
    if vs is not None:
        try:
            target = int(str(vs).strip())
        except ValueError:
            op["reason"] = (str(vs) + " " + str(op.get("reason") or "")).strip()
            target = None
    if roll_sum(spec, seed_key="probe") is None:  # a skill / attribute by name: the player's (or `who`'s) value
        who = str(op.get("who") or "player")
        hit = _r.find_target(R, reg.entries.get(who), spec + " " + " ".join(args[1:]))
        if hit is None:
            return {"ok": False, "why": f"unknown check {spec!r}"}
        label, target = hit
        spec = "1d100"
    if re.fullmatch(r"1?d100", spec.replace(" ", ""), re.IGNORECASE) and target is not None:
        roll = _d100(seed, key)
        lv = _r.level(roll, target, R)
        ok = _r.passed(lv)
        text = S["check_text"].format(roll=roll, op="≤" if roll <= target else ">", target=target, result=S[lv])
        out = {"ok": True, "dice": "1d100", "rolls": [roll], "total": roll, "vs": target, "passed": ok, "under": True,
               "level": lv, "label": label, "text": text, "request": f"dice 1d100 vs {target}",
               **_r.bands(target, R)}  # why it is that tier
    else:
        got = roll_sum(spec, seed_key=f"{seed}:{key}")
        if got is None:
            return {"ok": False, "why": f"bad dice {spec!r}"}
        total, rolls = got
        out = {"ok": True, "dice": spec.replace(" ", ""), "rolls": rolls, "total": total,
               "text": f"{total}" + (f"({'+'.join(map(str, rolls))})" if len(rolls) > 1 else "")}
    if op.get("reason"):
        out["reason"] = str(op["reason"])[:300]
    return out


def _stats_path(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "player" / "stats.json"


def san(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[san 0/1d6 理由]`` — the sanity check and its loss, written into the player's sheet now."""
    from neonrp.packs.rpg import character_state as cs

    S = _S(root)
    R = _r.rules(root)
    args = [str(a) for a in (op.get("args") or [])]
    spec = str(op.get("spec") or (args[0] if args else "")).strip()
    why = str(op.get("reason") or op.get("why") or " ".join(args[1:]) or "")
    m = re.match(r"^\s*([0-9d+\-]+)\s*/\s*([0-9d+\-]+)\s*$", spec, re.IGNORECASE)
    if not m:
        return {"ok": False, "why": f"bad sanity spec {spec!r} (want 0/1d6)"}
    p = _stats_path(root)
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "why": "no player sheet"}
    sanity = st.get("san") if isinstance(st.get("san"), dict) else {"current": st.get("san"), "max": R.get("san_max", 99)}
    cur = int(sanity.get("current") or 0)
    key = str(op.get("seed_key") or f"san:{spec}:{why[:20]}")
    roll = _d100(seed, key)
    lv = _r.level(roll, cur, R)
    ok = _r.passed(lv)
    lost = roll_sum(m.group(1) if ok else m.group(2), seed_key=f"{seed}:{key}:loss")
    loss = max(0, int(lost[0])) if lost else 0
    new = max(0, cur - loss)
    sanity["current"] = new
    st["san"] = sanity
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if "player.san" in getattr(reg, "variables", {}):
        reg.variables["player.san"].value = new
    from neonrp.core.output_lang import prompt_lang

    sn = san_names(R, prompt_lang(root), S)
    text = S["san_text"].format(roll=roll, op="≤" if roll <= cur else ">", san=cur, result=S[lv], loss=loss, a=cur, b=new, **sn)
    text = text[:1].upper() + text[1:]  # the line opens a sentence (en «Nerve check …»; no-op for zh / ja / ko)
    out: dict[str, Any] = {"ok": True, "dice": "1d100", "rolls": [roll], "total": roll, "vs": cur, "passed": ok, "under": True,
                           "level": lv, "loss": loss, "san": [cur, new], "request": f"san {spec}", "reason": why[:300],
                           **_r.bands(cur, R)}
    state = cs.read(root, "player")
    pend = list(state.get("pending_status") or [])
    turn = int(reg.variables["turn"].value or 0) if "turn" in getattr(reg, "variables", {}) else 0
    win = state.get("san_window") if isinstance(state.get("san_window"), dict) and state["san_window"].get("turn") == turn else {"turn": turn, "start": cur, "lost": 0}
    win["lost"] = int(win.get("lost") or 0) + loss
    cs.write(root, "player", san_window=win)
    limit = max(1, math.ceil(int(win.get("start") or cur) * float(R.get("san_insane_ratio", 0.5))))
    if loss and win["lost"] >= limit and new > 0 and "insane_temp" not in pend:  # BRP: half the SAN at once (here: one resolve)
        text += "; " + S["san_insane"].format(loss=win["lost"], limit=limit)
        pend.append("insane_temp")
    if new <= 0:
        text += "; " + S["san_zero"].format(**sn)
        pend.append("insane_perm")
    if pend:
        cs.write(root, "player", pending_status=pend)
    out["text"] = text
    return out
