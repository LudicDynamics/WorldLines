"""economy — markets, prices, caravans, trade (ported from the 3.0 mock's ECON, now engine rules).

World data (``game/world/economy.json``; without it the mixin stays inert)::

    {"currency": {"gold": 100, "silver": 10, "copper": 1},
     "goods":   {"grain": {"name": "粮", "unit": "斗", "base": 12}, …},
     "markets": {"T001": {"stock": {…}, "target": {…}, "prod": {"fish": 3.2}, "cons": {"grain": 1.8}}, …},
     "routes":  [["T001", "T004", 3]],          # a b travel-turns
     "caravan_every": 6}

Closed schema (installed as overlays, seeded once): ``stock.<T>.<g>`` · ``price.<T>.<g>`` (in
``game/towns/<T>/market.json``) · ``inv.<g>`` (``game/player/goods.json``) · ``econ.index``.
Open schema: class ``caravan`` (``game/caravans``) — instances keep appearing as the world runs.

Rules each apply (tick, 0 token): production − consumption (fractions carried) → prices
``base × clamp((target/stock)^0.55, .45, 3.2) × (1 + rumor premium)`` → caravans leave where the spread
> 35 % → caravans move, get robbed (if ``factions`` runs) or deliver. ``trade`` is the player's op.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp import prompts
from neonrp.core.handlers import Verdict
from neonrp.core.paths import get_data_dir_name
from neonrp.packs.mixins import (
    dget, new_entry, next_id, patch_entry, read, register_vars, rng, set_var, town_of, vint, world_data, write,
)

M = "neonrp.packs.mixins.economy"
SELL_RATE = 0.85  # a merchant buys at 85 %

MIXIN: dict[str, Any] = {
    "classes": {
        "caravan": {"folder": "game/caravans", "scope": "world", "tier": 2, "id_prefix": "C", "required": ["name"],
                    "render": prompts.by_lang("economy", "caravan_render"),
                    "props": {"status": {"type": "enum", "values": ["road", "delivered", "robbed"]},
                              "qty": {"type": "int", "min": 0}, "left": {"type": "int", "min": 0}},
                    "mutable": []},
    },
    "actions": {  # docs: prompts/economy.<lang>.json (the model reads them each turn, in the run's language)
        "trade": {"kind": "action", "handler": f"{M}:trade", "validator": f"{M}:judge_trade", "fields": ["good", "qty"],
                  "doc": prompts.by_lang("economy", "op_trade")},
        "new_caravan": {"kind": "action", "handler": f"{M}:new_caravan", "fields": ["from", "to", "good", "qty"],
                        "doc": prompts.by_lang("economy", "op_new_caravan")},
        "haul": {"kind": "action", "handler": f"{M}:haul", "fields": ["cv"], "doc": prompts.by_lang("economy", "op_haul")},
        "deliver": {"kind": "action", "handler": f"{M}:deliver", "fields": ["cv"], "doc": prompts.by_lang("economy", "op_deliver")},
        "rob": {"kind": "action", "handler": f"{M}:rob", "fields": ["cv"], "doc": prompts.by_lang("economy", "op_rob")},
    },
    "ticks": [f"{M}:tick"],
    "ui": {
        "slots": [{"cls": "caravan", "slot": "icon", "kind": "icon", "scope": "class", "required": "optional", "recipe": "caravan_icon"}],
        "prompts": {"caravan_icon": "A laden horse-drawn merchant caravan, a small side-view icon, {style}."},
        "views": [
            {"id": "market", "title": {"zh": "集市", "en": "Market", "ja": "市場", "ko": "시장"}, "bind": ["price.{town}.*", "stock.{town}.*", "inv.*"], "widget": "table", "actions": ["trade"],
             "layout": {"area": "right", "order": 3, "cols": 4}},
            {"id": "econ", "title": {"zh": "物价指数", "en": "Price index", "ja": "物価指数", "ko": "물가 지수"}, "bind": ["econ.index"], "widget": "sparkline", "layout": {"area": "studio", "order": 1}},
            {"id": "caravans", "title": {"zh": "商队", "en": "Caravans", "ja": "隊商", "ko": "상단"}, "bind": ["class:caravan"], "widget": "list", "layout": {"area": "right", "order": 5}},
        ],
    },
    "prompt": {"entries": [{"id": "economy", "when": "always", "text": prompts.by_lang("economy", "market_line")}]},
}


# ── install ──────────────────────────────────────────────────────────────────

def data(root: Path) -> dict[str, Any]:
    return world_data(root, "economy")


def _state_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "world" / "economy_state.json"


def install(root: Path) -> list[str]:
    d = data(root)
    goods, markets = d.get("goods") or {}, d.get("markets") or {}
    if not goods or not markets:
        return []
    from neonrp.core.output_lang import prompt_lang

    S = prompts.strings("economy", prompt_lang(root))  # the docs go to the model each turn: the run's language
    specs: dict[str, dict[str, Any]] = {}
    for t, m in markets.items():
        mp = f"{get_data_dir_name(root)}/towns/{t}/market.json"
        for g, gd in goods.items():
            s0 = int((m.get("stock") or {}).get(g, 0))
            specs[f"stock.{t}.{g}"] = {"type": "int", "path": mp, "key": f"stock.{g}", "min": 0, "readonly": True, "seed": s0,
                                      "doc": S["doc_stock"].format(town=t, good=gd.get("name", g))}
            specs[f"price.{t}.{g}"] = {"type": "int", "path": mp, "key": f"price.{g}", "min": 1, "max": 9999, "readonly": True,
                                      "seed": price(d, t, g, s0, 0.0), "doc": S["doc_price"].format(town=t, good=gd.get("name", g))}
    for g, gd in goods.items():
        specs[f"inv.{g}"] = {"type": "int", "path": f"{get_data_dir_name(root)}/player/goods.json", "key": g, "min": 0, "readonly": True,
                             "seed": 0, "doc": S["doc_inv"].format(good=gd.get("name", g), unit=gd.get("unit", ""))}
    specs["econ.index"] = {"type": "int", "path": f"{get_data_dir_name(root)}/world/economy_state.json", "key": "index",
                           "min": 0, "readonly": True, "seed": 100, "doc": S["doc_index"]}
    return register_vars(root, specs)


def installed(reg: Any) -> bool:
    return "econ.index" in reg.variables


# ── rules ────────────────────────────────────────────────────────────────────

def price(d: dict[str, Any], t: str, g: str, stock: int, premium: float) -> int:
    m, gd = d["markets"][t], d["goods"][g]
    s = max(1, int(stock))
    f = (float((m.get("target") or {}).get(g, s)) / s) ** 0.55
    f = max(0.45, min(3.2, f)) * (1 + premium)
    return max(1, round(float(gd.get("base", 1)) * f))


def _premium(root: Path, reg: Any, t: str, g: str) -> float:
    try:
        from neonrp.packs.mixins import factions

        return factions.premium(root, reg, t, g)
    except Exception:  # noqa: BLE001 — no factions mixin → no rumor premium
        return 0.0


def _coin(reg: Any, cur: dict[str, int]) -> int:
    return sum(vint(reg, f"player.{k}") * int(v) for k, v in cur.items() if f"player.{k}" in reg.variables)


def _pay(root: Path, reg: Any, cur: dict[str, int], total: int) -> None:
    """Set the wallet to ``total`` copper in the largest coins first."""
    for k, v in sorted(cur.items(), key=lambda kv: -int(kv[1])):
        if f"player.{k}" in reg.variables:
            n, total = divmod(total, int(v))
            set_var(root, reg, f"player.{k}", n)


def _fill(t: str, **kw: Any) -> str:
    for k, v in kw.items():
        t = t.replace("{" + k + "}", str(v))
    return t


def judge_trade(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    d = data(root)
    from neonrp.core.output_lang import prompt_lang

    S = prompts.strings("economy", prompt_lang(root))  # a refusal of the player's trade is shown to them: the run's language (10-16)
    f = lambda k, **kw: _fill(S["rf_" + k], **kw)  # noqa: E731
    if not installed(reg):
        return Verdict(False, reason=f("no_market"), fixable=False)
    t = town_of(reg, reg.player_location)
    g = str(op.get("good") or "")
    if t not in (d.get("markets") or {}):
        return Verdict(False, reason=f("not_at_market"), allowed=sorted(d.get("markets") or {}))
    if g not in d.get("goods", {}):
        names = {v.get("name"): k for k, v in d["goods"].items()}
        g = names.get(g, "")
        if not g:
            return Verdict(False, reason=f("no_good", good=repr(op.get('good'))), allowed=sorted(d["goods"]))
    try:
        qty = int(op.get("qty") or 0)
    except (TypeError, ValueError):
        qty = 0
    if not qty:
        return Verdict(False, reason=f("qty_zero"), scope="field", field="qty")
    p, stock, have = vint(reg, f"price.{t}.{g}"), vint(reg, f"stock.{t}.{g}"), vint(reg, f"inv.{g}")
    cur = d.get("currency") or {"gold": 100, "silver": 10, "copper": 1}
    gd = d["goods"][g]
    if qty > 0 and stock < qty:
        return Verdict(False, reason=f("stock_low", name=gd.get('name', g), stock=stock, unit=gd.get('unit', '')), scope="field", field="qty")
    if qty > 0 and _coin(reg, cur) < p * qty:
        return Verdict(False, reason=f("no_money", need=p * qty, have=_coin(reg, cur)), scope="field", field="qty")
    if qty < 0 and have < -qty:
        return Verdict(False, reason=f("have_only", have=have, unit=gd.get('unit', ''), name=gd.get('name', g)), scope="field", field="qty")
    return Verdict(True, data={"good": g, "qty": qty, "town": t})


def trade(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    d = data(root)
    cur = d.get("currency") or {"gold": 100, "silver": 10, "copper": 1}
    t, g, qty = op.get("town") or town_of(reg, reg.player_location), str(op["good"]), int(op["qty"])
    p = vint(reg, f"price.{t}.{g}")
    unit = p if qty > 0 else int(p * SELL_RATE)
    total = unit * abs(qty)
    _pay(root, reg, cur, _coin(reg, cur) + (-total if qty > 0 else total))
    set_var(root, reg, f"stock.{t}.{g}", vint(reg, f"stock.{t}.{g}") - qty)
    set_var(root, reg, f"inv.{g}", vint(reg, f"inv.{g}") + qty)
    st = read(_state_path(root))
    st["volume"] = int(st.get("volume", 0)) + total
    write(_state_path(root), st)
    return {"town": t, "unit": unit, "total": total, "side": "buy" if qty > 0 else "sell"}


def new_caravan(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    d = data(root)
    g, qty, fr, to = str(op["good"]), int(op["qty"]), str(op["from"]), str(op["to"])
    set_var(root, reg, f"stock.{fr}.{g}", vint(reg, f"stock.{fr}.{g}") - qty)
    eid = next_id(reg, "C")
    gd = d["goods"][g]
    new_entry(root, reg, "caravan", eid, {"name": f"{op.get('owner_name') or ''}商队 {eid}", "from": fr, "to": to, "good": g,
                                          "good_name": gd.get("name", g), "unit": gd.get("unit", ""), "qty": qty,
                                          "buy": vint(reg, f"price.{fr}.{g}"), "owner": op.get("owner") or "",
                                          "status": "road", "left": int(op.get("eta") or 3), "eta": int(op.get("eta") or 3)},
              parent=None, turn=res.turn, by="tick:economy")
    res.created.append({"op": "new_caravan", "class": "caravan", "id": eid, "name": eid})
    return {"cv": eid}


def haul(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    e = reg.entries[op["cv"]]
    left = max(0, int(e.props.get("left", 1)) - 1)
    patch_entry(root, reg, e.id, left=left)
    return {"left": left}


def deliver(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    e = reg.entries[op["cv"]]
    to, g, qty = e.props["to"], e.props["good"], int(e.props["qty"])
    set_var(root, reg, f"stock.{to}.{g}", vint(reg, f"stock.{to}.{g}") + qty)
    patch_entry(root, reg, e.id, status="delivered", left=0)
    profit = max(0, round((vint(reg, f"price.{to}.{g}") - int(e.props.get("buy", 0))) * qty * 0.2))
    patron = f"faction.{e.props.get('owner') or 'guild'}.wealth"
    if profit and patron in reg.variables:  # the guild lives on the cut
        set_var(root, reg, patron, vint(reg, patron) + profit)
    st = read(_state_path(root))
    st["delivered"] = int(st.get("delivered", 0)) + 1
    write(_state_path(root), st)
    return {"to": to, "good": g, "qty": qty}


def rob(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    e = reg.entries[op["cv"]]
    patch_entry(root, reg, e.id, status="robbed")
    st = read(_state_path(root))
    st["robbed"] = int(st.get("robbed", 0)) + 1
    write(_state_path(root), st)
    if "faction.bandits.wealth" in reg.variables:
        set_var(root, reg, "faction.bandits.wealth", vint(reg, "faction.bandits.wealth") + int(e.props.get("qty", 0)) * 4)
    return {"qty": e.props.get("qty")}


def tick(root: Path, reg: Any, *, turn: int, res: Any) -> list[dict[str, Any]]:
    d = data(root)
    if not d.get("markets"):
        return []
    if not installed(reg):
        install(root)  # the variables exist from the next load on
        return []
    ops: list[dict[str, Any]] = []
    goods, markets = d["goods"], d["markets"]
    st = read(_state_path(root))
    acc = dict(st.get("acc") or {})
    strike = bool(dget(read(root / get_data_dir_name(root) / "world" / "factions_state.json"), "strike", 0))
    after: dict[str, int] = {}
    # 1) production − consumption (fractions carried until whole)
    for t, m in markets.items():
        for g in goods:
            prod = float((m.get("prod") or {}).get(g, 0))
            if strike and g == (d.get("strike_good") or "jade") and t == (d.get("strike_town") or ""):
                prod = 0.0
            key = f"{t}.{g}"
            acc[key] = acc.get(key, 0.0) + prod - float((m.get("cons") or {}).get(g, 0))
            n = int(acc[key])  # toward zero
            cur = vint(reg, f"stock.{t}.{g}")
            real = max(-cur, n)
            acc[key] -= n
            if real:
                ops.append({"op": "add", "var": f"stock.{t}.{g}", "delta": real})
            after[key] = cur + real
    st["acc"] = {k: round(v, 3) for k, v in acc.items()}
    # 2) prices follow stock and rumors; the index is their mean over base
    idx_sum, n = 0.0, 0
    for t in markets:
        for g, gd in goods.items():
            p = price(d, t, g, after[f"{t}.{g}"], _premium(root, reg, t, g))
            if p != vint(reg, f"price.{t}.{g}"):
                ops.append({"op": "set", "var": f"price.{t}.{g}", "value": p})
            idx_sum += p / float(gd.get("base", 1))
            n += 1
    idx = round(idx_sum / max(1, n) * 100)
    if idx != vint(reg, "econ.index"):
        ops.append({"op": "set", "var": "econ.index", "value": idx})
    # 3) caravans on the road: robbed / move / arrive
    fac = "faction.bandits.power" in reg.variables
    for e in reg.of_class("caravan") if "caravan" in reg.classes else []:
        if e.props.get("status") != "road":
            continue
        if fac and not e.props.get("escorted"):
            bp, gp = vint(reg, "faction.bandits.power", 45), vint(reg, "faction.guard.power", 50)
            prob = max(0.0, min(0.4, 0.06 * bp / max(1, gp)))
            if rng(turn, "rob", e.id).random() < prob:
                ops.append({"op": "rob", "cv": e.id})
                if "town.alert" in reg.variables:
                    ops.append({"op": "add", "var": "town.alert", "delta": 1})
                if "faction.bandits.power" in reg.variables:
                    ops.append({"op": "add", "var": "faction.bandits.power", "delta": 2})
                if "rumor" in reg.actions:
                    ops.append({"op": "rumor", "text": f"{e.props.get('name', e.id)}在路上被劫了", "origin": e.props.get("from", ""),
                                "heat": 4, "tags": ["bandit"]})
                continue
        if int(e.props.get("left", 1)) <= 1:
            ops.append({"op": "deliver", "cv": e.id})
        else:
            ops.append({"op": "haul", "cv": e.id})
    # 4) new caravans where the spread is worth it
    every = int(d.get("caravan_every") or 6)
    if turn and turn % every == 0:
        for a, b, *eta in d.get("routes") or []:
            for fr, to in ((a, b), (b, a)):
                if fr not in markets or to not in markets:
                    continue
                best = None
                for g in goods:
                    pf, pt, s = vint(reg, f"price.{fr}.{g}"), vint(reg, f"price.{to}.{g}"), after[f"{fr}.{g}"]
                    spread = (pt - pf) / max(1, pf)
                    if spread > 0.35 and s > float((markets[fr].get("target") or {}).get(g, 0)) * 0.5 and (best is None or spread > best[1]):
                        best = (g, spread)
                if best:
                    qty = max(1, min(after[f"{fr}.{best[0]}"] // 3, 20))
                    ops.append({"op": "new_caravan", "from": fr, "to": to, "good": best[0], "qty": qty, "eta": int(eta[0]) if eta else 3,
                                "why": f"{goods[best[0]].get('name')}差价 {round(best[1] * 100)}%"})
    write(_state_path(root), st)
    return [o for o in ops if o.get("op") != "noop"]


# O7 (10-06): what this background unit may write — the orchestration graph lists it, lint checks overlaps, apply refuses
# anything outside it
tick.unit = {"on": "apply", "llm": False,  # type: ignore[attr-defined]
             "writes": ["var:stock.*", "var:price.*", "var:econ.index", "op:new_caravan", "op:haul", "op:deliver", "op:rob"]}
