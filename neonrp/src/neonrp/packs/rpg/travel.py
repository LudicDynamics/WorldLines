"""rpg travel — cross-town journeys take days (E5 C4b: both arms teleported; the JSON arm invented
「路走了几天」, the ADV arm arrived the same afternoon). The world map's routes carry a ``distance``; the engine
turns it into days, advances the calendar itself and tells the narrator what happened as an <event>."""
from __future__ import annotations

import json
import math
import re
from collections import deque
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp.core.place_nav import split_location
from neonrp.packs.rpg import data as _data
from neonrp.packs.rpg.i18n import lang_of, t as _t

PER_DAY = 20  # distance units a traveller covers in a day (the rpg pack's number; a world may set world_map.json "travel": {"per_day": …})


def _world_map(root: Path) -> dict[str, Any]:
    try:
        d = json.loads((root / get_data_dir_name(root) / "world" / "world_map.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def route_distance(root: Path, a: str, b: str) -> float | None:
    """Shortest route distance between two world nodes (towns / dungeons), over the map's routes; None if unconnected."""
    wm = _world_map(root)
    adj: dict[str, list[tuple[str, float]]] = {}
    for r in wm.get("routes") or []:
        if not isinstance(r, dict) or (r.get("state") or {}).get("blocked"):
            continue
        f, t, d = str(r.get("from")), str(r.get("to")), float(r.get("distance") or 0)
        adj.setdefault(f, []).append((t, d))
        adj.setdefault(t, []).append((f, d))
    best: dict[str, float] = {a: 0.0}
    q = deque([a])
    while q:  # small graphs: plain relaxation is fine
        x = q.popleft()
        for y, d in adj.get(x, []):
            if best[x] + d < best.get(y, math.inf):
                best[y] = best[x] + d
                q.append(y)
    return best.get(b)


def _hazards(root: Path) -> dict[str, dict[str, Any]]:
    """Route tag → {p, dc, fail_days, text, pass, fail} in the world's language (pack table packs/rpg/data/hazards.json,
    world overrides in game/rules/hazards.json or world_map.json travel.hazards)."""
    lang = lang_of(root)
    out: dict[str, dict[str, Any]] = {}
    for tag, h in _data.table(root, "hazards").items():
        if not isinstance(h, dict):
            continue
        out[tag] = {"p": float(h.get("p") or 0.0), "dc": int(h.get("dc") or 0), "fail_days": int(h.get("fail_days") or 0),
                    "text": _data.pick(h.get("text"), lang), "pass": _data.pick(h.get("pass"), lang), "fail": _data.pick(h.get("fail"), lang)}
    return out


def route_facts(root: Path, a: str, b: str) -> dict[str, Any]:
    """The route between two towns as the world wrote it: kind, distance, tags, note (the first leg on the shortest path)."""
    wm = _world_map(root)
    for r in wm.get("routes") or []:
        if isinstance(r, dict) and {str(r.get("from")), str(r.get("to"))} == {a, b}:
            return r
    return {}


def plan(root: Path, a: str, b: str, *, seed: str) -> dict[str, Any]:
    """The journey a → b as the referee sees it before anyone walks it: days, and the seeded stops (day, hazard).
    Seeded per turn + route: a re-proposal in the same turn sees the same road."""
    import random

    days = route_days(root, a, b) or 0
    r = route_facts(root, a, b)
    haz = _hazards(root)
    rng = random.Random(f"{seed}:{a}>{b}")
    stops: list[dict[str, Any]] = []
    for tag in r.get("tags") or []:
        h = haz.get(str(tag))
        if h and h["text"] and rng.random() < h["p"]:
            stops.append({"day": rng.randint(1, max(1, days)), "tag": str(tag), "text": h["text"], "dc": h["dc"], "pass": h["pass"], "fail": h["fail"], "fail_days": h["fail_days"]})
    stops.sort(key=lambda x: x["day"])
    return {"from": a, "to": b, "days": days, "stops": stops}


def encounters(root: Path, a: str, b: str, *, seed: str) -> list[str]:
    """Seeded: which of the route's hazards happen on this journey (the world pushes back:「世界不会这么顺从」)."""
    return [s["text"] for s in plan(root, a, b, seed=seed)["stops"]]


def route_days(root: Path, a: str, b: str) -> int | None:
    dist = route_distance(root, a, b)
    if dist is None:
        return None
    per_day = float(_data.rules(root).get("travel_per_day") or PER_DAY)
    return max(0, math.ceil(dist / per_day)) if dist > per_day / 2 else 0


def advance_calendar(root: Path, reg: Any, days: int, *, note: str, extra: list[str] | None = None, text: str | None = None) -> int:
    """time.day += days in run_state (the engine's own write, not an op); the narrator hears it as an <event>,
    with the route's own facts and whatever happened on the way."""
    if days <= 0:
        return 0
    rs_path = root / get_data_dir_name(root) / "meta" / "run_state.json"
    try:
        rs = json.loads(rs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    t = rs.get("time") if isinstance(rs.get("time"), dict) else {}
    t["day"] = int(t.get("day", 1)) + days
    rs["time"] = t
    rs_path.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
    if "time.day" in reg.variables:
        reg.variables["time.day"].value = t["day"]
    from neonrp.core.triggers import _INBOX, _meta, _read, _write

    inbox = _read(_meta(root) / _INBOX)
    items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
    items.append({"turn": turn, "trigger": "travel", "kind": "event", "id": "travel", "text": (text.format(day=t["day"]) if text else _t(root, "walked", note=note, days=days, day=t["day"])) + (" " + " ".join(extra) if extra else "")})
    inbox["items"] = items[-30:]
    _write(_meta(root) / _INBOX, inbox)
    return t["day"]


# ── the journey as a state machine: on the road → stopped by the road → resolved → arrived ────────────
# run_state.json["travel"] = {from, to, days, day, stops, pending, stopped_turn, log}. The map validator (packs.rpg.map.judge)
# asks the referee before it lets a cross-town move through; the roll tool settles a pending stop; the mover walks the rest.

def _rs_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "run_state.json"


def journey(root: Path) -> dict[str, Any] | None:
    try:
        j = json.loads(_rs_path(root).read_text(encoding="utf-8")).get("travel")
    except (OSError, ValueError):
        return None
    return j if isinstance(j, dict) and j.get("to") else None


def _write_journey(root: Path, j: dict[str, Any] | None) -> None:
    p = _rs_path(root)
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    if j is None:
        rs.pop("travel", None)
    else:
        rs["travel"] = j
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")


def _name(reg: Any, tid: str) -> str:
    e = reg.entries.get(tid) if reg is not None else None
    return e.name if e is not None else tid


def referee(root: Path, reg: Any, from_town: str, to_town: str, *, turn: int) -> tuple[str, dict[str, Any]]:
    """Ask the road whether the player gets to ``to_town`` this turn.

    Returns one of
      ("arrive",  {"days": n})                 — walk the rest (n days) and land; the mover advances the calendar
      ("stop",    journey)                      — the road stopped the party (newly stamped this turn or re-asked in the same turn);
                                                  the calendar has moved to the stop's day and the narrator gets an <event travel>
      ("blocked", journey)                      — a stop is still unresolved: no arrival until it is settled ([roll 1d6])
    Side effect (deliberate): a fresh stop is stamped when the referee refuses, so the state exists even if the re-proposed
    narration carries no op. Idempotent within a turn (stopped_turn)."""
    _ROOT["root"] = root
    j = journey(root)
    if j and j.get("from") == from_town and j.get("to") == to_town:
        if j.get("pending"):
            return "stop" if int(j.get("stopped_turn") if j.get("stopped_turn") is not None else -1) == int(turn) else "blocked", j
        nxt = [st for st in j.get("stops") or [] if int(st["day"]) > int(j.get("day", 0))]
        if nxt:
            st = nxt[0]
            _stamp(root, reg, j, st, turn)
            return "stop", j
        return "arrive", {"days": max(0, int(j.get("days", 0)) - int(j.get("day", 0))), "journey": j}
    p = plan(root, from_town, to_town, seed=str(turn))
    if not p["stops"] or p["days"] <= 0:
        return "arrive", {"days": p["days"]}
    j = {"from": from_town, "to": to_town, "days": p["days"], "day": 0, "stops": p["stops"], "pending": None, "stopped_turn": None, "log": []}
    _stamp(root, reg, j, p["stops"][0], turn)
    return "stop", j


def road_id(a: str, b: str) -> str:
    return f"road_{a}_{b}"


def route_target(root: Path, reg: Any, to: str) -> tuple[str, str] | None:
    """A move onto a road from one of its ends (its map id, its road id or its name): (here, the other end).
    10-19 N2 M5: the prose stopped on the trail, the state could only land at the dungeon's door — the road was no place."""
    here = reg.current_town or split_location(reg.player_location or "")[0]
    key = str(to or "").strip()
    if not here or not key:
        return None
    for r in _world_map(root).get("routes") or []:
        if not isinstance(r, dict) or (r.get("state") or {}).get("blocked"):
            continue
        a, b = str(r.get("from")), str(r.get("to"))
        if here not in (a, b):
            continue
        other = b if here == a else a
        if key in {str(r.get("id") or ""), str(r.get("name") or ""), road_id(here, other), road_id(a, b)} - {""}:
            return here, other
    return None


def set_out(root: Path, reg: Any, from_town: str, to_town: str, *, turn: int) -> str:
    """Walk onto the road and stop there (the player has set out, not arrived): a journey with nothing pending.
    The next move goes on (the road may still stop it) or turns back. Returns the road's id."""
    p = plan(root, from_town, to_town, seed=str(turn))
    # a road walked within the day has no stops (the referee lets those through: M8 r5 — a fog stop on the trail while
    # the prose was already at the door, and the party never got off the road)
    j = {"from": from_town, "to": to_town, "days": p["days"], "day": 0, "stops": p["stops"] if p["days"] > 0 else [], "pending": None,
         "stopped_turn": None, "log": [], "origin": reg.player_location}
    rid = road_id(from_town, to_town)
    companions = _souls_with_player(root, reg)
    _land(root, rid, town=None, display=_t(root, "road_name", a=_name(reg, from_town), b=_name(reg, to_town)), scope="road")
    _move_souls(root, reg, companions, rid)
    pl = reg.entries.get("player")
    if pl is not None:
        pl.parent = rid
    reg.player_location, reg.current_town = rid, None
    _write_journey(root, j)
    from neonrp.packs.rpg.loaders import add_road

    add_road(reg, j)
    return rid


def _land(root: Path, node: str, *, town: str | None, display: str, scope: str) -> None:
    """Write the player's position directly (the road is not on the town maps, so judge_move cannot land it)."""
    p = _rs_path(root)
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    loc = dict(rs.get("location") or {})
    loc.update({"scope": scope, "node_id": town, "node": node, "subnode_id": node if town else None, "display": display})
    rs["location"] = loc
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")


def _souls_with_player(root: Path, reg: Any) -> list[Any]:
    here = reg.player_location
    return [e for e in reg.of_class("soul") if here and e.parent == here]


def _move_souls(root: Path, reg: Any, souls: list[Any], node: str) -> None:
    from neonrp.core.turn_settlement import _apply_soul_move

    for e in souls:
        sdir = next((d for d in (root / "souls").iterdir() if d.name.endswith(e.id)), None) if (root / "souls").is_dir() else None
        if sdir is not None:
            _apply_soul_move(sdir, node, root=root, allow_cross_town=True)
            e.parent = node


def _stamp(root: Path, reg: Any, j: dict[str, Any], st: dict[str, Any], turn: int) -> None:
    walked = int(st["day"]) - int(j.get("day", 0))
    j["day"], j["pending"], j["stopped_turn"] = int(st["day"]), st, int(turn)
    if not j.get("origin"):  # leaving town: the party (player + whoever stands with them) is now ON THE ROAD, a place of its own
        j["origin"] = reg.player_location
        rid = road_id(j["from"], j["to"])
        a0, b0 = _name(reg, j["from"]), _name(reg, j["to"])
        companions = _souls_with_player(root, reg)
        _land(root, rid, town=None, display=_t(root, "road_name", a=a0, b=b0), scope="road")
        _move_souls(root, reg, companions, rid)
        pl = reg.entries.get("player")
        if pl is not None:
            pl.parent = rid
        reg.player_location, reg.current_town = rid, None
        from neonrp.packs.rpg.loaders import add_road

        add_road(reg, j)  # the live registry sees the road too (a re-verify in the same turn)
    _write_journey(root, j)
    a, b = _name(reg, j["from"]), _name(reg, j["to"])
    advance_calendar(root, reg, walked, note=_t(root, "from_toward", a=a, b=b),
                     text=_t(root, "stamp_event", a=a, b=b, d=j["day"], text=st["text"]))


_ROOT: dict[str, Any] = {}  # stop_reason's language comes from the world (set by referee)


def stop_reason(reg: Any, j: dict[str, Any], *, fresh: bool) -> str:
    """What the narrator is told when the road refuses the arrival (goes back as <refused move_to to>…</refused>)."""
    st = j.get("pending") or {}
    b = _name(reg, j["to"])
    if fresh:
        return _t(_ROOT.get("root"), "stop_fresh", d=j["day"], text=st.get("text"), b=b, road=road_id(j["from"], j["to"]), before=max(0, int(j["day"]) - 1))
    return _t(_ROOT.get("root"), "stop_blocked", d=j["day"], text=st.get("text"), b=b, to=j["to"])


def resolve(root: Path, reg: Any, total: int) -> str:
    """A die has been thrown while a stop is pending: settle it. Pass = the road lets the party through;
    fail = the road takes its price (days) and lets them through anyway. Returns the sentence for the tool's reply, or ''."""
    j = journey(root)
    st = (j or {}).get("pending")
    if not j or not st:
        return ""
    passed = int(total) >= int(st.get("dc", 4))
    cost = 0 if passed else int(st.get("fail_days") or 0)
    j["pending"] = None
    j.setdefault("log", []).append({"day": j["day"], "tag": st.get("tag"), "roll": int(total), "dc": st.get("dc"), "passed": passed, "cost_days": cost})
    if cost:
        j["day"] = int(j["day"]) + cost
    _write_journey(root, j)
    b = _name(reg, j["to"])
    if cost:
        advance_calendar(root, reg, cost, note="", text=_t(root, "fail_days", text=st.get("fail")))
    left = max(0, int(j["days"]) - int(j["day"]))
    tail = _t(root, "resolve_left", b=b, left=left) if left else _t(root, "resolve_today", b=b)
    return _t(root, "resolve_pass" if passed else "resolve_fail", dc=st.get("dc"), text=st.get("pass") if passed else st.get("fail")) + tail


def back(root: Path, reg: Any) -> str | None:
    """Turn around: walk the days already walked back to the origin, close the journey. Returns the landing."""
    j = journey(root)
    if not j:
        return None
    origin = str(j.get("origin") or "")
    walked = int(j.get("day", 0))
    _write_journey(root, None)
    a = _name(reg, j["from"])
    t, n = split_location(origin)
    _land(root, n or origin, town=t, display=f"{a}·{n or origin}", scope="town")
    if walked:
        advance_calendar(root, reg, walked, note="", text=_t(root, "back", n=walked, a=a))
    return origin


def finish(root: Path, reg: Any, from_town: str, to_town: str) -> int:
    """The mover landed the player in ``to_town``: walk the remaining days on the calendar and close the journey."""
    j = journey(root)
    if j and j.get("from") == from_town and j.get("to") == to_town:
        left = max(0, int(j.get("days", 0)) - int(j.get("day", 0)))
        _write_journey(root, None)
        a, b = _name(reg, from_town), _name(reg, to_town)
        if left:
            advance_calendar(root, reg, left, note=_t(root, "from_to", a=a, b=b), text=_t(root, "finish_left", n=left, b=b))
        else:
            advance_calendar(root, reg, 0, note="")
            from neonrp.core.triggers import _INBOX, _meta, _read, _write

            inbox = _read(_meta(root) / _INBOX)
            items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
            turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
            items.append({"turn": turn, "trigger": "travel", "kind": "event", "id": "travel", "text": _t(root, "arrived", b=b)})
            inbox["items"] = items[-30:]
            _write(_meta(root) / _INBOX, inbox)
        return left
    days = route_days(root, from_town, to_town) or 0
    if days:
        a, b = _name(reg, from_town), _name(reg, to_town)
        advance_calendar(root, reg, days, note=_t(root, "from_to", a=a, b=b))
    return days


def hint(reg: Any, root: Path) -> str:
    """One line for the travel hints when a journey is under way."""
    j = journey(root)
    if not j:
        return ""
    b = _name(reg, j["to"])
    a = _name(reg, j["from"])
    st = j.get("pending")
    left = max(0, int(j["days"]) - int(j["day"]))
    tail = _t(root, "hint_back", a_id=j["from"], a=a, d=j["day"])
    if st:
        return _t(root, "hint_pending", to=j["to"], b=b, d=j["day"], days=j["days"], text=st["text"]) + tail
    return _t(root, "hint_settled", to=j["to"], b=b, d=j["day"], days=j["days"], left=left) + tail


_DAY_RE = re.compile(r"第\s*([一二两三四五六七八九十\d]+)\s*天|\bday\s+(\d+|one|two|three|four|five|six|seven)\b|(\d+)\s*日目", re.IGNORECASE)
_EN = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_CN = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _day_num(tok: str) -> int:
    if tok.isdigit():
        return int(tok)
    if tok == "十":
        return 10
    n = 0
    for c in tok:
        if c == "十":
            n = (n or 1) * 10
        else:
            n += _CN.get(c, 0)
    return n


def overshoot(root: Path, reg: Any, narration: str, turn: int) -> list[dict[str, Any]]:
    """The road stopped the party on day N this turn, but the prose walked past it (fulllog-1001 C4a: stamped day 1,
    narrated 「第三天午后」an ambush). One fixable refusal: write up to day N only."""
    j = journey(root)
    tv = reg.variables.get("turn") if reg is not None else None
    this_turn = int(tv.value or 0) if tv is not None else int(turn)  # the stamp used the registry's turn counter, so compare with that
    if not j or not j.get("pending") or int(j.get("stopped_turn") if j.get("stopped_turn") is not None else -1) != this_turn:
        return []
    stop_day = int(j.get("day") or 1)
    days = sorted({_day_num(m.group(1)) if m.group(1) else (_EN.get(m.group(2).lower()) or int(m.group(2)) if m.group(2) else int(m.group(3)))
                   for m in _DAY_RE.finditer(narration or "")})
    over = [d for d in days if d > stop_day]
    if not over:
        return []
    b = _name(reg, j["to"])
    return [{"index": -1, "op": {"op": "move_to", "who": "player", "to": j["to"]}, "scope": "world", "field": "lines",
             "why": _t(root, "overshoot", d=stop_day, text=(j.get("pending") or {}).get("text"), over=max(over), b=b),
             "allowed": [], "fixable": True, "extra_loop": True}]


def plan_event(root: Path) -> str | None:
    """The ``plan_event`` seam (10-03, the planning seam): a stop on the road not yet settled does not wait for the talk."""
    j = journey(root)
    return "road_stop" if j and j.get("pending") else None



# ── a character elsewhere on the road (10-23) ────────────────────────────────────────────────────────────────────
# 21 of 69 regression runs had Rowan step from 碧石镇 to 石津镇's gate in one beat: the cross-town rule (set out, the
# road takes days) was the party's only. A character away from the player walks the same rule on her own clock: her
# move to another town puts her on the road (souls/<her>/run_state.json "travel"); when the world's day has moved on
# by the route's days, tick_souls lands her at the gate (one move_to, judged and landed like any other op).


def _soul_rs(root: Path, iid: str) -> tuple[Path | None, dict[str, Any]]:
    d = root / "souls"
    sdir = next((p for p in d.iterdir() if p.is_dir() and p.name.endswith(iid)), None) if d.is_dir() else None
    if sdir is None:
        return None, {}
    p = sdir / "run_state.json"
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    return p, rs if isinstance(rs, dict) else {}


def soul_journey(root: Path, iid: str) -> dict[str, Any] | None:
    j = _soul_rs(root, iid)[1].get("travel")
    return j if isinstance(j, dict) and j.get("to") else None


def _write_soul_journey(root: Path, iid: str, j: dict[str, Any] | None) -> None:
    p, rs = _soul_rs(root, iid)
    if p is None:
        return
    if j is None:
        rs.pop("travel", None)
    else:
        rs["travel"] = j
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")


def soul_journeys(root: Path, reg: Any) -> list[tuple[Any, dict[str, Any]]]:
    out = []
    for e in reg.of_class("soul"):
        j = soul_journey(root, e.id)
        if j:
            out.append((e, j))
    return out


def _today(reg: Any) -> int:
    try:
        return int(reg.variables["time.day"].value or 1) if "time.day" in reg.variables else 1
    except (TypeError, ValueError):
        return 1


def road_ends(root: Path, rid: str) -> tuple[str, str] | None:
    """The two towns of a road id, whichever way round it was written."""
    for r in _world_map(root).get("routes") or []:
        if isinstance(r, dict):
            a, b = str(r.get("from")), str(r.get("to"))
            if rid in (road_id(a, b), road_id(b, a)):
                return a, b
    return None


def soul_set_out(root: Path, reg: Any, e: Any, from_town: str, to_town: str) -> str:
    """She walks onto the road between her town and the other: her own journey, counted on the world's days."""
    j = {"from": from_town, "to": to_town, "days": route_days(root, from_town, to_town) or 0, "start_day": _today(reg)}
    rid = road_id(from_town, to_town)
    _move_souls(root, reg, [e], rid)
    _write_soul_journey(root, e.id, j)
    from neonrp.packs.rpg.loaders import add_road

    add_road(reg, {**j, "day": 0})
    return rid


def soul_days_left(reg: Any, j: dict[str, Any]) -> int:
    return max(0, int(j.get("days") or 0) - (_today(reg) - int(j.get("start_day") or _today(reg))))


def soul_landing(reg: Any, town: str) -> str:
    """Where a road ends for her: the town's gate, else the town itself."""
    return next((p.id for p in reg.of_class("place") if p.parent == town and "gate" in p.id), None) or town


def tick_souls(root: Path, reg: Any, *, turn: int = 0, res: Any = None) -> list[dict[str, Any]]:
    """A character whose road's days have passed arrives (atlas/move judges and lands the move)."""
    return [{"op": "move_to", "who": e.id, "to": soul_landing(reg, str(j["to"]))}
            for e, j in soul_journeys(root, reg) if soul_days_left(reg, j) == 0 and e.parent == road_id(str(j["from"]), str(j["to"]))]


def soul_arrived(root: Path, reg: Any, e: Any, to_town: str) -> None:
    """Close her journey and tell the narrator (the trigger inbox, as the party's arrival does)."""
    _write_soul_journey(root, e.id, None)
    try:
        from neonrp.core.triggers import _INBOX, _meta, _read, _write

        inbox = _read(_meta(root) / _INBOX)
        items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
        turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
        items.append({"turn": turn, "trigger": "travel", "kind": "event", "id": f"travel:{e.id}",
                      "text": _t(root, "soul_arrived", who=e.name, b=_name(reg, to_town))})
        inbox["items"] = items[-30:]
        _write(_meta(root) / _INBOX, inbox)
    except Exception:  # noqa: BLE001 — telling is never worth failing the move
        pass
