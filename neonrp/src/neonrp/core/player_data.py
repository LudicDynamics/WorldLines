"""The player's own record across runs (10-15, niko): characters they have gained, endings they have reached,
achievements — each an id + when + which world it came from. One file per player, kept with the launcher's things in
``~/.worldlines/player-data/<player>.json`` (engine / launcher line: never inside a template or a run folder).

    GET /api/v1/local/player-data[?player=<id>]
    → {player, characters: [{sid, name, world, how, memory, at}], talked: [{sid, name, world, at}],
       endings: [{id, title, world, at}], achievements: [{id, world, at, source}],
       rewards: [{id, kind, amount?, cg?, world, source, status: pending, at}],
       cards: [{id, world, kind, title, desc, rarity, image?, version, run, source, at}],
       runs: [{world, run, exit, ending?, version, at}]}

``cards`` are what a world's ``rewards`` handed out (core/rewards, 10-18): each a copy of the card as it was when it was
earned (its picture copied beside the record) — never taken back, even when the author drops it; ``version`` is the
template's then, and when the author ships a new one the player may pull the new face (:func:`refresh`). ``runs`` —
one row per run that reached its exit (``run.settled``: the 「打完一局」 every achievement / replay agrees on).

``rewards`` are what a settlement / milestone / achievement earned and the platform has not paid out yet (points need
the platform's account — PLATFORM-PLAY-RULES §9): written ``pending``; the platform marks them ``granted``.

The player is ``local`` unless ``WORLDLINES_PLAYER_ID`` says otherwise (a signed-in account can name its own file).

Two switches on a soul (PLATFORM-PLAY-RULES-1015 §3 §5), and the rules that follow:

- ``standalone: true`` — the character can be chatted with on its own without being gained first. Talking with it (a
  direct chat, core/light_chat, or it answered the player in a beat of a run) is noted in ``talked`` — it is **not**
  gained by that (niko 10-15); its chat thread and memory stay as they are
- ``takeable`` (default true) + ``take_when`` (default ``companion_at_ending``; or ``ending:<id>``) — when the condition
  holds the player takes the character home with its full memory (``how`` = the condition, ``memory: full``):
  ``companion_at_ending`` = it walks with the player when any ending lands; ``ending:<id>`` = that ending landed
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

HOME = Path.home() / ".worldlines" / "player-data"
_LOCK = threading.Lock()


def player_id() -> str:
    pid = os.environ.get("WORLDLINES_PLAYER_ID", "").strip()
    return "".join(c for c in pid if c.isalnum() or c in "-_.") or "local"


def _path(player: str | None = None) -> Path:
    return HOME / f"{player or player_id()}.json"


def read(player: str | None = None) -> dict[str, Any]:
    pid = player or player_id()
    try:
        d = json.loads(_path(pid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"player": pid, **{k: list(d.get(k) or []) for k in KINDS}}


def _add(kind: str, rec: dict[str, Any], key: tuple[str, ...], player: str | None = None) -> bool:
    """Add one record unless one with the same ``key`` fields is there. True = new."""
    with _LOCK:
        d = read(player)
        if any(all(r.get(k) == rec.get(k) for k in key) for r in d[kind]):
            return False
        d[kind].append({**rec, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        _save(d)
        return True


def _save(d: dict[str, Any]) -> None:
    p = _path(d["player"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({k: d[k] for k in KINDS}, ensure_ascii=False, indent=1), encoding="utf-8")
    try:  # signed in: the record goes up to the account shortly (core/collection_sync, 10-18)
        from neonrp.core import collection_sync

        collection_sync.schedule()
    except Exception:  # noqa: BLE001 — syncing never stops a save
        pass


KINDS = ("characters", "talked", "endings", "achievements", "rewards", "cards", "runs")


def player_dir(player: str | None = None) -> Path:
    """The player's own folder beside the record (snapshots of characters taken, card pictures, chats)."""
    return HOME / (player or player_id())


def add_card(rec: dict[str, Any]) -> bool:
    """A card a world's ``rewards`` handed out; one per (id, world), never taken back. True = new."""
    return _add("cards", rec, ("id", "world"))


