"""Turn a world's map into the folder tree.

    uv run python scripts/migrate_map_to_folders.py <world_root>            # dry run: print the plan
    uv run python scripts/migrate_map_to_folders.py <world_root> --write    # do it

Reads the old three sources — ``game/world/world_map.json`` nodes, ``game/towns/<T>/town_map.json`` nodes, flat
``game/locations/*.json`` (and one-level ``game/locations/<id>/`` folders) — and writes one folder per place:

    game/locations/<world node>/location.json
    game/locations/<town>/<spot>/location.json          (a spot's ``parent`` inside the town → one folder deeper)

A flat record that is the same spot as a town-map node (same id, same name, "<town name>·<spot name>", or an engine
alias such as north-gate → gate_north) is merged into that node: the town map's id wins, the other id goes into
``aliases``, the record's own words (summary, tags, notes …) fill what the node lacks, its connections are re-pointed.
A flat record that only names its town ("石津镇·集市广场") becomes a new spot inside it. Other files of a place folder
(notes.md, scene_state.json, assets/) move with it.

Afterwards ``world_map.json`` and each ``town_map.json`` keep everything except ``nodes`` (name, routes, time, travel,
state …), which is what makes the engine read the folders (place_tree.is_tree). A drag saved in ``world_map.json``
``layout`` for a stray world dot that moved into a town is dropped (world units do not fit a town map).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEPS = ("·", "・", "/", " - ", "：", ":")
_LEGACY_ALIASES = {"north-gate": "gate_north"}  # place_nav._ALIASES — the engine already treats these as one spot
_RECORD = "location.json"


def _rj(p: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def _name(d: dict[str, Any], fallback: str) -> str:
    for k in ("name", "name_local", "title", "label"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def _tail(name: str) -> str:
    for sep in _SEPS:
        if sep in name:
            return name.split(sep)[-1].strip()
    return name


def _after_prefix(name: str, wname: str) -> str | None:
    """``"Stone Ford · Market Square"`` under ``"Stone Ford"`` → ``"Market Square"``; also when the place name carries a
    reading in brackets (``"石津(いしづ)の町"`` names ``"石津の町・市場広場"``). None when it is not "<wname><sep><rest>"."""
    for pre in dict.fromkeys([wname, re.sub(r"[（(][^）)]*[）)]", "", wname)]):
        if pre and name != pre and name.startswith(pre):
            rest = name[len(pre):].lstrip()
            for sep in _SEPS:
                if rest.startswith(sep.strip()) and rest[len(sep.strip()):].strip():
                    return rest[len(sep.strip()):].strip()
    return None


@dataclass
class Plan:
    game: Path
    records: dict[str, dict[str, Any]] = field(default_factory=dict)   # rel folder ("T001/gate_north") → record
    moves: list[tuple[Path, Path]] = field(default_factory=list)       # extra files of an old place folder
    removes: list[Path] = field(default_factory=list)                  # old flat files / emptied folders
    strips: dict[Path, dict[str, Any]] = field(default_factory=dict)   # map file → its content without nodes
    notes: list[str] = field(default_factory=list)

    def rec(self, rel: str) -> dict[str, Any]:
        return self.records.setdefault(rel, {})


def plan_world(root: Path) -> Plan:
    game = root / "game"
    plan = Plan(game)
    wm_path = game / "world" / "world_map.json"
    wm = _rj(wm_path)
    if wm is None or not isinstance(wm.get("nodes"), list):
        plan.notes.append("already a folder tree (or no world_map.json) — nothing to do")
        return plan

    # ── world level ──
    routes = {str(r["id"]): (str(r.get("from")), str(r.get("to"))) for r in wm.get("routes") or []
              if isinstance(r, dict) and r.get("id") and r.get("from") and r.get("to")}
    wnodes = {str(n["id"]): n for n in wm["nodes"] if isinstance(n, dict) and n.get("id")}
    wfolder: dict[str, str] = {}

    def world_rel(nid: str, seen: frozenset = frozenset()) -> str:
        n = wnodes[nid]
        up = str(n.get("parent") or "")
        if up and up in wnodes and up not in seen:
            return f"{world_rel(up, seen | {nid})}/{nid}"
        return nid

    for nid, n in wnodes.items():
        rel = world_rel(nid)
        wfolder[nid] = rel
        conns: list[str] = []
        for link in n.get("links") or []:
            link = str(link)
            ends = routes.get(link)
            others = [e for e in ends if e != nid] if ends else [link]
            for o in others:
                if o in wnodes and o != nid and o not in conns:
                    conns.append(o)
        for r in routes.values():  # a route the node's links forgot still joins it
            if nid in r:
                o = r[1] if r[0] == nid else r[0]
                if o in wnodes and o not in conns:
                    conns.append(o)
        rec = plan.rec(rel)
        rec.update({k: v for k, v in n.items() if k not in ("links", "parent")})
        rec["connections"] = conns

    # ── towns ──
    town_nodes: dict[str, dict[str, dict[str, Any]]] = {}
    town_rel: dict[str, dict[str, str]] = {}
    towns_dir = game / "towns"
    for td in sorted(towns_dir.iterdir()) if towns_dir.is_dir() else []:
        tm = _rj(td / "town_map.json") if td.is_dir() else None
        if tm is None or not isinstance(tm.get("nodes"), list):
            continue
        tid = str(tm.get("town_id") or td.name)
        base = wfolder.get(tid)
        if base is None:
            base = tid
            tj = _rj(td / "town.json") or {}
            plan.rec(base).update({"id": tid, "name": _name(tj, tid), "type": "town"})
            plan.rec(base).setdefault("connections", [])
            plan.notes.append(f"town {tid} is not a world_map node — made a top folder for it")
        nodes = {str(n["id"]): n for n in tm["nodes"] if isinstance(n, dict) and n.get("id")}
        town_nodes[tid] = nodes

        def spot_rel(sid: str, seen: frozenset = frozenset(), nodes=nodes, base=base) -> str:
            up = str(nodes[sid].get("parent") or "")
            if up and up in nodes and up not in seen:
                return f"{spot_rel(up, seen | {sid})}/{sid}"
            return f"{base}/{sid}"

        town_rel[tid] = {}
        for sid, n in nodes.items():
            rel = spot_rel(sid)
            town_rel[tid][sid] = rel
            rec = plan.rec(rel)
            rec.update({k: v for k, v in n.items() if k not in ("links", "parent")})
            rec["connections"] = [str(x) for x in n.get("links") or [] if x]
        plan.strips[td / "town_map.json"] = {k: v for k, v in tm.items() if k != "nodes"}

    # ── flat records ──
    world_names = {nid: _name(n, nid) for nid, n in wnodes.items()}
    alias: dict[str, dict[str, str]] = {tid: {} for tid in town_nodes}   # town → {old id: town-map id}
    ldir = game / "locations"
    flat: list[tuple[str, dict[str, Any], Path]] = []
    for child in sorted(ldir.iterdir()) if ldir.is_dir() else []:
        if child.is_dir() and (child / _RECORD).is_file():
            d = _rj(child / _RECORD) or {}
            flat.append((str(d.get("id") or child.name), d, child))
        elif child.suffix == ".json" and child.name not in ("scene_state.json", "map.json"):
            d = _rj(child)
            if d:
                flat.append((str(d.get("id") or child.stem), d, child))

    def owner(fid: str, d: dict[str, Any]) -> tuple[str, str | None] | None:
        """(town or world node, same-spot town-map id or None)."""
        name, tail = _name(d, fid), _tail(_name(d, fid))
        hint = str(d.get("town") or "") or str(d.get("parent") or "").partition("/")[0] or None
        order = ([hint] if hint in town_nodes else []) + [t for t in town_nodes if t != hint]
        canon = _LEGACY_ALIASES.get(fid, fid)
        for t in order:  # the same spot first: a grown place the town map already registered under its own id
            for sid, n in town_nodes[t].items():
                if canon == sid or name == _name(n, sid) or (tail and tail == _name(n, sid)):
                    return t, sid
        if hint in town_nodes:
            return hint, None
        for key in ("parent", "within"):
            v = str(d.get(key) or "")
            if v in wnodes:
                return v, None
            for t in town_nodes:
                if v in town_nodes[t]:
                    return t, None
        for wid, wname in world_names.items():
            if wname and _after_prefix(name, wname):
                return wid, None
        return None

    def strip_town_prefix(name: str, t: str) -> str:
        return _after_prefix(name, world_names.get(t, "")) or name

    new_kids: list[tuple[str, str]] = []  # (town, rel)
    for fid, d, path in flat:
        if fid in wfolder:  # a world node's own record
            rel, merge_into = wfolder[fid], True
            target_id = fid
        else:
            o = owner(fid, d)
            if o is None:
                rel, merge_into, target_id = fid, False, fid
                plan.notes.append(f"{fid}: no town says it is inside — stays a world place")
            elif o[1] is not None:
                rel, merge_into, target_id = town_rel[o[0]][o[1]], True, o[1]
                if fid != o[1]:
                    alias[o[0]][fid] = o[1]
                    plan.notes.append(f"{fid} = {o[0]}/{o[1]} (merged, kept as alias)")
            else:
                t = o[0]
                # in a town a record's ``parent`` is the spot it hangs off (the engine made it a road), not "inside" —
                # layers come from the town map's own ``parent``, which the same-spot merge above already carries
                rel, merge_into, target_id = f"{wfolder.get(t, t)}/{fid}", False, fid
                if t in town_nodes:
                    new_kids.append((t, rel))
                plan.notes.append(f"{fid}: new place inside {t} → locations/{rel}")
        rec = plan.rec(rel)
        if merge_into:
            for k, v in d.items():
                if k in ("id", "connections", "parent", "town", "within"):
                    continue
                if k == "name" and rec.get("name"):
                    continue
                rec.setdefault(k, v)
            if fid != target_id:
                rec["aliases"] = sorted({*map(str, rec.get("aliases") or []), fid})
            rec["connections"] = list(dict.fromkeys([*rec.get("connections", []), *map(str, d.get("connections") or [])]))
        else:
            rec.update({k: v for k, v in d.items() if k not in ("parent", "town", "within")})
            if "/" in rel:
                town = rel.split("/")[0]
                rec["name"] = strip_town_prefix(_name(d, fid), town)
            rec["id"] = target_id
            hang = str(d.get("parent") or "").rpartition("/")[2]
            hang = hang if hang in town_nodes.get(rel.split("/")[0], {}) else ""  # only a sibling spot is a road
            rec["connections"] = list(dict.fromkeys([*(str(c) for c in d.get("connections") or []), *([hang] if hang else [])]))
        dest = game / "locations" / rel
        if path.is_dir():
            for f in sorted(path.rglob("*")):
                if f.is_file() and f.name != _RECORD:
                    to = dest / f.relative_to(path)
                    if f != to:
                        plan.moves.append((f, to))
            if path != dest:
                plan.removes.append(path)
        else:
            plan.removes.append(path)

    # ── re-point connections at merged ids; join new spots back from the places they name ──
    for rel, rec in plan.records.items():
        parts = rel.split("/")
        town = parts[0]
        amap = {**_LEGACY_ALIASES, **alias.get(town, {})} if len(parts) > 1 else {}
        rec["connections"] = list(dict.fromkeys(amap.get(c, c) for c in rec.get("connections") or [] if c != parts[-1]))
        rec["id"] = parts[-1]  # the folder name is the id; other names for the spot live in aliases
    siblings: dict[str, dict[str, str]] = {}
    for rel in plan.records:
        up, _, leaf = rel.rpartition("/")
        siblings.setdefault(up, {})[leaf] = rel
    from neonrp.core.locations import _town_pos

    for _t, rel in new_kids:
        up, _, leaf = rel.rpartition("/")
        for c in plan.records[rel]["connections"]:
            other = siblings.get(up, {}).get(c)
            if other and leaf not in plan.records[other]["connections"]:
                plan.records[other]["connections"].append(leaf)
        if "pos" not in plan.records[rel]:  # beside the first place it joins, clear of the others (the engine's own rule)
            peers = [r for k, r in siblings.get(up, {}).items() if k != leaf and isinstance(plan.records[r].get("pos"), dict)]
            anchor = next((plan.records[siblings[up][c]] for c in plan.records[rel]["connections"] if c in siblings.get(up, {})
                           and isinstance(plan.records[siblings[up][c]].get("pos"), dict)), None)
            if peers:
                plan.records[rel]["pos"] = _town_pos([plan.records[r] for r in peers], anchor)

    # ── layout keys ──
    stripped = {k: v for k, v in wm.items() if k != "nodes"}
    layout = wm.get("layout") if isinstance(wm.get("layout"), dict) else None
    if layout:
        # a drag saved for a stray world-map dot is in world units; the spot now sits on its town's map (pixels) —
        # the position does not carry over, so the drag is dropped (the spot keeps its own pos)
        moved = {old for amap in alias.values() for old in amap} | {rel.rsplit("/", 1)[1] for _t, rel in new_kids}
        dropped = sorted(k for k in layout if k in moved)
        if dropped:
            plan.notes.append(f"layout: dropped world-map drags of spots that moved into a town: {dropped}")
        stripped["layout"] = {k: v for k, v in layout.items() if k not in moved}
    plan.strips[wm_path] = stripped
    return plan


def apply(plan: Plan) -> list[Path]:
    from neonrp.core.storage import atomic_write_json

    written: list[Path] = []
    for src, dst in plan.moves:
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
    for rel, rec in sorted(plan.records.items()):
        p = plan.game / "locations" / rel / _RECORD
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, rec)
        written.append(p)
    for path, doc in plan.strips.items():
        atomic_write_json(path, doc)
        written.append(path)
    for p in plan.removes:
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            leftover = [f for f in p.rglob("*") if f.is_file() and f.name not in (_RECORD, ".DS_Store")]
            if not leftover:
                shutil.rmtree(p)
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("world_root", type=Path)
    ap.add_argument("--write", action="store_true", help="apply (default: dry run)")
    a = ap.parse_args()
    plan = plan_world(a.world_root.resolve())
    for n in plan.notes:
        print("·", n)
    print(f"{len(plan.records)} place folders, {len(plan.moves)} files moved, {len(plan.removes)} old records removed, "
          f"{len(plan.strips)} map files keep their other keys")
    for rel in sorted(plan.records):
        r = plan.records[rel]
        extra = f"  aliases={r['aliases']}" if r.get("aliases") else ""
        print(f"  locations/{rel}/  {r.get('name', '')}  → {r.get('connections')}{extra}")
    if not a.write:
        print("\n(dry run — add --write to apply)")
        return 0
    if not plan.records:
        return 0
    apply(plan)
    print("written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
