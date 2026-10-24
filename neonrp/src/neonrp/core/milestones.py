"""Open-adventure milestones (PLATFORM-PLAY-RULES-1015 §5 §9, 10-15): the author only says whether a world has
them (``template.json`` ``milestones: true | false``; unset = on for an ``open-adventure`` run); the engine finds them
itself, and settles them when the player leaves.

    a new place found        type place    (``place.discovered`` of the beat — grow · arrive · reveal; only a place that
                                            has a picture — the author's CG or its scene image — and at most PLACE_MAX a run)
    a commission completed   type job      (a ``job`` entry whose state now reads done, core/objective.job_state)
    a day gone by            type day      (``time.day`` moved on)
    a stretch of the road    type stretch  (STRETCH beats went by with no milestone — an open adventure may never end,
                                             so the milestones keep coming at a pace)

    event   milestone {turn, id, type, label, points, art, generate}   (type = the kind of milestone; ``kind`` is the event's name)                              (/engine/beats)
    POST /api/v1/play/engine/settlement/leave
    → {milestones: [...settled now], points, art: [...], rewards: [...pending], since}           (again: only what is new)
    GET  /api/v1/play/engine/settlement/milestones → {enabled, milestones: [...all], settled}

The picture (10-15: an endless run outgrows any author's CG, and a milestone need not have its own):

    art: {kind: "cg", slot}                                         the author's picture for it (a plot picture of the
                                                                    place / the commission), when there is one
    art: {kind: "composite", scene, souls: [{iid, sid, name, slot}], caption}
                                                                    else the front end composes one: the scene picture of
                                                                    where the player stands + the companions present
                                                                    (sprite, else portrait) + one line
    generate: {scene, caption}                                      what a live picture would be made of — the front
                                                                    end's button (Voyager; others see it greyed → the
                                                                    upgrade page); the engine never generates on its own

Each milestone is reached once per run (``meta/milestones.json``). Its points and its picture are written into the
player's record as a pending reward when the player leaves (core/player_data ``rewards``: the platform pays out).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# provisional (to be set): the open adventure's milestones give more — the first values × 1.5 (lead 10-15)
POINTS = {"place": 30, "job": 75, "day": 45, "stretch": 30}
PLACE_MAX = 10
STRETCH = 12  # beats without a milestone before the road itself counts as one
_FILE = "milestones.json"
CONTRACTS = ("open-adventure",)


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta"


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, d: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def enabled(root: Path) -> bool:
    rec = _j(_meta(root) / "template.json", {}) or {}
    if isinstance(rec.get("milestones"), bool):
        return rec["milestones"]
    from neonrp.template import contract as C

    return str((C.run_contract(root) or {}).get("id") or "") in CONTRACTS


def _state(root: Path) -> dict[str, Any]:
    d = _j(_meta(root) / _FILE, {}) or {}
    return {"items": list(d.get("items") or []), "settled": int(d.get("settled") or 0), "beats": int(d.get("beats") or 0)}


def _T(root: Path) -> dict[str, Any]:
    from neonrp import prompts
    from neonrp.core.output_lang import prompt_lang

    return prompts.strings("milestones", prompt_lang(root))


def _author_cg(slots: dict[str, Any], eid: str | None) -> str | None:
    """A plot picture the author drew for this thing (a place, a commission) — filled, not a class slot's stand-in."""
    if not eid:
        return None
    hit = next((s for s in slots.values() if s["slot"].startswith("plot:") and ":ending:" not in s["slot"]
                and s.get("inst") == eid and s.get("have")), None)
    return str(hit["slot"]) if hit else None


def _has_scene(root: Path, addr: str | None) -> bool:
    from neonrp.core import worldmap

    return bool(addr) and worldmap.scene_image_path(Path(root), str(addr)) is not None


def art(root: Path, reg: Any, label: str, eid: str | None = None, slots: dict[str, Any] | None = None) -> dict[str, Any]:
    """The milestone's picture: the author's CG, else the parts of a composite (scene + companions here + a line)."""
    from neonrp.core import holdings, show

    try:
        slots = slots if slots is not None else show.run_slots(root, reg)
    except Exception:  # noqa: BLE001 — no slots: a composite of nothing but the line
        slots = {}
    own = _author_cg(slots, eid)
    if own:
        return {"kind": "cg", "slot": own}
    here = reg.player_location
    scene = next((s["slot"] for s in slots.values() if s.get("cls") == "place" and s.get("entry") == here), None)
    if scene and not _has_scene(root, here):
        scene = None  # a slot nobody filled: the front end draws its own backdrop
    party = holdings.members(root) or []
    souls = []
    for iid, info in holdings._souls(root).items():
        e = reg.entries.get(iid)
        if e is None or e.parent != here or (iid not in party and info.get("role") != "companion"):
            continue
        sid = str(info.get("sid") or iid)
        slot = next((f"soul.{k}:{sid}" for k in ("sprite", "portrait") if f"soul.{k}:{sid}" in slots), None)
        souls.append({"iid": iid, "sid": sid, "name": e.name, **({"slot": slot} if slot else {})})
    return {"kind": "composite", "scene": scene, "souls": souls, "caption": label}


