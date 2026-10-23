"""factions — social organizations: power / wealth / relations, rumors, quests, strikes
(ported from the 3.0 mock's FAC, now engine rules).

World data (``game/world/factions.json``; without it the mixin stays inert)::

    {"factions":  {"guild": {"name": "石津公会", "seat": "T001/guild", "town": "T001", "power": 55, "wealth": 320,
                             "rep_var": "reputation.guild_T001"}, "bandits": {…, "role": "bandits"}, "guard": {…, "role": "guard"},
                   "miners": {…, "role": "labor"}},
     "relations": {"guild.guard": 6, "guild.bandits": -6},
     "rumors":    [{"text": "北路又见着独眼虎的人了", "origin": "T001", "heat": 3, "tags": ["bandit"]}],
     "premiums":  [{"tag": "bandit", "town": "T001", "goods": ["jade", "tools"], "per_heat": 0.05}],
     "routes":    [["T001", "T004"]],                       # where rumors travel (defaults to economy routes)
     "strike":    {"faction": "miners", "town": "T004", "good": "jade", "below": 42, "turns": 3, "lasts": 4},
     "bounty":    {"giver": "guild", "above": 54, "done_below": 40, "reward_gold": 20}}

Closed schema: ``faction.<k>.power|wealth`` (``game/factions/<k>.json``) · ``rep.<k>`` · ``rel.<a>.<b>``.
Open schema: ``faction`` · ``rumor`` (``game/rumors``) · ``quest`` (``game/quests``). Roles pick the rules:
``bandits`` rob / raid / recruit, ``guard`` patrols, ``labor`` strikes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp import prompts
from neonrp.core.handlers import Verdict
from neonrp.core.paths import get_data_dir_name
from neonrp.packs.mixins import new_entry, next_id, patch_entry, read, register_vars, rng, set_var, vint, world_data, write

M = "neonrp.packs.mixins.factions"

MIXIN: dict[str, Any] = {
    "classes": {
        "faction": {"folder": "game/factions", "scope": "world", "tier": 1, "required": ["name"],
                    "render": prompts.by_lang("factions", "faction_render")},
        "rumor": {"folder": "game/rumors", "scope": "world", "tier": 2, "id_prefix": "R", "required": ["text"],
                  "render": prompts.by_lang("factions", "rumor_render"),
                  "props": {"heat": {"type": "int", "min": 0, "max": 9}}},
        "quest": {"folder": "game/quests", "scope": "world", "tier": 1, "id_prefix": "Q", "required": ["title"],
                  "render": prompts.by_lang("factions", "quest_render"),
                  "props": {"status": {"type": "enum", "values": ["open", "taken", "done", "failed", "expired"]}}},
    },
    "actions": {  # docs: prompts/factions.<lang>.json (the model reads them each turn, in the run's language)
        "take_quest": {"kind": "action", "handler": f"{M}:take_quest", "validator": f"{M}:judge_take", "fields": ["id"],
                       "doc": prompts.by_lang("factions", "op_take_quest")},
        "rumor": {"kind": "action", "handler": f"{M}:rumor", "fields": ["text", "origin"], "doc": prompts.by_lang("factions", "op_rumor")},
        "spread": {"kind": "action", "handler": f"{M}:spread", "fields": ["id", "town"], "doc": prompts.by_lang("factions", "op_spread")},
        "new_quest": {"kind": "action", "handler": f"{M}:new_quest", "fields": ["kind", "title", "giver"], "doc": prompts.by_lang("factions", "op_new_quest")},
        "quest": {"kind": "action", "handler": f"{M}:quest", "fields": ["id", "to"], "doc": prompts.by_lang("factions", "op_quest")},
        "strike": {"kind": "action", "handler": f"{M}:strike", "fields": ["on"], "doc": prompts.by_lang("factions", "op_strike")},
    },
    "ticks": [f"{M}:tick"],
    "ui": {
        "slots": [{"cls": "faction", "slot": "emblem", "kind": "icon", "required": "optional", "recipe": "emblem"}],
        "prompts": {"emblem": "The emblem of “{inst.name}”: {inst.blurb}. Heraldic style, centred, no text, {style}."},  # an image prompt: English, like the other recipes
        "views": [
            {"id": "factions", "title": {"zh": "势力", "en": "Factions", "ja": "勢力", "ko": "세력"}, "bind": ["faction.*.power", "rep.*"], "widget": "bars", "layout": {"area": "right", "order": 4}},
            {"id": "rumors", "title": {"zh": "传闻", "en": "Rumors", "ja": "噂", "ko": "소문"}, "bind": ["class:rumor"], "widget": "list", "layout": {"area": "right", "order": 6}},
            {"id": "quests", "title": {"zh": "委托", "en": "Quests", "ja": "依頼", "ko": "의뢰"}, "bind": ["class:quest"], "widget": "list", "actions": ["take_quest"], "layout": {"area": "right", "order": 7}},
        ],
    },
    "prompt": {"entries": [{"id": "factions", "when": "always",
                            "text": prompts.by_lang("factions", "line")}]},
}


def data(root: Path) -> dict[str, Any]:
    return world_data(root, "factions")


def _S(root: Path) -> dict[str, Any]:
    """factions strings in the run's language (docs, refusals and the rumors / quests the rules write go to the model and the player)."""
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("factions", prompt_lang(root))


