"""Monopoly (大富翁) — the third built-in template: a RING map (advance = (pos + dice) mod N), money
that is settled by procedure (rent / tax / GO), a narrator LLM that only narrates and decides
buys, and endings as rules. Everything numeric is deterministic and seeded.

    game/board/B01.json … {"id": "B01", "class": "tile", "props": {"name": "起点", "kind": "go", "price": 0, "rent": 0, "owner": "", "houses": 0}}
    game/seats/S01.json … {"id": "S01", "class": "seat", "props": {"name": "阿明", "cash": 150, "pos": 0, "alive": true}}
    game/meta/table.json   {"turn_of": "S01", "round": 1, "alive": 3, "seed": 7, "n": 12, "last": ""}

Turn shape (what the phase machine will formalise, P3): the engine rolls for `turn_of` BEFORE the
narrator speaks (`roll` is a procedure, not an LLM decision); the narrator then narrates the landing
and proposes `buy` / `endturn`; `endturn` passes the dice to the next living seat.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from neonrp.core.handlers import Verdict
from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import ActionSpec, ClassSpec

from neonrp import prompts

_OPS = {lg: prompts.strings("monopoly", lg) for lg in ("zh", "en", "ja", "ko")}  # op docs the model reads: prompts/monopoly.<lang>.json (10-16)


def _op_zh(key: str) -> str:
    return _OPS["zh"][key]


def _op_i18n(key: str) -> dict[str, str]:
    return {lg: _OPS[lg][key] for lg in ("en", "ja", "ko")}


GO_BONUS = 100
CHANCE = [("路上捡到钱包", 60), ("交医药费", -40), ("彩票中奖", 80), ("车子抛锚修车", -30), ("生日,每人送你祝福", 20)]

CLASSES: dict[str, ClassSpec] = {
    "world": ClassSpec("world", None, ["name"], []),
    "player": ClassSpec("player", None, ["name"], []),
    "soul": ClassSpec("soul", None, ["name"], []),
    "tile": ClassSpec("tile", None, ["name"], [], "- {id} {name}[{kind}] 价{price} 租{rent} 主:{owner}",
                      folder="game/board", scope="world", tier=1, id_prefix="B",
                      props={"kind": {"type": "enum", "values": ["go", "street", "chance", "tax", "rest"]}, "price": {"type": "int", "min": 0},
                             "rent": {"type": "int", "min": 0}, "owner": {"type": "str"}, "houses": {"type": "int", "min": 0, "max": 4}},
                      mutable=["owner", "houses"]),
    "seat": ClassSpec("seat", None, ["name"], [], "- {id} {name} 现金{cash} 位置{pos} 在局:{alive}",
                      folder="game/seats", scope="world", tier=0, id_prefix="S",
                      props={"cash": {"type": "int"}, "pos": {"type": "int", "min": 0}, "alive": {"type": "bool"}},
                      mutable=["cash", "pos", "alive"]),
}

ACTIONS: list[ActionSpec] = [
    ActionSpec("roll", "action", "neonrp.packs.monopoly.pack:roll", ["who"], validator="neonrp.packs.monopoly.pack:judge_roll", scope="engine",
               doc=_op_zh("op_roll"), doc_i18n=_op_i18n("op_roll")),
    ActionSpec("buy", "action", "neonrp.packs.monopoly.pack:buy", ["who", "tile"], validator="neonrp.packs.monopoly.pack:judge_buy",
               doc=_op_zh("op_buy"), doc_i18n=_op_i18n("op_buy")),
    ActionSpec("endturn", "action", "neonrp.packs.monopoly.pack:endturn", [], doc=_op_zh("op_endturn"), doc_i18n=_op_i18n("op_endturn")),
    ActionSpec("patch", "update", "patch_props", ["who", "props"], doc=_op_zh("op_patch"), doc_i18n=_op_i18n("op_patch")),
    ActionSpec("flag", "update", "set_flag", ["key"], doc=_op_zh("op_flag"), doc_i18n=_op_i18n("op_flag")),
]

VARIABLES = {
    "table.turn_of": {"type": "str", "path": "game/meta/table.json", "key": "turn_of", "readonly": True, "doc": "轮到谁(endturn 推进)"},
    "table.round": {"type": "int", "path": "game/meta/table.json", "key": "round", "readonly": True},
    "table.alive": {"type": "int", "path": "game/meta/table.json", "key": "alive", "readonly": True, "doc": "还没破产的座位数(引擎自算)"},
    "table.last": {"type": "str", "path": "game/meta/table.json", "key": "last", "readonly": True, "doc": "上一次掷骰结算的一句话"},
}

TRIGGERS = {
    # reactions on the op event (P1): the narrator hears exactly what the dice did
    "landed": {"when": {"op": "roll"}, "then": [{"to": "narration", "text": "(引擎结算){who_name} 掷出 {dice} → {landed_name}:{event}"}]},
    "broke": {"when": {"op": "roll"}, "if": [{"var": "table.alive", "<=": 1}], "then": [{"to": "end", "ending": "E_LAST", "title": "最后一个没破产的人"}]},
    "round_cap": {"when": {"var": "table.round"}, "if": [{"var": "table.round", ">=": 20}], "then": [{"to": "end", "ending": "E_TIME", "title": "二十轮到,数钱"}]},
}

MECHANICS = {
    "contract": "neonrp.packs.monopoly.pack:contract",
    "observe": "neonrp.packs.monopoly.pack:observe",
    "participation": "neonrp.packs.monopoly.pack:everyone",
    "soul_turn": "builtin:none",
    "settle": "builtin:none",
}


# ── state helpers ────────────────────────────────────────────────────────────

def _table_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "table.json"


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(p: Path, d: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _save(root: Path, reg: Any, e: Any) -> None:
    p = root / (e.source or f"game/{'board' if e.cls == 'tile' else 'seats'}/{e.id}.json")
    d = _read(p)
    d.update({"id": e.id, "class": e.cls, "props": dict(e.props)})
    _write(p, d)


def _seat(reg: Any, ref: str) -> Any:
    sid = reg.resolve(str(ref), cls="seat") or str(ref)
    e = reg.entries.get(sid)
    return e if e is not None and e.cls == "seat" else None


def _tiles(reg: Any) -> list[Any]:
    return sorted(reg.of_class("tile"), key=lambda e: e.id)


def _sync_table(root: Path, reg: Any, **more: Any) -> dict[str, Any]:
    t = _read(_table_path(root))
    t["alive"] = sum(1 for s in reg.of_class("seat") if s.props.get("alive", True))
    t.update(more)
    _write(_table_path(root), t)
    for name, key in (("table.turn_of", "turn_of"), ("table.round", "round"), ("table.alive", "alive"), ("table.last", "last")):
        if name in reg.variables and key in t:
            reg.variables[name].value = t[key]
    return t


# ── ops ──────────────────────────────────────────────────────────────────────

def judge_roll(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    t = _read(_table_path(root))
    s = _seat(reg, op.get("who", ""))
    if s is None:
        return Verdict(False, reason=f"{op.get('who')!r} is not a seat", allowed=[e.id for e in reg.of_class("seat")])
    if s.id != t.get("turn_of"):
        return Verdict(False, reason=f"it is {t.get('turn_of')}'s turn, not {s.id}'s", allowed=[str(t.get("turn_of"))])
    if not s.props.get("alive", True):
        return Verdict(False, reason="a bankrupt seat does not roll")
    return Verdict(True, data={"who": s.id})


def roll(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    """Dice → advance on the ring → settle the landing. Seeded per (seed, round, seat)."""
    t = _read(_table_path(root))
    s = reg.entries[op["who"]]
    tiles = _tiles(reg)
    n = len(tiles)
    rng = random.Random(f"{t.get('seed', 0)}:{t.get('round', 1)}:{s.id}")
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    start = int(s.props.get("pos", 0))
    pos = (start + a + b) % n
    passed_go = start + a + b >= n
    events: list[str] = []
    if passed_go:
        s.props["cash"] = int(s.props.get("cash", 0)) + GO_BONUS
        events.append(f"过起点 +{GO_BONUS}")
    tile = tiles[pos]
    kind = tile.props.get("kind")
    owner = str(tile.props.get("owner") or "")
    if kind == "street" and owner and owner != s.id:
        rent = int(tile.props.get("rent", 0)) * (1 + int(tile.props.get("houses", 0)))
        s.props["cash"] = int(s.props.get("cash", 0)) - rent
        o = reg.entries.get(owner)
        if o is not None:
            o.props["cash"] = int(o.props.get("cash", 0)) + rent
            _save(root, reg, o)
        events.append(f"付 {reg.entries[owner].props.get('name', owner) if owner in reg.entries else owner} 租金 {rent}")
    elif kind == "street" and not owner:
        events.append(f"无主,售价 {tile.props.get('price')}(可 buy)")
    elif kind == "street":
        events.append("自家地,歇脚")
    elif kind == "tax":
        tax = int(tile.props.get("rent", 0))
        s.props["cash"] = int(s.props.get("cash", 0)) - tax
        events.append(f"交税 {tax}")
    elif kind == "chance":
        text, delta = CHANCE[rng.randrange(len(CHANCE))]
        s.props["cash"] = int(s.props.get("cash", 0)) + delta
        events.append(f"机会卡「{text}」{delta:+d}")
    elif kind == "go":
        events.append("正好停在起点")
    else:
        events.append("休息一回合")
    s.props["pos"] = pos
    broke = False
    if int(s.props.get("cash", 0)) < 0:
        s.props["alive"] = False
        broke = True
        for tl in tiles:  # properties go back to the bank
            if tl.props.get("owner") == s.id:
                tl.props["owner"] = ""
                tl.props["houses"] = 0
                _save(root, reg, tl)
        events.append("现金见负,破产出局")
    _save(root, reg, s)
    event = ";".join(events)
    last = f"{s.props.get('name')} 掷 {a}+{b} 到 {tile.props.get('name')}:{event}"
    _sync_table(root, reg, last=last)
    return {"who_name": s.props.get("name"), "dice": f"{a}+{b}", "landed": tile.id, "landed_name": tile.props.get("name"),
            "event": event, "cash": s.props.get("cash"), "broke": broke}


def judge_buy(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    t = _read(_table_path(root))
    s = _seat(reg, op.get("who", ""))
    if s is None:
        return Verdict(False, reason=f"{op.get('who')!r} is not a seat")
    if s.id != t.get("turn_of"):
        return Verdict(False, reason=f"it is {t.get('turn_of')}'s turn: {s.id} cannot buy", allowed=[str(t.get("turn_of"))])
    tiles = _tiles(reg)
    here = tiles[int(s.props.get("pos", 0))] if tiles else None
    want = reg.resolve(str(op.get("tile") or ""), cls="tile") or (here.id if here else None)
    tile = reg.entries.get(want or "")
    if tile is None or tile.cls != "tile":
        return Verdict(False, reason=f"no such tile {op.get('tile')!r}")
    if here is None or tile.id != here.id:
        return Verdict(False, reason=f"{s.props.get('name')} stands on {here.props.get('name') if here else '?'}: only the tile underfoot can be bought", allowed=[here.id] if here else [])
    if tile.props.get("kind") != "street":
        return Verdict(False, reason=f"{tile.props.get('name')} is not for sale")
    if tile.props.get("owner"):
        return Verdict(False, reason=f"{tile.props.get('name')} already belongs to {tile.props.get('owner')}")
    if int(s.props.get("cash", 0)) < int(tile.props.get("price", 0)):
        return Verdict(False, reason=f"cash {s.props.get('cash')} is not enough for {tile.props.get('name')} (price {tile.props.get('price')})")
    return Verdict(True, data={"who": s.id, "tile": tile.id})


def buy(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    s, tile = reg.entries[op["who"]], reg.entries[op["tile"]]
    s.props["cash"] = int(s.props.get("cash", 0)) - int(tile.props.get("price", 0))
    tile.props["owner"] = s.id
    _save(root, reg, s)
    _save(root, reg, tile)
    return {"paid": tile.props.get("price"), "cash": s.props.get("cash"), "tile_name": tile.props.get("name")}


def endturn(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    t = _read(_table_path(root))
    seats = sorted(reg.of_class("seat"), key=lambda e: e.id)
    ids = [s.id for s in seats]
    cur = str(t.get("turn_of") or (ids[0] if ids else ""))
    i = ids.index(cur) if cur in ids else -1
    rnd = int(t.get("round", 1))
    nxt = cur
    for k in range(1, len(ids) + 1):
        j = (i + k) % len(ids)
        if j <= i:
            rnd_candidate = rnd + 1
        else:
            rnd_candidate = rnd
        if seats[j].props.get("alive", True):
            nxt, rnd = ids[j], rnd_candidate
            break
    tt = _sync_table(root, reg, turn_of=nxt, round=rnd)
    return {"next": nxt, "next_name": reg.entries[nxt].props.get("name") if nxt in reg.entries else nxt, "round": tt.get("round")}


# ── mechanics ────────────────────────────────────────────────────────────────

_TABLE = "monopoly"

def _G(lang: str) -> dict[str, Any]:
    from neonrp import prompts

    return prompts.strings(_TABLE, lang)


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def contract(root: Path, reg: Any, structured: str = "together") -> str:
    from neonrp.core.adv import assemble
    from neonrp.core.output_lang import prompt_lang
    from neonrp.packs import resolve as _resolve_pack

    t = _read(_table_path(root))
    who = reg.entries.get(str(t.get("turn_of") or ""))
    lang = prompt_lang(root)
    rules = _f(_G(lang)["rules"], round=t.get('round', 1), who=who.props.get('name') if who else '?', turn_of=t.get('turn_of'),
               last=t.get('last') or '—')
    return assemble(root, reg, rules=rules, lang=lang, blocks=tuple(_resolve_pack(root).blocks))


def observe(root: Path, iid: str) -> str:
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    t = _read(_table_path(root))
    from neonrp.core.output_lang import prompt_lang

    G = _G(prompt_lang(root))
    return _f(G["observe"], round=t.get('round', 1), turn_of=t.get('turn_of'), iid=iid) + "\n".join(
        _f(G["seat"], id=s.id, name=s.props.get('name'), cash=s.props.get('cash'), pos=s.props.get('pos')) + ("" if s.props.get("alive", True) else G["broke"]) for s in reg.of_class("seat"))


def everyone(root: Path, reg: Any, iid: str) -> bool:
    return True


def _pack():
    from neonrp.packs import Pack

    return Pack("monopoly", dict(CLASSES), list(ACTIONS), dict(VARIABLES), dict(TRIGGERS), dict(MECHANICS), "",
                "大富翁:环形棋盘、掷骰与结算是引擎流程、庄家 LLM 只解说和替 AI 座位决定、结局是规则。", "builtin")


PACK = _pack()
# the agent loop (Pack.loop, 09-30): this template only exists on the five-phase loop — its ops, validators
# and ending triggers land through sdk.apply, which v2b never calls
PACK.loop = {"turn": {"mode": "v3"}}


def scaffold(root: Path, *, seats: list[tuple[str, str, int]] | None = None, seed: int = 7) -> None:
    """A small 12-tile ring + seats, for tests and the testbed."""
    board = [("起点", "go", 0, 0), ("老街", "street", 60, 30), ("机会", "chance", 0, 0), ("码头", "street", 80, 40),
             ("税关", "tax", 0, 40), ("茶楼", "street", 100, 50), ("休息", "rest", 0, 0), ("书院", "street", 100, 50),
             ("机会", "chance", 0, 0), ("绸缎庄", "street", 120, 60), ("税关", "tax", 0, 40), ("钱庄", "street", 140, 70)]
    for i, (name, kind, price, rent) in enumerate(board):
        _write(root / "game" / "board" / f"B{i + 1:02d}.json", {"id": f"B{i + 1:02d}", "class": "tile", "props": {"name": name, "kind": kind, "price": price, "rent": rent, "owner": "", "houses": 0}})
    seats = seats or [("S01", "阿明", 150), ("S02", "阿花", 150), ("S03", "老钱", 150)]  # S01 = the human; "玩家" would collide with the player entity's alias
    for sid, name, cash in seats:
        _write(root / "game" / "seats" / f"{sid}.json", {"id": sid, "class": "seat", "props": {"name": name, "cash": cash, "pos": 0, "alive": True}})
    _write(root / "manifest.json", {"template": "monopoly", "name": "石津大富翁"})
    _write(root / "game" / "meta" / "table.json", {"turn_of": seats[0][0], "round": 1, "alive": len(seats), "seed": seed, "n": len(board), "last": ""})
