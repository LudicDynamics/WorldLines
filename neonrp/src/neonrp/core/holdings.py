"""Who holds what, and who walks with the player — read off the registry before and after one apply (10-14, the standard
front end: it compared two state snapshots to guess 「捡到 / 别人给的 / 用掉了」 and 「同行」).

    snapshot(reg)                 things (owner · parent · class · name · effect?) and people (where they stand)
    diff(before, after)           (gained, lost) — every change of owner, whoever made it (the model's ops, a template
                                  handler, a tick, a trigger, an effect running out)
    party(root, reg, before, …)   (joined, left) — the souls walking with the player, kept in ``<data>/meta/party.json``

A *thing* is any entry that is not a person and not a place; its owner is ``Registry.owner_of`` (an effect's ``on``, a
person it sits on, the player's bag). ``how`` says where it came from / went: gained ``new`` (made in someone's hands) ·
``picked`` (from a place, or from nobody) · ``given`` (from another person); lost ``gone`` (removed: used up, ran out) ·
``dropped`` (left at a place) · ``given`` (to another person).

The party needs no party in the world: a soul joins when it comes along on the player's move (it stood with the player
and lands where the player lands), leaves when the player goes on without it or it walks off; a soul cast as the
player's ``companion`` and standing with the player is in it from the start.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLACE_CLASSES = ("place", "town", "room", "dungeon", "region", "road", "world", "level")


def snapshot(reg: Any) -> dict[str, Any]:
    things: dict[str, dict[str, Any]] = {}
    people: dict[str, Any] = {}
    for e in reg.entries.values():
        if str(e.id).startswith("~"):
            continue
        if reg.is_person(e.cls):
            people[e.id] = e.parent
            continue
        if e.cls in PLACE_CLASSES:
            continue
        spec = reg.classes.get(e.cls)
        things[e.id] = {"owner": reg.owner_of(e), "parent": e.parent, "cls": e.cls, "name": e.name,
                        "effect": bool(spec is not None and getattr(spec, "effect", False)), "clue": reg.is_clue(e)}
    return {"things": things, "people": people, "player": reg.player_location}


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gained: list[dict[str, Any]] = []
    lost: list[dict[str, Any]] = []
    people = set(before.get("people") or {}) | set(after.get("people") or {})
    b_all, a_all = before.get("things") or {}, after.get("things") or {}
    for tid in list(b_all) + [k for k in a_all if k not in b_all]:
        b, a = b_all.get(tid), a_all.get(tid)
        ob, oa = (b or {}).get("owner"), (a or {}).get("owner")
        if ob == oa:
            continue
        x = a or b or {}
        rec = {"id": tid, "cls": x.get("cls"), "name": x.get("name"), "kind": "effect" if x.get("effect") else "clue" if x.get("clue") else "item"}
        if ob:
            to = oa or (a or {}).get("parent")
            lost.append({**rec, "who": ob, "to": to, "how": "gone" if a is None else "given" if oa in people else "dropped"})
        if oa:
            fr = ob or (b or {}).get("parent")
            gained.append({**rec, "who": oa, "from": fr, "how": "new" if b is None else "given" if ob in people else "picked"})
    return gained, lost


def _party_path(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return root / get_data_dir_name(root) / "meta" / "party.json"


def members(root: Path) -> list[str] | None:
    """The souls walking with the player now (None = not tracked yet in this run)."""
    try:
        d = json.loads(_party_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return [str(x) for x in d.get("members") or []] if isinstance(d, dict) else None


def _souls(root: Path) -> dict[str, dict[str, str]]:
    """instance id → {sid, role} from the run's playthrough.json."""
    from neonrp.core.paths import get_data_dir_name

    for p in (root / "playthrough.json", root / get_data_dir_name(root) / "playthrough.json", root / ".neonrp" / "playthrough.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        return {str(s.get("instance_id")): {"sid": str(s.get("sid") or ""), "role": str(s.get("role") or "")}
                for s in d.get("souls") or [] if isinstance(s, dict) and s.get("instance_id")}
    return {}


def party(root: Path, reg: Any, before: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(joined, left) this apply, and the party file brought up to date."""
    cast = _souls(root)
    souls = {e.id for e in reg.of_class("soul")}
    was = members(root)
    p0, p1 = before.get("player"), reg.player_location
    stood0 = before.get("people") or {}
    joined: list[dict[str, Any]] = []
    left: list[dict[str, Any]] = []

    def rec(iid: str, why: str) -> dict[str, Any]:
        e = reg.entries.get(iid)
        return {"iid": iid, "sid": (cast.get(iid) or {}).get("sid") or iid, "name": e.name if e is not None else iid, "why": why}

    if was is None:  # first look at this run: the companions standing with the player are already with them
        was = []
        for iid in sorted(souls):
            if (cast.get(iid) or {}).get("role") == "companion" and p0 and stood0.get(iid) == p0:
                was.append(iid)
                joined.append(rec(iid, "companion"))
    now = [m for m in was if m in souls]
    left += [rec(m, "gone") for m in was if m not in souls]  # left the world (died, written out)
    here = {iid: (reg.entries[iid].parent if iid in reg.entries else None) for iid in souls}
    if p1 and p1 != p0:  # the player moved: whoever stood with them and landed with them came along
        for iid in sorted(souls):
            if iid not in now and p0 and stood0.get(iid) == p0 and here.get(iid) == p1:
                now.append(iid)
                joined.append(rec(iid, "follow"))
        for iid in list(now):
            if here.get(iid) != p1:
                now.remove(iid)
                left.append(rec(iid, "stayed"))
    else:
        for iid in list(now):
            if here.get(iid) != p1:
                now.remove(iid)
                left.append(rec(iid, "left"))
    if joined or left or members(root) is None:
        p = _party_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"members": now}, ensure_ascii=False, indent=2), encoding="utf-8")
    return joined, left
