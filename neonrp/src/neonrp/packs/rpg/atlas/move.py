"""The RPG template's map: the town graph judge and the player / NPC / soul movers (rpg pack).
Bound from the pack's ``move_to`` action (validator / handler) and its ``participation`` seam."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.core.handlers import Verdict
from neonrp.packs.rpg.i18n import t as _t

# ── reference handlers (the RPG template's map) ──────────────────────────────

def _nm(reg: Any, tid: str) -> str:
    e = reg.entries.get(tid)
    return e.name if e is not None else tid


def judge(root: Path, reg: Any, who: str, cur: str, to: str) -> Verdict:
    """The engine's graph: in-town free, cross-town two beats (clamp to the gate), scoped ids."""
    from neonrp.core.place_nav import judge_move, qualify_location

    from neonrp.core.place_nav import split_location
    from neonrp.packs.rpg import travel

    allowed = [f"{e.id}({e.name})" for e in reg.exits(cur)] if cur else []
    mover = reg.entries.get(who) if who != "player" else None
    if mover is not None and mover.parent != reg.player_location:  # a character elsewhere: her own town, her own road (10-23)
        away, to = _judge_away(root, reg, mover, cur, to, allowed)
        if away is not None:
            return away
    here_e, to_e = reg.entries.get(cur), reg.entries.get(to)
    if not (here_e is not None and here_e.cls == "road"):
        rt = travel.route_target(root, reg, to)
        if rt is not None:  # setting out: the party stops on the road (10-19), the next beat goes on or back
            rid = travel.road_id(*rt)
            if who != "player" and (who not in reg.entries or reg.entries[who].parent != reg.player_location):
                return Verdict(False, None, reason=_t(root, "follow_party"), allowed=allowed, field="to", fixable=False)
            return Verdict(True, rid, clamped=(rid != to), reason=_t(root, "set_out", b=_nm(reg, rt[1])), allowed=allowed)
    if here_e is not None and here_e.cls == "road":  # on the road: continue to the destination, or turn back; nothing else
        j = travel.journey(root)
        if not j:
            return Verdict(False, None, reason=_t(root, "road_done"), allowed=allowed, field="to")
        if to == cur or to in {travel.road_id(j["from"], j["to"]), str(travel.route_facts(root, j["from"], j["to"]).get("id") or cur)}:
            return Verdict(True, cur, clamped=(to != cur), allowed=allowed)  # already on it
        to_town = split_location(to)[0] or to

        def _arrival() -> Verdict:  # the road's end: a town's gate, a dungeon's entry room (10-19)
            dest = reg.entries.get(j["to"])
            if "/" in to:
                return Verdict(True, to, allowed=allowed)
            if dest is not None and dest.cls == "dungeon":
                entry = next((r for r in reg.of_class("room") if r.parent == j["to"] and str(r.props.get("type")) == "entry"), None)
                if entry is not None:
                    return Verdict(True, entry.id, clamped=True, reason=_t(root, "enter_entry", d=dest.name, e=entry.name), allowed=allowed)
                return Verdict(True, to, allowed=allowed)
            landing = next((r.id for r in reg.of_class("place") if r.parent == j["to"] and "gate" in r.id), None) or to
            return Verdict(True, landing, clamped=(landing != to), reason=(_t(root, "enter_gate", b=_nm(reg, j["to"])) if landing != to else ""), allowed=allowed)

        if who != "player":
            if j.get("pending"):
                return Verdict(False, None, reason=_t(root, "companion_on_road", who=_nm(reg, who), to=to_town), allowed=allowed, field="to", fixable=False)
            if to_town == j["to"]:
                return _arrival()
            if to_town == j["from"]:
                return Verdict(True, to, allowed=allowed)
            return Verdict(False, None, reason=_t(root, "follow_party"), allowed=allowed, field="to", fixable=False)
        turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
        if to_town == j["to"]:
            state, jj = travel.referee(root, reg, j["from"], j["to"], turn=turn)
            if state == "stop":
                return Verdict(False, None, reason=travel.stop_reason(reg, jj, fresh=True), allowed=allowed, field="to")
            if state == "blocked":
                return Verdict(False, None, reason=travel.stop_reason(reg, jj, fresh=False), allowed=allowed, field="to")
            return _arrival()
        if to_town == j["from"]:
            if int(j.get("stopped_turn") if j.get("stopped_turn") is not None else -1) == turn:  # stamped this very turn: the re-proposal is describing the stop, not turning back
                return Verdict(False, None, reason=_t(root, "no_turn_back_now"), allowed=[j["to"]], field="to")
            back_to = to if "/" in to and to in reg.entries else str(j.get("origin") or j["from"])
            return Verdict(True, back_to, clamped=(back_to != to), reason=_t(root, "turn_back", n=j["day"], a=_nm(reg, j["from"])), allowed=allowed)
        return Verdict(False, None, reason=_t(root, "road_only", b=_nm(reg, j["to"]), to=j["to"], from_=j["from"]), allowed=[j["to"], j["from"]], field="to")
    if to_e is not None and to_e.cls in ("room", "dungeon") and not (here_e is not None and here_e.cls == "room"):
        # entering a dungeon from a town obeys the same two beats the landing does (10-02 N2: verify said R001, apply
        # clamped to the gate — the narrator fought at the gate it thought was the dungeon)
        did = to if to_e.cls == "dungeon" else str(to_e.parent or "")
        gv = judge_move(root, current_location=qualify_location(root, cur), target=did)
        if not gv.allowed and gv.clamped_to:
            landing = reg.resolve(gv.clamped_to, cls="place") or gv.clamped_to
            return Verdict(True, landing, clamped=True, reason=gv.reason or "", allowed=allowed)
    if to_e is not None and to_e.cls == "room":  # dungeon rooms: the layout graph is the map (judge_move knows towns, not rooms)
        if here_e is not None and here_e.cls == "room":
            if to_e.parent != here_e.parent:
                return Verdict(False, None, reason=_t(root, "other_dungeon", name=to_e.name), allowed=allowed, field="to")
            if to == cur or to in here_e.links:
                return Verdict(True, to, allowed=allowed)
            return Verdict(False, None, reason=_t(root, "not_adjacent", name=to_e.name), allowed=allowed, field="to")
        entry = next((r for r in reg.of_class("room") if r.parent == to_e.parent and str(r.props.get("type")) == "entry"), None)
        if entry is not None and entry.id != to:
            return Verdict(True, entry.id, clamped=True, reason=_t(root, "enter_entry", d=reg.entries[to_e.parent].name if to_e.parent in reg.entries else to_e.parent, e=entry.name), allowed=allowed)
        return Verdict(True, to, allowed=allowed)
    if to_e is not None and to_e.cls == "dungeon":  # "去 D001": land in the entry room
        entry = next((r for r in reg.of_class("room") if r.parent == to and str(r.props.get("type")) == "entry"), None)
        if entry is not None:
            return Verdict(True, entry.id, clamped=True, reason=_t(root, "enter_entry", d=to_e.name, e=entry.name), allowed=allowed)
    v = judge_move(root, current_location=qualify_location(root, cur), target=to)
    landing = None
    if v.allowed:
        landing = reg.resolve(v.resolved, cls="place") if v.resolved and reg.resolve(v.resolved, cls="place") else to
    elif v.clamped_to:
        landing = reg.resolve(v.clamped_to, cls="place") or v.clamped_to
    if landing:
        from_town, to_town = split_location(cur)[0], split_location(landing)[0]
        if from_town and to_town and to_town != from_town:
            # a journey: the road (referee) decides whether the party arrives this turn (世界不会这么顺从)
            turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
            if who == "player":
                state, j = travel.referee(root, reg, from_town, to_town, turn=turn)
                if state == "stop":
                    return Verdict(False, None, reason=travel.stop_reason(reg, j, fresh=True), allowed=allowed, field="to")
                if state == "blocked":
                    return Verdict(False, None, reason=travel.stop_reason(reg, j, fresh=False), allowed=allowed, field="to")
            else:
                j = travel.journey(root)
                # a companion cannot arrive while the party is held up on the road; once the stop is settled she may land with the player (adv9 C4d)
                if j and j.get("pending") and j.get("to") == to_town and (reg.player_location or "").split("/")[0] != to_town:
                    return Verdict(False, None, reason=_t(root, "companion_on_road", who=reg.entries[who].name if who in reg.entries else who, to=to_town), allowed=allowed, field="to", fixable=False)
        if v.allowed:
            return Verdict(True, landing, allowed=allowed)
        return Verdict(True, landing, clamped=True, reason=v.reason or "", allowed=allowed)
    return Verdict(False, None, reason=v.reason or "move refused", allowed=allowed)