def note_run(root: Path, exit_: dict[str, Any] | None) -> bool:
    """The run reached its exit (settlement): one row per run. True = new."""
    ex = exit_ or {}
    return _add("runs", {"world": world_of(root), "run": Path(root).name, "exit": str(ex.get("kind") or ""),
                         **({"ending": str(ex["id"])} if ex.get("id") else {}), "version": version_of(root)}, ("world", "run"))


def update(kind: str, match: dict[str, Any], fields: dict[str, Any]) -> bool:
    """Change one record in place (a pulled new version); nothing is removed. True = found."""
    with _LOCK:
        d = read()
        hit = next((r for r in d[kind] if all(r.get(k) == v for k, v in match.items())), None)
        if hit is None:
            return False
        hit.update(fields)
        _save(d)
        return True


def unlock_achievement(aid: str, world: str, source: str = "", *, once: bool = False) -> bool:
    """``once``: one per player across every world (「the first ending」); else one per world."""
    return _add("achievements", {"id": str(aid), "world": world, "source": source}, ("id",) if once else ("id", "world"))


def add_reward(rid: str, kind: str, world: str, source: str, **fields: Any) -> bool:
    """A reward earned and waiting for the platform (``status: pending``); ``rid`` keeps it from being earned twice."""
    return _add("rewards", {"id": str(rid), "kind": kind, "world": world, "source": source, **fields, "status": "pending"}, ("id",))


