"""Drawing the map (rpg map tool): ``[~map]`` from state, the level the player is on, never the model's imagination."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.packs.rpg.i18n import t as _t

def draw_map(root: Path, reg: Any, op: dict[str, Any], res: Any = None, *, seed: str = "") -> dict[str, Any]:
    """``[map]`` — the engine draws where the player is, from state (never from the model's imagination):
    a town place with its exits (two hops), a dungeon with its rooms (unexplored beyond one hop as [???]),
    or the road between two towns with the journey's day and stop. Returned as a panel (shown to the player)."""
    here = reg.entries.get(reg.player_location or "")
    if here is None:
        return {"ok": False, "why": _t(root, "where_unknown")}
    lines: list[str] = []
    if here.cls == "road":
        from neonrp.packs.rpg import travel

        j = travel.journey(root) or {}
        a, b = reg.entries.get(str(j.get("from"))), reg.entries.get(str(j.get("to")))
        day, days = int(j.get("day") or 0), int(j.get("days") or 0)
        bar = "".join("●" if i < day else "○" for i in range(max(days, 1)))
        st = j.get("pending")
        an, bn = (a.name if a else str(j.get("from"))), (b.name if b else str(j.get("to")))
        lines += [_t(root, "map_road_head", a=an, b=bn), _t(root, "map_road_bar", a=an, b=bn, bar=bar, d=day, days=days),
                  _t(root, "map_you_road", what=_t(root, "map_stopped", text=st.get("text")) if st else _t(root, "map_settled")),
                  _t(root, "map_back_fwd", d=day, a=an, left=max(0, days - day))]
    elif here.cls == "room":
        dg = reg.entries.get(here.parent or "")
        lines.append(f"── {dg.name if dg else here.parent} ──")
        seen = {here.id}
        lines.append(_t(root, "map_here", name=here.name, id=here.id.split("/")[-1]))
        for x in reg.exits(here.id):
            seen.add(x.id)
            st = x.props.get("state") if isinstance(x.props.get("state"), dict) else {}
            known = st.get("explored") or st.get("cleared")
            lines.append(f"  │── {x.name if known else '[???]'}({x.id.split('/')[-1]})" + _t(root, "map_explored" if known else "map_unexplored"))
            for y in reg.exits(x.id):
                if y.id not in seen:
                    seen.add(y.id)
                    lines.append(f"  │     └── [???]({y.id.split('/')[-1]})")
        rest = [r for r in reg.of_class("room") if r.parent == here.parent and r.id not in seen]
        if rest:
            lines.append(_t(root, "map_deeper", n=len(rest)))
    else:
        town = reg.entries.get(reg.current_town or "")
        lines.append(f"── {town.name if town else here.parent or ''} ──")
        lines.append(_t(root, "map_here", name=here.name, id=here.id.split("/")[-1]))
        for x in reg.exits(here.id):
            far = "、".join(f"{y.name}" for y in reg.exits(x.id) if y.id != here.id)[:60]
            lines.append(f"  ├── {x.name}({x.id.split('/')[-1]})" + (f" → {far}" if far else ""))
        present = [e for e in [*reg.of_class("soul"), *reg.of_class("npc")] if e.parent == here.id]
        if present:
            lines.append(_t(root, "map_present", names=", ".join(e.name for e in present)))
        from neonrp.packs.rpg import travel as _trv

        far_towns = []
        for t in sorted(reg.of_class("town"), key=lambda e: e.id):
            if t.id != reg.current_town:
                d = _trv.route_days(root, reg.current_town or "", t.id) if reg.current_town else None
                if d is not None:
                    far_towns.append(f"{t.name}({_t(root, 'map_today') if d == 0 else _t(root, 'map_days', n=d)})")
        if far_towns:
            lines.append(_t(root, "map_far", towns=", ".join(far_towns)))
    text = "\n".join(lines)
    from neonrp.core import panels as _panels

    fmt = (_panels.declared(root).get("map") or {}).get("format", "text")
    value: dict[str, Any] = {"id": "map", "format": "text", "source": "tool", "text": text}
    if fmt in ("json", "image"):
        data = _map_data(root, reg, here, image=(fmt == "image"))
        if data:
            value = {"id": "map", "format": fmt, "source": "tool", "data": data, "text": text}
    return {"ok": True, "text": text, "panel": "map", "panel_value": value, "request": "map"}


def _map_data(root: Path, reg: Any, here: Any, *, image: bool) -> dict[str, Any] | None:
    """The world-map level the player is on (core/worldmap tree): nodes with positions, edges, the player's pin and marks
    (people here, the road's progress). ``image`` adds the level's generated picture + hotspots when it exists."""
    try:
        from neonrp.core import worldmap
    except Exception:  # noqa: BLE001 — the layered map is optional
        return None
    try:
        tree = worldmap.build_map_tree(root)
    except Exception:  # noqa: BLE001
        return None
    nodes = tree.get("nodes") or {}
    addr = here.id if here.id in nodes else (here.parent if here.parent in nodes else None)
    if here.cls == "road":
        level = next((a for a in nodes if (nodes[a].get("parent") is None)), None)
        pin = None
    else:
        level = (nodes.get(addr) or {}).get("parent") if addr else None
        pin = addr
    if not level or level not in nodes:
        return None
    kids = nodes[level].get("children") or []
    data: dict[str, Any] = {
        "level": level, "kind": worldmap.level_kind(tree, level) if hasattr(worldmap, "level_kind") else None,
        "nodes": [{"addr": c, "name": nodes[c].get("name"), "kind": nodes[c].get("kind"), "pos": nodes[c].get("pos")} for c in kids],
        "edges": [e for e in (nodes[level].get("edges") or [])],
        "here": pin,
        "marks": [{"addr": e.parent, "id": e.id, "name": e.name, "kind": e.cls} for e in [*reg.of_class("soul"), *reg.of_class("npc")] if e.parent in kids],
    }
    if here.cls == "road":
        from neonrp.packs.rpg import travel

        j = travel.journey(root) or {}
        data["road"] = {"from": j.get("from"), "to": j.get("to"), "day": j.get("day"), "days": j.get("days"), "stop": (j.get("pending") or {}).get("text")}
    if image:
        try:
            img = worldmap.map_image_path(root, level)
            if img.exists():
                data["image"] = str(img.relative_to(root))
                data["hotspots"] = worldmap.hotspots(root, tree, level)
        except Exception:  # noqa: BLE001
            pass
    return data
