"""rpg passive tools — requests the narrator writes as ``[roll d20]``: the engine runs them in ④ and
feeds the result back before the prose continues (设计 §7 被动工具). Seeded per turn + index, so a
re-proposal sees the same number."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neonrp.packs.rpg.i18n import t as _t

_DICE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$", re.IGNORECASE)


def roll(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    spec = str(op.get("dice") or op.get("args", [""])[0] if op.get("args") else op.get("dice") or "d20").strip().lower()
    m = _DICE.match(spec)
    if not m:
        return {"ok": False, "why": _t(root, "bad_dice", spec=spec)}
    from neonrp.core import dice as _dice

    n, sides, mod = int(m.group(1) or 1), int(m.group(2)), int(m.group(3) or 0)
    spec = f"{n}d{sides}{m.group(3) or ''}"  # canonical: the count is always written (1d6, 2d10)
    # every roll goes through core/dice (10-03): one random-number backend, one dice.rolled event
    r0 = _dice.roll_expr(spec, rng=_dice.rng_for(f"{seed}:{op.get('seed_key') or spec}")) or {"rolls": [1], "total": 1 + mod}
    rolls, total = r0["rolls"], r0["total"]
    text = f"{total}" + (f"({'+'.join(map(str, rolls))}{m.group(3) or ''})" if n > 1 or mod else "")
    # the road's referee: while a journey stop is pending, this die decides it (travel.resolve writes the outcome)
    from neonrp.core.modes import read_mode
    from neonrp.packs.rpg import travel

    own = op.get("source") in (None, "tool")  # a roll the narrator wrote; a referee's / a plan check's roll never settles a road stop
    verdict = "" if (read_mode(root) or not own) else travel.resolve(root, reg, total)  # inside a layer (combat) the fight itself settles the stop

    if verdict:
        text += " —— " + verdict
    return {"ok": True, "dice": spec, "rolls": rolls, "total": total, "text": text, "travel": verdict or None}


def dice(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[dice 1d20+2 vs 12]reason[/dice]`` — a checked roll: the requester writes what is tested and why, the engine
    writes the number and pass / fail (roll-over: total >= vs). Without ``vs`` it is a plain roll with a reason."""
    args = [str(a) for a in (op.get("args") or [])]
    spec = str(op.get("dice") or (args[0] if args else "") or "d20").strip()
    if "]" in spec:  # [dice 1d4+1]山贼乙的刀…掷伤害] — the closer was a bare bracket: the tail is the reason
        spec, tail = spec.split("]", 1)
        op["reason"] = (tail.strip("] ") + " " + str(op.get("reason") or "")).strip()
    vs = op.get("vs")
    if vs is None and "vs" in args:
        i = args.index("vs")
        vs = args[i + 1] if i + 1 < len(args) else None
    r = roll(root, reg, {**{k: v for k, v in op.items() if k in ("source", "seed_key", "who", "attr")}, "op": "roll", "dice": spec}, res, seed=seed)
    if not r.get("ok"):
        return r
    text = r["text"].split(" —— ")[0]
    if vs is not None:
        try:
            int(str(vs).strip())
        except ValueError:  # [dice 1d6 伤害] — the trailing words are the reason, not a target
            op["reason"] = (str(vs) + " " + str(op.get("reason") or "")).strip()
            vs = None
    if vs is not None:
        target = int(str(vs).strip())
        passed = int(r["total"]) >= target
        text = f"{text} vs {target} —— {_t(root, 'pass' if passed else 'fail')}"
        r.update({"vs": target, "passed": passed, "request": f"dice {r['dice']} vs {target}"})  # the reply tag reads <dice 1d20+2 vs 12>
    if r.get("travel"):
        text += " —— " + r["travel"]
    if op.get("reason"):
        r["reason"] = str(op["reason"])[:300]
    label = check_label(root, reg, op)
    if label:
        r["label"] = label  # a named roll: the world's `check` triggers hear it (core/triggers.py)
    return {**r, "text": text}


_LABEL_END = " ·・:：,，、—-/|（("