def take(root: Path, iid: str, how: str, *, memory: str = "full") -> bool:
    """The player takes a character home at a settlement (``how`` = settlement · truth_quiz): only one its author lets
    leave (``takeable``); ``memory`` full = with this run's memory, fresh = the character as written. A character already
    taken from this world is not taken again — unless it now comes with its full memory (the record is upgraded)."""
    s = run_souls(root).get(iid)
    if s is None or not s["takeable"]:
        return False
    rec = {"sid": s["sid"], "name": s["name"], "world": world_of(root), "how": how, "memory": memory, "version": version_of(root)}
    if _add("characters", rec, ("sid", "world")):
        if memory == "full":
            _snapshot_of(root, s, rec["world"])
        return True
    if memory != "full":
        return False
    with _LOCK:
        d = read()
        hit = next((r for r in d["characters"] if r.get("sid") == rec["sid"] and r.get("world") == rec["world"]), None)
        if hit is None or hit.get("memory") == "full":
            return False
        hit.update({"memory": "full", "how": how, "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        _save(d)
    _snapshot_of(root, s, rec["world"])
    return True


# ── the run side ─────────────────────────────────────────────────────────────

def world_of(root: Path) -> str:
    """The world a run was made from: its template's id (else the run folder's name)."""
    from neonrp.core.paths import get_data_dir_name

    try:
        rec = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
        if isinstance(rec, dict) and rec.get("id"):
            return str(rec["id"])
    except (OSError, ValueError):
        pass
    return Path(root).name


def version_of(root: Path) -> str:
    """The template version the run was built from ("" when unknown)."""
    from neonrp.core.paths import get_data_dir_name

    try:
        rec = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
        return str(rec.get("version") or "") if isinstance(rec, dict) else ""
    except (OSError, ValueError):
        return ""


TAKE_WHEN = ("companion_at_ending",)  # plus ending:<id>


def take_when_ok(v: Any, endings: set[str] | None = None) -> bool:
    """A ``take_when`` value the engine knows: companion_at_ending, or ending:<id> (an ending of the world when given)."""
    s = str(v or "")
    if s in TAKE_WHEN:
        return True
    return s.startswith("ending:") and bool(s[7:]) and (endings is None or s[7:] in endings)


def free_zone(root: Path) -> bool:
    """The run was made from a Free-Zone work (``zone: open``): what the author uploaded is all there is — no cards, and
    nobody comes home from it (niko 10-18)."""
    from neonrp.core.paths import get_data_dir_name

    try:
        rec = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
        return isinstance(rec, dict) and rec.get("zone") == "open"
    except (OSError, ValueError):
        return False


def run_souls(root: Path) -> dict[str, dict[str, Any]]:
    """instance id → {sid, name, standalone, takeable, take_when} of the run's souls (their soul.json). A Free-Zone run's
    souls are never takeable (:func:`free_zone`) — so no settlement, ending or quiz takes anyone home from it."""
    from neonrp.core.worldmap import cast_ids

    free = free_zone(root)

    out: dict[str, dict[str, Any]] = {}
    sdir = Path(root) / "souls"
    cast = cast_ids(Path(root))  # only the souls this run cast (a world soul not listed stays inactive)
    for d in sorted(sdir.iterdir()) if sdir.is_dir() else []:
        try:
            sj = json.loads((d / "soul.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(sj, dict):
            continue
        from neonrp.core.worldmap import soul_dir_iid

        iid = soul_dir_iid(d)
        if cast is not None and iid not in cast:
            continue
        out[iid] = {"dir": str(d), "sid": str(sj.get("sid") or iid), "name": str(sj.get("name_local") or sj.get("name") or ""),
                    "standalone": sj.get("standalone") is True, "takeable": sj.get("takeable") is not False and not free,
                    "take_when": str(sj.get("take_when") or "companion_at_ending")}
    for eid, e in plot_npcs(root).items():  # 10-18: a plot's own character (the creation desk's mine_N01) is one too
        if eid in out:
            continue
        props = e["props"]
        out[eid] = {"dir": None, "npc": True, "sid": eid, "name": e["name"], "standalone": props.get("standalone") is True,
                    "takeable": props.get("takeable") is not False and not free, "take_when": e["take_when"],
                    **{k: str(props[k]) for k in ("persona", "appearance") if props.get(k)}}
    return out


def take_when_of(rule: dict[str, Any] | None) -> str:
    """A plot's collect rule (template/creation.rules) as a ``take_when``: clear · ending:<id> · flag:<key>; none =
    companion_at_ending."""
    on = (rule or {}).get("on") if rule else None
    if on == "clear":
        return "clear"
    if isinstance(on, dict) and on.get("ending"):
        return f"ending:{on['ending']}"
    if isinstance(on, dict) and on.get("flag"):
        return f"flag:{on['flag']}"
    return "companion_at_ending"


def plot_npcs(root: Path) -> dict[str, dict[str, Any]]:
    """entry id → {name, props, plot, take_when} of the run's plot entries of class ``npc`` (only named ones)."""
    from neonrp.core.paths import get_data_dir_name
    from neonrp.template import creation

    try:
        plots = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "plots.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for pid, info in (plots.items() if isinstance(plots, dict) else []):
        try:
            pdef = json.loads((Path(root) / str((info or {}).get("dir") or "") / "plot.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(pdef, dict):
            continue
        rules = creation.rules(pdef)
        for eid, e in (pdef.get("entries") or {}).items():
            if not isinstance(e, dict) or e.get("class") != "npc":
                continue
            props = e.get("props") if isinstance(e.get("props"), dict) else {}
            name = str(e.get("name") or props.get("name") or "").strip()
            if name and str(eid) not in out:
                out[str(eid)] = {"name": name, "props": props, "plot": pid, "take_when": take_when_of(rules.get(str(eid)) or rules.get(name))}
    return out


def standalone_souls(root: Path) -> dict[str, dict[str, Any]]:
    return {i: s for i, s in run_souls(root).items() if s["standalone"]}


def talked(root: Path, iid: str) -> bool:
    """The player talked with a standalone character: noted (not gained — niko 10-15). True = the first time."""
    s = run_souls(root).get(iid)
    if s is None or not s["standalone"]:
        return False
    return _add("talked", {"sid": s["sid"], "name": s["name"], "world": world_of(root)}, ("sid", "world"))


def gain(root: Path, iid: str, how: str) -> bool:
    """The player takes the character home (with its full memory) when it is ``takeable`` and ``how`` is its
    ``take_when``; the only way a character is gained. True = new. ``how == "talked"`` is :func:`talked`."""
    if how == "talked":
        return talked(root, iid)
    s = run_souls(root).get(iid)
    if s is None or not s["takeable"] or s["take_when"] != how:
        return False
    rec = {"sid": s["sid"], "name": s["name"], "world": world_of(root), "how": how, "memory": "full", "version": version_of(root),
           **({"npc": True} if s.get("npc") else {})}
    new = _add("characters", rec, ("sid", "world"))
    if new:
        _snapshot_of(root, s, rec["world"])
    return new


def collect(root: Path, rows: list[dict[str, Any]] | None) -> list[str]:
    """What a settlement's ``collected`` lists (the plots' collect rules, template/creation.granted: {who, plot, rarity,
    why}) goes into the record: each ``who`` (an instance id, a sid or a name of the run's characters) is gained with
    ``how = collect:<why>``, as written (``memory: fresh`` — like the settlement's floor; three right in the truth quiz, or
    walking home as the companion, still brings the full memory: :func:`take` upgrades the record). A Free-Zone run gains
    nobody (``takeable`` is false). → the iids gained."""
    souls = run_souls(root)
    got = []
    for r in rows or []:
        who = str((r or {}).get("who") or "")
        iid = next((i for i, s in souls.items() if who and who in (i, s["sid"], s["name"])), None)
        if iid is None or not souls[iid]["takeable"]:
            continue
        s = souls[iid]
        rec = {"sid": s["sid"], "name": s["name"], "world": world_of(root), "how": f"collect:{r.get('why') or ''}", "memory": "fresh",
               "version": version_of(root), **({"rarity": r["rarity"]} if r.get("rarity") else {}), **({"npc": True} if s.get("npc") else {})}
        if _add("characters", rec, ("sid", "world")):
            got.append(iid)
    return got


def _snapshot_of(root: Path, s: dict[str, Any], world: str) -> None:
    """The snapshot for a taken character: its soul folder; a plot NPC has none — its folder is made the way the phone
    makes one (core/soul_chat.npc_dir: what the plot says of it, its own memory grows there) and kept from that."""
    if s.get("dir"):
        _snapshot(Path(s["dir"]), world, s["sid"])
    else:
        from neonrp.core import soul_chat
        from neonrp.core.output_lang import prompt_lang

        try:
            src = soul_chat.npc_dir(world, s["sid"], {"name": s["name"], **{k: s[k] for k in ("persona", "appearance") if s.get(k)}}, prompt_lang(root))
        except Exception:  # noqa: BLE001 — no snapshot: the character is still gained (chat falls back to the template)
            return
        _snapshot(Path(src), world, s["sid"])
    try:  # the snapshot's own base for a later author's update (core/soul_update, 10-20)
        from neonrp.core import soul_update

        soul_update.on_take(root, world, s["sid"], source="template" if s.get("dir") else "npc")
    except Exception:  # noqa: BLE001 — never stops a take
        pass


def _snapshot(src: Path, world: str, sid: str) -> None:
    """The taken character's folder as it is at this moment of the run — its full memory, for talking with it later
    (core/soul_chat); its pictures and stickers come along too, so the character does not need its template (10-20)."""
    import shutil

    from neonrp.core.soul_chat import snapshot_dir

    dst = snapshot_dir(world, sid)
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    except OSError:
        pass


def after_turn(root: Path, reports: list[dict[str, Any]]) -> list[str]:
    """A beat's character turns: a standalone character who answered the player in words has talked with them (noted in
    ``talked``, not gained)."""
    got = []
    for r in reports or []:
        if isinstance(r, dict) and r.get("iid") and r.get("kind") == "speak" and str(r.get("text") or "").strip():
            if talked(root, str(r["iid"])):
                got.append(str(r["iid"]))
    return got


def after_ending(root: Path, reg: Any, ended: dict[str, Any]) -> None:
    """An ending landed: it is the player's now, and the characters whose take condition it meets go home with them —
    ``ending:<this id>``, or ``companion_at_ending`` for the ones walking with the player."""
    from neonrp.core import holdings

    eid = str(ended.get("id") or "")
    _add("endings", {"id": eid, "title": str(ended.get("title") or ""), "world": world_of(root)}, ("id", "world"))
    party = holdings.members(root)
    if party is None:
        party = [iid for iid, s in holdings._souls(root).items() if s.get("role") == "companion"]
    here = reg.player_location
    for iid, s in run_souls(root).items():
        if s.get("npc") and s["take_when"] != "companion_at_ending":
            continue  # a plot NPC with a collect rule: the settlement's collected takes it home (collect:<why>, core/sdk)
        if s["take_when"] == f"ending:{eid}":
            gain(root, iid, s["take_when"])
        elif s["take_when"] == "companion_at_ending" and (iid in party or s.get("npc")):  # a plot NPC walks with no party: it stands with the player
            e = reg.entries.get(iid)
            if e is not None and (not here or e.parent == here):
                gain(root, iid, "companion_at_ending")