def _state_p(root: Path) -> Path:
    return root / get_data_dir_name(root) / "world" / "factions_state.json"


def _by_role(d: dict[str, Any], role: str) -> str | None:
    return next((k for k, f in (d.get("factions") or {}).items() if f.get("role") == role), None)


def _routes(root: Path, d: dict[str, Any]) -> list[tuple[str, str]]:
    rs = d.get("routes") or world_data(root, "economy").get("routes") or []
    return [(str(r[0]), str(r[1])) for r in rs if len(r) >= 2]


def installed(reg: Any) -> bool:
    return any(n.startswith("faction.") for n in reg.variables)


def install(root: Path) -> list[str]:
    d = data(root)
    facs = d.get("factions") or {}
    if not facs:
        return []
    g = get_data_dir_name(root)
    specs: dict[str, dict[str, Any]] = {}
    S = _S(root)
    for k, f in facs.items():
        fp = root / g / "factions" / f"{k}.json"
        if not fp.exists():
            write(fp, {"id": k, "class": "faction", "parent": f.get("town"), "power": int(f.get("power", 50)), "wealth": int(f.get("wealth", 100)),
                       "props": {"name": f.get("name", k), "blurb": f.get("blurb", ""), "seat": f.get("seat", ""), "role": f.get("role", ""),
                                 "power": int(f.get("power", 50)), "wealth": int(f.get("wealth", 100))}})
        specs[f"faction.{k}.power"] = {"type": "int", "path": f"{g}/factions/{k}.json", "key": "power", "min": 0, "max": 100,
                                       "readonly": True, "doc": S["doc_power"].replace("{name}", str(f.get('name', k)))}
        specs[f"faction.{k}.wealth"] = {"type": "int", "path": f"{g}/factions/{k}.json", "key": "wealth", "min": 0, "readonly": True,
                                        "doc": S["doc_wealth"].replace("{name}", str(f.get('name', k)))}
        if not f.get("rep_var"):
            specs[f"rep.{k}"] = {"type": "int", "path": f"{g}/player/reputation.json", "key": k, "min": -10, "max": 10, "seed": 0,
                                 "doc": S["doc_rep"].replace("{name}", str(f.get('name', k)))}
    for pair, v in (d.get("relations") or {}).items():
        specs[f"rel.{pair}"] = {"type": "int", "path": f"{g}/world/factions_state.json", "key": f"rel.{pair}", "min": -10, "max": 10,
                                "seed": int(v), "readonly": True, "doc": S["doc_rel"].replace("{pair}", pair.replace('.', ' ↔ '))}
    added = register_vars(root, specs)
    st = read(_state_p(root))
    if not st.get("seeded"):
        for i, r in enumerate(d.get("rumors") or [], 1):
            rid = f"R{i:03d}"
            write(root / g / "rumors" / f"{rid}.json", {"id": rid, "class": "rumor", "parent": None,
                                                        "props": {"name": r["text"][:12], "text": r["text"], "origin": r.get("origin", ""),
                                                                  "heat": int(r.get("heat", 2)), "tags": list(r.get("tags") or []),
                                                                  "towns": [r.get("origin", "")], "towns_text": r.get("origin", "")}})
        st["seeded"] = True
        write(_state_p(root), st)
    return added