def after_apply(root: Path, reg: Any, res: Any, vars0: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The milestones this beat reached (each once a run)."""
    if not enabled(root):
        return []
    from neonrp.core.objective import job_state

    st = _state(root)
    have = {m["id"] for m in st["items"]}
    T = _T(root)
    found: list[tuple[str, str, str, str | None]] = []  # (id, kind, label, the entry it is about)

    def add(mid: str, kind: str, label: str, eid: str | None = None) -> None:
        if mid not in have:
            have.add(mid)
            found.append((mid, kind, label, eid))

    places = sum(1 for m in st["items"] if m.get("type") == "place")
    disc = [pl for pl in getattr(res, "discovered", None) or [] if pl.get("addr")]
    if disc and places < PLACE_MAX:
        from neonrp.core import show

        try:
            slots0 = show.run_slots(root, reg)
        except Exception:  # noqa: BLE001
            slots0 = {}
        for pl in disc:
            addr = str(pl["addr"])
            if places >= PLACE_MAX or f"place:{addr}" in have or not (_author_cg(slots0, addr) or _has_scene(root, addr)):
                continue  # a place with no picture is not a milestone (the map still shows it)
            places += 1
            add(f"place:{addr}", "place", str(T["place"]).format(name=pl.get("name") or addr), addr)
    for e in reg.of_class("job"):
        if job_state(e.props.get("state") or e.props.get("status")) == "done":
            add(f"job:{e.id}", "job", str(T["job"]).format(name=e.name or e.id), e.id)
    day0 = (vars0 or {}).get("time.day")
    day = reg.variables["time.day"].value if "time.day" in reg.variables else None
    if isinstance(day0, int) and isinstance(day, int) and day > day0:
        for d in range(day0, day):
            add(f"day:{d}", "day", str(T["day"]).format(n=d))
    turn = getattr(res, "turn", None)
    beats = int(st.get("beats") or 0) + 1
    if not found and beats >= STRETCH:
        add(f"stretch:{len([m for m in st['items'] if m.get('type') == 'stretch']) + 1}", "stretch", str(T["stretch"]))
    st["beats"] = 0 if found else beats
    new = []
    if found:
        from neonrp.core import show

        try:
            slots = show.run_slots(root, reg)
        except Exception:  # noqa: BLE001
            slots = {}
        for mid, kind, label, eid in found:
            a = art(root, reg, label, eid, slots)
            gen = {"scene": reg.player_location, "caption": label}
            new.append({"id": mid, "type": kind, "label": label, "points": POINTS[kind], "turn": turn, "art": a, "generate": gen})
        st["items"] += new
    _w(_meta(root) / _FILE, st)
    return new


def listing(root: Path) -> dict[str, Any]:
    st = _state(root)
    return {"enabled": enabled(root), "milestones": st["items"], "settled": st["settled"]}


def leave(root: Path) -> dict[str, Any]:
    """The player leaves: the milestones reached since the last leave are settled — points and CG written as a
    pending reward each, so leaving twice never pays twice."""
    from neonrp.core import player_data

    st = _state(root)
    fresh = st["items"][st["settled"]:]
    world = player_data.world_of(root)
    run = Path(root).name
    rewards = []
    for m in fresh:
        rid = f"milestone:{world}:{run}:{m['id']}"
        fields = {"amount": m["points"], **({"art": m["art"]} if m.get("art") else {})}
        if player_data.add_reward(rid, "points", world, f"milestone:{m['type']}", **fields):
            rewards.append({"id": rid, "kind": "points", **fields, "status": "pending"})
    since = st["settled"]
    st["settled"] = len(st["items"])
    _w(_meta(root) / _FILE, st)
    return {"milestones": fresh, "points": sum(m["points"] for m in fresh), "art": [m["art"] for m in fresh if m.get("art")],
            "rewards": rewards, "since": since}