def check_label(root: Path, reg: Any, op: dict[str, Any]) -> str:
    """What a checked roll tests, when it names it: ``label`` / ``attr`` given, else the reason opening with one of the
    roller's attributes / skills or a rule-table row's name (「识·读朔」 → 识). Empty when it names none."""
    for k in ("label", "attr"):
        if str(op.get(k) or "").strip():
            return str(op[k]).strip()
    why = str(op.get("reason") or "").strip()
    if not why:
        return ""
    from neonrp.packs.rpg import data as _data
    from neonrp.packs.rpg import sheet as _sheet

    e = reg.entries.get(str(op.get("who") or "player")) if reg is not None else None
    props = (e.props if e is not None else None) or {}
    names = [str(k) for k in (props.get("attributes") or {})] if isinstance(props.get("attributes"), dict) else []
    sk = props.get("skills") or []
    names += [str(k) for k in sk] if isinstance(sk, dict) else [str(x.get("name")) for x in sk if isinstance(x, dict) and x.get("name")]
    try:
        R = _data.rules(root)
        names += [n for t in ("attrs", "skills") for key, row in (R.get(t) or {}).items() if isinstance(row, dict) for n in _sheet._names(key, row)]
    except Exception:  # noqa: BLE001 — no table: the sheet's own names
        pass
    for n in sorted({n for n in names if n}, key=len, reverse=True):
        if why.casefold().startswith(n.casefold()) and (len(why) == len(n) or why[len(n)] in _LABEL_END):
            return n
    return ""


from neonrp.packs.rpg.atlas.draw import _map_data, draw_map  # noqa: E402,F401 — the map moved to the map tool (atlas)


_SHEET_L = {"zh": ("生命", "属性", "技艺", "装备", "背包", "钱袋", "状态", "无"), "en": ("HP", "Attributes", "Skills", "Equipment", "Pack", "Purse", "Status", "none"),
            "ja": ("HP", "能力", "技", "装備", "持ち物", "財布", "状態", "なし")}


def sheet(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[~sheet]`` — the player's own sheet as a panel (adversarial2 F2: asked for 「属性面板」, the narrator read every
    number into the prose — a fourth-wall break). Drawn from the files, shown to the player, never fed to the narrator."""
    import json

    from neonrp.core.adv import run_lang

    g = root / "game" / "player"

    def rd(n: str) -> dict:
        try:
            return json.loads((g / n).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    st, inv, wal, eq = rd("stats.json"), rd("inventory.json"), rd("wallet.json"), rd("equipment.json")
    L = _SHEET_L.get(run_lang(root), _SHEET_L["zh"])
    hp = st.get("hp") or {}
    attrs = " · ".join(f"{k.upper()} {v}" for k, v in (st.get("attributes") or {}).items())
    skills = "、".join(str(x.get("name") or x.get("id")) for x in st.get("skills") or []) or L[7]
    pieces: list[Any] = []
    for v in (eq.values() if isinstance(eq, dict) else []):
        pieces += v if isinstance(v, list) else [v]
    gear = "、".join(str(x.get("name") or x.get("id")) if isinstance(x, dict) else str(x) for x in pieces if x)
    items = "、".join(f"{x.get('name') or x.get('id')}×{x.get('qty', 1)}" for x in inv.get("items") or []) or L[7]
    purse = " ".join(f"{wal[k]}{u}" for k, u in (("gold", "g"), ("silver", "s"), ("copper", "c")) if wal.get(k) is not None)
    status = "、".join(str(x.get("name") or x) if isinstance(x, dict) else str(x) for x in st.get("status_effects") or []) or L[7]
    lines = [f"{L[0]} {hp.get('current')}/{hp.get('max')}", f"{L[1]} {attrs}", f"{L[2]} {skills}"]
    try:  # each skill on its own line with its one-line note, named as the rule table names it (10-19: every skill explained)
        from neonrp.core import sheet as _sh

        rows = [r for r in _sh.sheet(root, reg=reg).get("skills") or [] if r.get("desc")]
        if rows:
            lines[2] = f"{L[2]}\n" + "\n".join(f"  {r['label']} {r.get('value')}" + (f"% — {r['desc']}" if r.get("check") is not None else f" — {r['desc']}")
                                                for r in rows)
    except Exception:  # noqa: BLE001 — the plain list stays
        pass
    if gear:
        lines.append(f"{L[3]} {gear}")
    lines += [f"{L[4]} {items}", f"{L[5]} {purse}", f"{L[6]} {status}"]
    text = "\n".join(lines)
    return {"ok": True, "text": text, "panel": "sheet", "request": "sheet",
            "panel_value": {"id": "sheet", "format": "text", "source": "tool", "text": text}}