def _sync_props(root: Path, reg: Any, k: str) -> None:
    if k in reg.entries:
        patch_entry(root, reg, k, power=vint(reg, f"faction.{k}.power"), wealth=vint(reg, f"faction.{k}.wealth"))


def premium(root: Path, reg: Any, t: str, g: str) -> float:
    """What rumors heard in town ``t`` add to the price of good ``g`` (economy reads this)."""
    rules = data(root).get("premiums") or []
    if not rules or "rumor" not in reg.classes:
        return 0.0
    p = 0.0
    for r in reg.of_class("rumor"):
        heat = int(r.props.get("heat", 0))
        if heat <= 0 or t not in (r.props.get("towns") or []):
            continue
        for rule in rules:
            if rule.get("tag") in (r.props.get("tags") or []) and rule.get("town", t) == t and g in (rule.get("goods") or []):
                p += float(rule.get("per_heat", 0.04)) * heat
    return min(0.6, p)


# ── ops ──────────────────────────────────────────────────────────────────────

def judge_take(root: Path, reg: Any, op: dict[str, Any]) -> Verdict:
    q = reg.entries.get(str(op.get("id") or ""))
    open_q = [e.id for e in reg.of_class("quest") if e.props.get("status") == "open"] if "quest" in reg.classes else []
    if q is None or q.cls != "quest":
        return Verdict(False, reason=_S(root)["no_quest"], allowed=open_q)
    if q.props.get("status") != "open":
        return Verdict(False, reason=_S(root)["quest_closed"], allowed=open_q, fixable=False)
    seat = str(q.props.get("seat") or "")
    if seat and reg.player_location != seat:
        return Verdict(False, reason=_S(root)["go_take"].replace("{giver}", str(q.props.get('giver_name', ''))).replace("{seat}", seat), allowed=[seat])
    return Verdict(True, data={"id": q.id})


