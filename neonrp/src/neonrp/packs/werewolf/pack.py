"""Werewolf (狼人杀) — the second built-in template, and the proof that the core is template-free:
no map, no towns, everyone at one table; seats are a registered class; `vote` / `kill` are
template ops with their own validator + handler; the endings are WHEN / IF / THEN rows; the
world-side contract is a judge, not a narrator.

    game/seats/S01.json … {"id": "S01", "class": "seat", "props": {"name": "阿明", "role": "wolf", "alive": true, "votes": 0}}
    game/meta/table.json   {"wolves": 2, "villagers": 4, "phase": "day", "round": 1}   (the pack's variables)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.core.handlers import Verdict
from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import ActionSpec, ClassSpec

from neonrp import prompts

_OPS = {lg: prompts.strings("werewolf", lg) for lg in ("zh", "en", "ja", "ko")}  # op docs the model reads: prompts/werewolf.<lang>.json (10-16)


def _op_zh(key: str) -> str:
    return _OPS["zh"][key]


def _op_i18n(key: str) -> dict[str, str]:
    return {lg: _OPS[lg][key] for lg in ("en", "ja", "ko")}


CLASSES: dict[str, ClassSpec] = {
    "world": ClassSpec("world", None, ["name"], []),
    "player": ClassSpec("player", None, ["name"], []),
    "soul": ClassSpec("soul", None, ["name"], []),
    "seat": ClassSpec("seat", None, ["name"], [], prompts.by_lang("werewolf", "seat_render"),  # the judge sees every role (P4 hides it from seats)
                      folder="game/seats", scope="world", tier=0, id_prefix="S",
                      props={"role": {"type": "enum", "values": ["wolf", "villager", "seer"]}, "alive": {"type": "bool"}, "votes": {"type": "int", "min": 0}},
                      mutable=["alive", "votes"], person=True),
}

ACTIONS: list[ActionSpec] = [
    ActionSpec("vote", "action", "neonrp.packs.werewolf.pack:vote", ["who", "target"], validator="neonrp.packs.werewolf.pack:judge_vote",
               doc=_op_zh("op_vote"), doc_i18n=_op_i18n("op_vote")),
    ActionSpec("kill", "action", "neonrp.packs.werewolf.pack:kill", ["target"], validator="neonrp.packs.werewolf.pack:judge_kill",
               doc=_op_zh("op_kill"), doc_i18n=_op_i18n("op_kill")),
    ActionSpec("phase", "update", "neonrp.packs.werewolf.pack:phase", ["value"], doc=_op_zh("op_phase"), doc_i18n=_op_i18n("op_phase")),
    ActionSpec("set", "update", "set_variable", ["var", "value"], doc=_op_zh("op_set"), doc_i18n=_op_i18n("op_set")),
    ActionSpec("add", "update", "add_variable", ["var", "delta"], doc=_op_zh("op_add"), doc_i18n=_op_i18n("op_add")),
    ActionSpec("flag", "update", "set_flag", ["key"], doc=_op_zh("op_flag"), doc_i18n=_op_i18n("op_flag")),
    ActionSpec("need", "request", "need", ["who"], alias="ask", doc=_op_zh("op_need"), doc_i18n=_op_i18n("op_need")),
    ActionSpec("patch", "update", "patch_props", ["who", "props"], doc=_op_zh("op_patch"), doc_i18n=_op_i18n("op_patch")),
]

VARIABLES = {
    # counts are maintained by the kill handler, never by the judge: readonly = verify refuses set/add
    # (testbed 09-27: the judge did `kill` AND `add table.wolves -1` → a false ending; P2 makes these formulas)
    "table.wolves": {"type": "int", "path": "game/meta/table.json", "key": "wolves", "min": 0, "readonly": True, "doc": prompts.by_lang("werewolf", "var_wolves")},
    "table.villagers": {"type": "int", "path": "game/meta/table.json", "key": "villagers", "min": 0, "readonly": True, "doc": prompts.by_lang("werewolf", "var_villagers")},
    "table.round": {"type": "int", "path": "game/meta/table.json", "key": "round", "min": 1},
    "table.phase": {"type": "str", "path": "game/meta/table.json", "key": "phase", "readonly": True, "doc": prompts.by_lang("werewolf", "var_phase")},
}

TRIGGERS = {
    "village_wins": {"when": {"var": "table.wolves"}, "if": [{"var": "table.wolves", "<=": 0}],
                     "then": [{"to": "end", "ending": "E_VILLAGE", "title": prompts.by_lang("werewolf", "end_village")}]},
    "wolves_win": {"when": {"var": "table.villagers"}, "if": [{"var": "table.villagers", "<=": 1}],
                   "then": [{"to": "end", "ending": "E_WOLVES", "title": prompts.by_lang("werewolf", "end_wolves")}]},
}

MECHANICS = {
    "contract": "neonrp.packs.werewolf.pack:contract",
    "observe": "neonrp.packs.werewolf.pack:observe",
    "participation": "neonrp.packs.werewolf.pack:everyone",
    "soul_turn": "builtin:none",
    "settle": "builtin:none",
    "run_outputs": "neonrp.packs.werewolf.pack:run_outputs",
}


# ── handlers ─────────────────────────────────────────────────────────────────

def _table_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "table.json"


def _seat(reg: Any, ref: str) -> Any:
    sid = reg.resolve(str(ref), cls="seat") or str(ref)
    e = reg.entries.get(sid)
    return e if e is not None and e.cls == "seat" else None


def judge_vote(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    a, b = _seat(reg, op.get("who", "")), _seat(reg, op.get("target", ""))
    alive = [f"{e.id}({e.props.get('name')})" for e in reg.of_class("seat") if e.props.get("alive", True)]
    if a is None or b is None:
        return Verdict(False, reason=f"both sides of a vote must be seats: {op.get('who')!r} → {op.get('target')!r}", allowed=alive)
    if not a.props.get("alive", True) or not b.props.get("alive", True):
        return Verdict(False, reason="a seat that is out can neither vote nor be voted for", allowed=alive)
    return Verdict(True, data={"who": a.id, "target": b.id})


def vote(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    b = reg.entries[op["target"]]
    b.props["votes"] = int(b.props.get("votes", 0)) + 1
    _save_seat(root, reg, b)
    a = _seat(reg, op.get("who", ""))
    _log(root, "vote_log", {"who": a.id if a is not None else str(op.get("who") or ""), "target": b.id})  # 10-08: the accusation record
    return {"votes": b.props["votes"]}


def judge_kill(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    b = _seat(reg, op.get("target", ""))
    if b is None or not b.props.get("alive", True):
        return Verdict(False, reason="only a living seat can be put out", allowed=[e.id for e in reg.of_class("seat") if e.props.get("alive", True)])
    return Verdict(True, data={"target": b.id})


def kill(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    b = reg.entries[op["target"]]
    b.props["alive"] = False
    _save_seat(root, reg, b)
    _log(root, "exiles", {"target": b.id, "name": b.props.get("name"), "role": b.props.get("role")})  # day = exiled · night = killed
    wolves = sum(1 for e in reg.of_class("seat") if e.props.get("alive", True) and e.props.get("role") == "wolf")
    villagers = sum(1 for e in reg.of_class("seat") if e.props.get("alive", True) and e.props.get("role") != "wolf")
    t = _read(_table_path(root))
    t.update({"wolves": wolves, "villagers": villagers})
    _table_path(root).write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, val in (("table.wolves", wolves), ("table.villagers", villagers)):
        if name in reg.variables:
            reg.variables[name].value = val
    return {"role": b.props.get("role"), "wolves": wolves, "villagers": villagers}


def phase(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    t = _read(_table_path(root))
    t["phase"] = str(op.get("value") or "day")
    if t["phase"] == "day":
        t["round"] = int(t.get("round", 1)) + 1
    _table_path(root).write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, key in (("table.phase", "phase"), ("table.round", "round")):
        if name in reg.variables:
            reg.variables[name].value = t[key]
    return {"phase": t["phase"], "round": t.get("round")}


def _log(root: Path, key: str, row: dict[str, Any]) -> None:
    """Append a row (stamped with the table's round and phase) to table.json[key] — what the run's settlement reads."""
    t = _read(_table_path(root))
    t.setdefault(key, []).append({"round": t.get("round", 1), "phase": t.get("phase", "day"), **row})
    _table_path(root).parent.mkdir(parents=True, exist_ok=True)
    _table_path(root).write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")


def run_outputs(root: Path, reg: Any, contract: dict[str, Any] | None) -> dict[str, Any]:
    """At the run's exit (10-08 E4): ``accusation`` = each day's exile with the votes of that round;
    ``truth_reveal`` adds every seat's role (the plot's reveal text comes from the engine)."""
    t = _read(_table_path(root))
    votes = [v for v in t.get("vote_log") or [] if isinstance(v, dict)]
    acc = [{**x, "votes": [{"who": v.get("who"), "target": v.get("target")} for v in votes if v.get("round") == x.get("round") and v.get("phase") == "day"]}
           for x in t.get("exiles") or [] if isinstance(x, dict) and x.get("phase") == "day"]
    night = [x for x in t.get("exiles") or [] if isinstance(x, dict) and x.get("phase") == "night"]
    roles = [{"id": e.id, "name": e.props.get("name"), "role": e.props.get("role"), "alive": bool(e.props.get("alive", True))}
             for e in sorted(reg.of_class("seat"), key=lambda e: e.id)]
    return {"accusation": acc, "truth_reveal": {"roles": roles, "night": night}}


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_seat(root: Path, reg: Any, e: Any) -> None:
    p = root / (e.source or f"game/seats/{e.id}.json")
    d = _read(p)
    d.update({"id": e.id, "class": "seat", "props": dict(e.props)})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ── mechanics ────────────────────────────────────────────────────────────────

_TABLE = "werewolf"

def _G(lang: str) -> dict[str, Any]:
    from neonrp import prompts

    return prompts.strings(_TABLE, lang)


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def contract(root: Path, reg: Any, structured: str = "together") -> str:
    """The judge's contract: rules + the ADV format generated from this pack's tables (no hand-written op list)."""
    from neonrp.core.adv import assemble
    from neonrp.core.output_lang import prompt_lang
    from neonrp.packs import resolve as _resolve_pack

    t = _read(_table_path(root))
    lang = prompt_lang(root)
    rules = _f(_G(lang)["rules"], round=t.get('round', 1), phase=t.get('phase', 'day'), wolves=t.get('wolves'), villagers=t.get('villagers'))
    return assemble(root, reg, rules=rules, lang=lang, blocks=tuple(_resolve_pack(root).blocks))


def observe(root: Path, iid: str) -> str:
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    t = _read(_table_path(root))
    from neonrp.core.output_lang import prompt_lang

    G = _G(prompt_lang(root))
    rows = [_f(G["seat"], id=e.id, name=e.props.get('name')) + ("" if e.props.get("alive", True) else G["out"]) for e in reg.of_class("seat")]
    return _f(G["observe"], round=t.get('round', 1), phase=t.get('phase', 'day'), iid=iid) + "\n".join(rows)


def everyone(root: Path, reg: Any, iid: str) -> bool:
    return True


def _pack():
    from neonrp.packs import Pack

    return Pack("werewolf", dict(CLASSES), list(ACTIONS), dict(VARIABLES), dict(TRIGGERS), dict(MECHANICS), "",
                "狼人杀:一张桌子、座位类、vote / kill 模板操作、法官契约、两条结局规则。", "builtin")


PACK = _pack()
# the agent loop (Pack.loop, 09-30): this template only exists on the five-phase loop — its ops, validators
# and ending triggers land through sdk.apply, which v2b never calls
PACK.loop = {"turn": {"mode": "v3"}}
PACK.cast_class = "seat"  # the six seats are the cast (a contract's entry.cast: fixed)
# the day / night of the table as two nodes of the orchestration graph (O3, 10-05): the phase op is the edge
PACK.orchestration = {
    "nodes": {"day": {"kind": "phase", "var": "table.phase", "value": "day", "title": "day"},
              "night": {"kind": "phase", "var": "table.phase", "value": "night", "title": "night"}},
    "edges": [{"id": "day>night:phase", "from": "day", "to": "night", "on": {"op": "phase", "value": "night"}},
              {"id": "night>day:phase", "from": "night", "to": "day", "on": {"op": "phase", "value": "day"}}],
}