def _judge_away(root: Path, reg: Any, mover: Any, cur: str, to: str, allowed: list[str]) -> tuple[Verdict | None, str]:
    """A character away from the player (10-23: 21 of 69 regression runs had Rowan step from one town to the other's
    gate in one beat — the cross-town rule was the party's only). Her names resolve in her own town (「北门」 is her
    town's gate or nothing, never the player's); another town is a road she walks on her own days (travel.soul_set_out);
    on her road she arrives when the days have passed. (None, to) = nothing of hers applies: the rules below, with
    ``to`` resolved in her town."""
    from neonrp.core.place_nav import resolve_move_target, split_location
    from neonrp.packs.rpg import travel

    here_e = reg.entries.get(cur)
    if str(cur).startswith("road_") or (here_e is not None and here_e.cls == "road"):
        j = travel.soul_journey(root, mover.id)
        if not j:
            return None, to  # with the party on its road: the party's rule
        if to == cur:
            return Verdict(True, cur, allowed=allowed), to
        to_town = split_location(to)[0] or to
        if to_town == j["to"]:
            left = travel.soul_days_left(reg, j)
            if left:
                return Verdict(False, None, reason=_t(root, "soul_on_road", who=mover.name, b=_nm(reg, j["to"]), n=left), allowed=[cur], field="to", fixable=False), to
            landing = to if "/" in to and to in reg.entries else travel.soul_landing(reg, j["to"])
            return Verdict(True, landing, clamped=(landing != to), reason=_t(root, "soul_arrived", who=mover.name, b=_nm(reg, j["to"])), allowed=allowed), to
        if to_town == j["from"]:
            back = to if "/" in to and to in reg.entries else travel.soul_landing(reg, j["from"])
            return Verdict(True, back, clamped=(back != to), allowed=allowed), to
        return Verdict(False, None, reason=_t(root, "road_only", b=_nm(reg, j["to"]), to=j["to"], from_=j["from"]), allowed=[j["to"], j["from"]], field="to", fixable=False), to
    my_town = split_location(cur)[0] or cur
    t_town, t_node = split_location(to)
    if not t_town:
        tid = reg.resolve(to, cls="town")
        if tid:
            t_town, t_node = tid, None
    if not t_town:  # a bare id or name: hers or nothing
        own = [p for p in reg.of_class("place") if p.parent == my_town]
        resolved = resolve_move_target(root, to, current_location=cur) if t_node else None
        if resolved and split_location(resolved)[0] == my_town:
            return None, resolved
        by_name = next((p.id for p in own if p.name == to), None)
        if by_name:
            return None, by_name
        return Verdict(False, None, reason=_t(root, "soul_no_place", who=mover.name, a=_nm(reg, my_town), to=to),
                       allowed=[f"{p.id}({p.name})" for p in own], field="to"), to
    if t_town == my_town:
        return None, to
    days = travel.route_days(root, my_town, t_town)
    if days is None:
        return Verdict(False, None, reason=_t(root, "soul_no_road", who=mover.name, a=_nm(reg, my_town), b=_nm(reg, t_town)), allowed=allowed, field="to", fixable=False), to
    if days == 0:
        return None, to  # within the day: the rules below land her at the gate
    return Verdict(True, travel.road_id(my_town, t_town), clamped=True,
                   reason=_t(root, "soul_set_out", who=mover.name, a=_nm(reg, my_town), b=_nm(reg, t_town), n=days), allowed=allowed), to