def take_quest(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    patch_entry(root, reg, op["id"], status="taken", taken_turn=res.turn)
    return {"status": "taken"}


def rumor(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any] | bool:
    if any(r.props.get("text") == op["text"] and int(r.props.get("heat", 0)) > 0 for r in reg.of_class("rumor")):
        return False
    rid = next_id(reg, "R")
    origin = str(op.get("origin") or "")
    new_entry(root, reg, "rumor", rid, {"name": str(op["text"])[:12], "text": op["text"], "origin": origin, "heat": int(op.get("heat", 3)),
                                        "tags": list(op.get("tags") or []), "towns": [origin], "towns_text": origin},
              turn=res.turn, by="tick:factions")
    res.created.append({"op": "rumor", "class": "rumor", "id": rid, "name": str(op["text"])[:12]})
    return {"id": rid}


def spread(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any] | bool:
    r = reg.entries.get(op["id"])
    if r is None or op["town"] in (r.props.get("towns") or []):
        return False
    towns = list(r.props.get("towns") or []) + [op["town"]]
    patch_entry(root, reg, r.id, towns=towns, towns_text=_S(root)["towns_sep"].join(towns))
    return {"towns": towns}


def new_quest(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any] | bool:
    if any(q.props.get("kind") == op["kind"] and q.props.get("status") in ("open", "taken") for q in reg.of_class("quest")):
        return False
    f = (data(root).get("factions") or {}).get(op["giver"], {})
    qid = next_id(reg, "Q")
    new_entry(root, reg, "quest", qid, {"name": op["title"], "title": op["title"], "kind": op["kind"], "giver": op["giver"],
                                        "giver_name": f.get("name", op["giver"]), "seat": f.get("seat", ""),
                                        "reward_gold": int(op.get("reward_gold", 0)), "status": "open"},
              parent=f.get("seat") or None, turn=res.turn, by="tick:factions")
    res.created.append({"op": "new_quest", "class": "quest", "id": qid, "name": op["title"]})
    return {"id": qid}


def quest(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    q = reg.entries[op["id"]]
    patch_entry(root, reg, q.id, status=op["to"])
    if op["to"] == "done" and q.props.get("reward_gold") and "player.gold" in reg.variables:
        set_var(root, reg, "player.gold", vint(reg, "player.gold") + int(q.props["reward_gold"]))
    return {"status": op["to"]}


def strike(root: Path, reg: Any, op: dict[str, Any], res: Any) -> dict[str, Any]:
    st = read(_state_p(root))
    on = bool(op.get("on"))
    st["strike"] = int((data(root).get("strike") or {}).get("lasts", 4)) if on else 0
    write(_state_p(root), st)
    return {"strike": on}


# ── tick ─────────────────────────────────────────────────────────────────────

def tick(root: Path, reg: Any, *, turn: int, res: Any) -> list[dict[str, Any]]:
    d = data(root)
    if not d.get("factions"):
        return []
    if not installed(reg):
        install(root)
        return []
    for k in d["factions"]:
        _sync_props(root, reg, k)  # the entries show last turn's numbers
    ops: list[dict[str, Any]] = []
    st = read(_state_p(root))
    bandits, guard, labor = _by_role(d, "bandits"), _by_role(d, "guard"), _by_role(d, "labor")
    bp = vint(reg, f"faction.{bandits}.power") if bandits else 0
    gp = vint(reg, f"faction.{guard}.power") if guard else 0
    alert = vint(reg, "town.alert")

    def add(var: str, delta: int) -> None:
        if var in reg.variables and delta:
            ops.append({"op": "add", "var": var, "delta": delta})

    def rel(a: str, b: str) -> str:
        return f"rel.{a}.{b}" if f"rel.{a}.{b}" in reg.variables else f"rel.{b}.{a}"

    # rumors: travel along routes by heat, cool down every 4 turns
    routes = _routes(root, d)
    for r in reg.of_class("rumor") if "rumor" in reg.classes else []:
        heat = int(r.props.get("heat", 0))
        if heat <= 0:
            continue
        towns = set(r.props.get("towns") or [])
        for a, b in routes:
            for fr, to in ((a, b), (b, a)):
                if fr in towns and to not in towns and rng(turn, "spread", r.id, to).random() < 0.12 * heat:
                    ops.append({"op": "spread", "id": r.id, "town": to})
                    towns.add(to)
        if turn and turn % 4 == 0:
            ops.append({"op": "patch_rumor", "id": r.id, "heat": heat - 1})
    # guard patrols when the alert is up or bandits are strong
    if guard and bandits and turn and turn % 3 == 0 and (alert >= 2 or bp > 55):
        hit = rng(turn, "patrol").random() < gp / max(1, gp + bp)
        add(f"faction.{guard}.wealth", -20)
        add(f"faction.{bandits}.power", -5 if hit else -1)
        add(f"faction.{guard}.power", 1 if hit else -1)
        add(rel(guard, bandits), -1)
        add("town.alert", -1 if alert > 0 else 0)
    # bandits recruit with loot, raid when they out-muscle the guard
    if bandits:
        if vint(reg, f"faction.{bandits}.wealth") >= 80 and bp < 80:
            add(f"faction.{bandits}.wealth", -60)
            add(f"faction.{bandits}.power", 2)
        if guard and bp > gp + 8 and rng(turn, "raid").random() < 0.2:
            sk = d.get("strike") or {}
            target = f"stock.{sk.get('town', '')}.{sk.get('good', '')}"
            if target in reg.variables:
                add(target, -min(6, vint(reg, target)))
            add(f"faction.{bandits}.wealth", 40)
            ops.append({"op": "rumor", "text": _S(root)["raid"].replace("{name}", str(d['factions'][bandits].get('name', bandits))).replace("{town}", str(sk.get('town', ''))),
                        "origin": sk.get("town", ""), "heat": 4, "tags": ["bandit"]})
    # bounty: posted when bandits grow, paid when they shrink
    bo = d.get("bounty") or {}
    if bandits and bo:
        quests = reg.of_class("quest") if "quest" in reg.classes else []
        live = [q for q in quests if q.props.get("kind") == "bounty" and q.props.get("status") in ("open", "taken")]
        if bp >= int(bo.get("above", 54)) and not live:
            ops.append({"op": "new_quest", "kind": "bounty", "title": _S(root)["bounty"].replace("{name}", str(d['factions'][bandits].get('name', bandits))),
                        "giver": bo.get("giver", "guild"), "reward_gold": int(bo.get("reward_gold", 20))})
        for q in live:
            if q.props.get("status") == "taken" and bp < int(bo.get("done_below", 40)):
                ops.append({"op": "quest", "id": q.id, "to": "done"})
                giver = str(q.props.get("giver") or "")
                rv = (d["factions"].get(giver) or {}).get("rep_var") or f"rep.{giver}"
                add(rv, 2)
    # labor strikes when their good stays cheap
    sk = d.get("strike") or {}
    if labor and sk:
        pv = f"price.{sk.get('town')}.{sk.get('good')}"
        if int(st.get("strike", 0)) > 0:
            if int(st["strike"]) == 1:
                ops.append({"op": "strike", "on": False})
            else:
                st["strike"] = int(st["strike"]) - 1
        elif pv in reg.variables:
            st["low"] = int(st.get("low", 0)) + 1 if vint(reg, pv) < int(sk.get("below", 42)) else 0
            if st["low"] >= int(sk.get("turns", 3)):
                st["low"] = 0
                ops.append({"op": "strike", "on": True})
                add(rel(str(bo.get("giver", "guild")), labor), -2)
                ops.append({"op": "rumor", "text": _S(root)["strike"].replace("{name}", str(d['factions'][labor].get('name', labor))), "origin": sk.get("town", ""),
                            "heat": 4, "tags": ["strike"]})
    # a rumor already hot is not born twice (the op would only be refused)
    hot = {str(r.props.get("text")) for r in reg.of_class("rumor") if int(r.props.get("heat", 0)) > 0} if "rumor" in reg.classes else set()
    ops = [o for o in ops if not (o["op"] == "rumor" and o["text"] in hot)]
    # slow recovery
    if turn and turn % 8 == 0:
        if guard and gp < 50:
            add(f"faction.{guard}.power", 1)
        if bandits and bp < 60:
            add(f"faction.{bandits}.power", 1)
    write(_state_p(root), st)
    # rumor cooling is bookkeeping, not an op the model knows: land it here
    out = []
    for o in ops:
        if o["op"] == "patch_rumor":
            patch_entry(root, reg, o["id"], heat=max(0, int(o["heat"])))
        else:
            out.append(o)
    return out


# O7 (10-06): what this background unit may write
tick.unit = {"on": "apply", "llm": False,  # type: ignore[attr-defined]
             "writes": ["var:faction.*", "var:rel.*", "op:spread", "op:patch_rumor"]}
