"""The town map as a graph of layers (rpg map tool). ``town_map.json`` nodes carry ``links`` (roads, one layer only)
and an optional ``parent`` (the node they sit inside). Every edit here is checked so the map still draws."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.core.locations import _link, _read_json, _town_dir_for, _town_pos, _write_json, location_record_path

# ── town-map edges (「不仅点上能新增点,还可以两点中间新建新的点,以及在这个点上再新连边」) ──


def _town_map(root: Path, town: str) -> tuple[Path | None, dict[str, Any]]:
    """(where the town's map lives, its town_map-shaped doc) — town_map.json or the town's place folders (place_tree)."""
    from neonrp.core import place_tree

    if _town_dir_for(root, town) is None:
        return None, {}
    folders = place_tree.level_in_folders(root, town)
    path = (place_tree.locations_dir(root) / town) if folders else place_tree.town_map_file(root, town)
    return path, (place_tree.level_doc(root, town) or {})


def _save(root: Path, town: str, data: dict[str, Any]) -> None:
    from neonrp.core import place_tree

    place_tree.save_level_doc(root, town, data)


def town_edge(root: Path, town: str, a: str, b: str, *, add: bool) -> list[str]:
    """Add / drop the edge a–b on ``town``'s map (node ids), both ends, plus the places' own records. Paths written."""
    path, data = _town_map(root, town)
    if path is None:
        return []
    by_id = {str(n.get("id")): n for n in data.get("nodes") or [] if isinstance(n, dict)}
    if a not in by_id or b not in by_id or a == b:
        return []
    changed = False
    for x, y in ((a, b), (b, a)):
        links = [str(v) for v in by_id[x].get("links") or [] if v]
        if add and y not in links:
            links.append(y)
            changed = True
        elif not add and y in links:
            links.remove(y)
            changed = True
        by_id[x]["links"] = links
    written: list[str] = []
    if changed:
        _save(root, town, data)
        written.append(str(path.relative_to(root)) if path.is_relative_to(root) else str(path))
    for x, y in ((a, b), (b, a)):
        p = _link(root, y, x, add=add)
        if p:
            written.append(str(p.relative_to(root)) if p.is_relative_to(root) else str(p))
    return written


def town_linked(root: Path, town: str, a: str, b: str) -> bool:
    _, data = _town_map(root, town)
    n = next((x for x in data.get("nodes") or [] if isinstance(x, dict) and str(x.get("id")) == a), None)
    return bool(n and b in [str(v) for v in n.get("links") or []])


def town_stays_whole(root: Path, town: str, a: str, b: str) -> bool:
    """Without the edge a–b, can one still walk from a to b? (cutting a road must not cut a part of town off;
    nodes that were never connected — a record with no links yet — are not this edge's business)"""
    _, data = _town_map(root, town)
    adj = {str(n.get("id")): {str(v) for v in n.get("links") or []} for n in data.get("nodes") or [] if isinstance(n, dict)}
    adj.get(a, set()).discard(b)
    adj.get(b, set()).discard(a)
    seen, todo = {a}, [a]
    while todo:
        for y in adj.get(todo.pop(), set()):
            if y in adj and y not in seen:
                seen.add(y)
                todo.append(y)
    return b in seen


def town_place_between(root: Path, town: str, x: str, a: str, b: str) -> None:
    """Put the node x half-way between a and b (nudged clear of the others)."""
    path, data = _town_map(root, town)
    nodes = [n for n in data.get("nodes") or [] if isinstance(n, dict)]
    by_id = {str(n.get("id")): n for n in nodes}
    if path is None or not {x, a, b} <= set(by_id):
        return
    try:
        ax, ay, bx, by = (float(by_id[a]["pos"]["x"]), float(by_id[a]["pos"]["y"]), float(by_id[b]["pos"]["x"]), float(by_id[b]["pos"]["y"]))
    except (KeyError, TypeError, ValueError):
        return
    others = [(float(n["pos"]["x"]), float(n["pos"]["y"])) for n in nodes
              if str(n.get("id")) != x and isinstance(n.get("pos"), dict) and {"x", "y"} <= set(n["pos"])]
    mx, my = (ax + bx) / 2, (ay + by) / 2
    dx, dy = -(by - ay), bx - ax  # perpendicular, for a nudge
    norm = max((dx * dx + dy * dy) ** 0.5, 1.0)
    for k in (0, 1, -1, 2, -2, 3, -3):
        px, py = mx + dx / norm * 40 * k, my + dy / norm * 40 * k
        if all((px - ox) ** 2 + (py - oy) ** 2 >= 45 ** 2 for ox, oy in others):
            break
    by_id[x]["pos"] = {"x": round(px), "y": round(py)}
    _save(root, town, data)


# ── town-map layers (「新增地点要说它在哪一层:和谁同层、是谁的 parent / children、最近的是哪几个」) ──
# A town map is a tree of layers: a node's optional "parent" (another node id of the same map) puts it one layer down,
# inside that node; no parent = the town's own layer. Edges ("links") only join nodes of one layer; going up / down is
# always through the parent (a cellar is entered from the guild, never from the street).

RELATIONS = ("near", "between", "in", "over")


def town_layer(data: dict[str, Any], node: str) -> str | None:
    n = next((x for x in data.get("nodes") or [] if isinstance(x, dict) and str(x.get("id")) == node), None)
    return str(n["parent"]) if n and n.get("parent") else None


def check_town_tree(data: dict[str, Any]) -> list[str]:
    """What would stop the map from being drawn: an unknown parent, a cycle, an edge across layers."""
    by_id = {str(n.get("id")): n for n in data.get("nodes") or [] if isinstance(n, dict) and n.get("id")}
    probs: list[str] = []
    for nid, n in by_id.items():
        p, seen = n.get("parent"), {nid}
        while p:
            if p not in by_id:
                probs.append(f"{nid} 的上一层 {p} 不存在")
                break
            if p in seen:
                probs.append(f"{nid} 的层级成环")
                break
            seen.add(p)
            p = by_id[p].get("parent")
        for lk in n.get("links") or []:
            if lk in by_id and (by_id[lk].get("parent") or None) != (n.get("parent") or None):
                probs.append(f"{nid}–{lk} 跨了层(路只连同一层)")
    return probs


def town_rehang(root: Path, town: str, x: str, rel: str, targets: list[str]) -> tuple[bool, str]:
    """Put node x into the tree by one relation, replacing its edges and layer:
    near=A[,B] same layer as A, joined to them · between=A,B on the A–B road · in=A one layer down, inside A ·
    over=A,B one layer up: x becomes their parent, and their roads out of the group move onto x.
    All-or-nothing: the map is written only when the result still draws (``check_town_tree``)."""
    import copy

    path, data = _town_map(root, town)
    if path is None:
        return False, f"no town map for {town}"
    new = copy.deepcopy(data)
    by_id = {str(n.get("id")): n for n in new.get("nodes") or [] if isinstance(n, dict)}
    if x not in by_id:
        return False, f"{x} 不在 {town} 的地图上"
    ts = [t for t in targets if t]
    if rel not in RELATIONS or not ts:
        return False, f"关系要写 {'/'.join(RELATIONS)} 之一和至少一个地点"
    miss = [t for t in ts if t not in by_id or t == x]
    if miss:
        return False, f"不认识的地点 {miss}"
    if rel == "between" and len(ts) != 2:
        return False, "between 要两个地点"
    if rel == "in" and len(ts) != 1:
        return False, "in 只写一个地点"
    layers = {(by_id[t].get("parent") or None) for t in ts}
    if rel in ("near", "between", "over") and len(layers) != 1:
        return False, "这几个地点不在同一层"

    def drop_edges(n: str) -> None:
        for y in list(by_id[n].get("links") or []):
            if y in by_id:
                by_id[y]["links"] = [v for v in by_id[y].get("links") or [] if v != n]
        by_id[n]["links"] = []

    def join(a: str, b: str) -> None:
        for p, q in ((a, b), (b, a)):
            ls = [str(v) for v in by_id[p].get("links") or []]
            if q not in ls:
                ls.append(q)
            by_id[p]["links"] = ls

    drop_edges(x)
    if rel in ("near", "between"):
        by_id[x]["parent"] = by_id[ts[0]].get("parent")
        if rel == "between":
            a, b = ts
            by_id[a]["links"] = [v for v in by_id[a].get("links") or [] if v != b]
            by_id[b]["links"] = [v for v in by_id[b].get("links") or [] if v != a]
        for t in ts:
            join(x, t)
    elif rel == "in":
        by_id[x]["parent"] = ts[0]
    else:  # over
        layer = by_id[ts[0]].get("parent")
        if any(_is_under(by_id, t, x) for t in ts):
            return False, "不能把自己的上层包进来"
        by_id[x]["parent"] = layer
        group = set(ts)
        for t in ts:
            for y in list(by_id[t].get("links") or []):
                if y in by_id and y not in group:
                    by_id[t]["links"] = [v for v in by_id[t]["links"] if v != y]
                    by_id[y]["links"] = [v for v in by_id[y].get("links") or [] if v != t]
                    join(x, y)
            by_id[t]["parent"] = x
    if not by_id[x].get("parent"):
        by_id[x].pop("parent", None)
    probs = check_town_tree(new)
    if probs:
        return False, ";".join(probs[:3])
    nodes = [n for n in new.get("nodes") or [] if isinstance(n, dict)]
    peers = [n for n in nodes if (n.get("parent") or None) == (by_id[x].get("parent") or None) and str(n.get("id")) != x]
    if rel == "between":
        _save(root, town, new)
        town_place_between(root, town, x, ts[0], ts[1])
    else:
        if rel == "over":
            pts = [by_id[t]["pos"] for t in ts if isinstance(by_id[t].get("pos"), dict)]
            if pts:
                by_id[x]["pos"] = {"x": round(sum(p["x"] for p in pts) / len(pts)), "y": round(sum(p["y"] for p in pts) / len(pts))}
        else:  # near: beside the first; in: the first child sits at its parent's spot, later ones beside their siblings
            kids = [n for n in nodes if n.get("parent") == ts[0] and str(n.get("id")) != x] if rel == "in" else []
            anchor = by_id[ts[0]] if rel == "near" or not kids else kids[0]
            by_id[x]["pos"] = _town_pos(peers if rel == "near" else kids, anchor) if (rel == "near" or kids) else dict(by_id[ts[0]].get("pos") or {"x": 100, "y": 100})
        _save(root, town, new)
    rec = location_record_path(root, x)
    if rec is not None:
        d = _read_json(rec)
        d["connections"] = list(by_id[x].get("links") or [])
        if by_id[x].get("parent"):
            d["within"] = by_id[x]["parent"]
        else:
            d.pop("within", None)
        _write_json(rec, d)
    return True, ""


def _is_under(by_id: dict[str, Any], a: str, b: str) -> bool:
    """Is a one of b's ancestors (b's parent chain reaches a)?"""
    p, seen = by_id.get(b, {}).get("parent"), set()
    while p and p not in seen:
        if p == a:
            return True
        seen.add(p)
        p = by_id.get(p, {}).get("parent")
    return False