def move(root: Path, reg: Any, who: str, to: str) -> bool:
    """Land a move: player run_state, NPC file, or the soul's run_state."""
    if who == "player":
        from neonrp.core.place_nav import split_location
        from neonrp.core.turn_settlement import _apply_player_move
        from_town = reg.current_town
        to_town, _node = split_location(to)
        here_e = reg.entries.get(reg.player_location or "")
        if here_e is not None and here_e.cls == "road":  # leaving the road: land directly (the road is not on the town maps)
            from neonrp.packs.rpg import travel

            if to == here_e.id:
                return True
            j = travel.journey(root) or {}
            companions = travel._souls_with_player(root, reg)
            if to_town == j.get("from"):
                origin = travel.back(root, reg)
                if origin and "/" in to and to != origin and to in reg.entries:  # back to a place beside the road, not the gate
                    t, n = split_location(to)
                    travel._land(root, n or to, town=t, display=f"{_nm(reg, t or to)}·{n or ''}".rstrip("·"), scope="town")
                    origin = to
                if origin:
                    travel._move_souls(root, reg, companions, origin)
                return bool(origin)
            t, n = split_location(to)
            travel._land(root, n or to, town=t, display=f"{_nm(reg, t or to)}·{n or ''}".rstrip("·"), scope="town")
            travel._move_souls(root, reg, companions, to)
            travel.finish(root, reg, str(j.get("from") or from_town), to_town or to)
            _room_entered(root, reg, to)
            return True
        if str(to).startswith("road_"):
            from neonrp.packs.rpg import travel

            rt = travel.route_target(root, reg, to)
            if rt is None:
                return False
            turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
            travel.set_out(root, reg, *rt, turn=turn)
            return True
        ok = bool(_apply_player_move(root, to))
        if ok and from_town and to_town and to_town != from_town:  # a journey: walk the remaining days on the calendar, close the journey
            from neonrp.packs.rpg import travel

            travel.finish(root, reg, from_town, to_town)
        if ok:
            _room_entered(root, reg, to)
        return ok
    e = reg.entries.get(who)
    if str(to).startswith("road_"):
        if e is not None and e.parent == to:
            return True
        from neonrp.packs.rpg import travel

        if e is not None and e.cls == "soul" and e.parent != reg.player_location:  # away from the party: her own road (10-23)
            from neonrp.core.place_nav import split_location

            ends = travel.road_ends(root, to)
            my_town = split_location(e.parent or "")[0] or e.parent
            if ends is None or my_town not in ends:
                return False
            travel.soul_set_out(root, reg, e, my_town, ends[1] if ends[0] == my_town else ends[0])
            return True
        travel._move_souls(root, reg, [e] if e is not None else [], to)  # a companion sets out with the party (the player's move already carried her)
        return e is not None
    if e is not None and e.cls == "npc":
        return bool(move_npc(root, e, to))
    from neonrp.core.ontology import move_entity

    own_road = None
    if e is not None and e.cls == "soul" and str(e.parent).startswith("road_"):
        from neonrp.packs.rpg import travel

        own_road = travel.soul_journey(root, who)
    ok = bool(move_entity(root, who, to).get("ok"))
    if ok and own_road:  # off her road: arrived, or turned back
        from neonrp.core.place_nav import split_location
        from neonrp.packs.rpg import travel

        if (split_location(to)[0] or to) == own_road["to"]:
            travel.soul_arrived(root, reg, e, str(own_road["to"]))
        else:
            travel._write_soul_journey(root, who, None)
    return ok




def _room_entered(root: Path, reg: Any, to: str) -> None:
    room = reg.entries.get(to)
    if room is not None and room.cls == "room":  # a dungeon room rolls its encounter table on entry
        from neonrp.packs.rpg import combat

        turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else 0
        combat.maybe_encounter(root, reg, room, turn=turn)


def colocated(root: Path, reg: Any, iid: str) -> bool:
    """rpg participation: a soul takes part when it stands where the player stands."""
    e = reg.entries.get(iid)
    return bool(e is not None and reg.player_location and e.parent == reg.player_location)


def move_npc(root: Path, e: Any, to: str) -> bool:
    """An NPC lives in its town's ``npcs.json``; moving it rewrites that record's location."""
    import json

    from neonrp.core.place_nav import split_location

    src = e.source or ""
    if not src.endswith("npcs.json"):
        return False
    path = root / src
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    _t, node = split_location(to)
    for n in data.get("npcs") or []:
        if isinstance(n, dict) and str(n.get("id")) in (e.id, e.id.split("/")[-1]):
            n["location"] = node or to
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
    return False
