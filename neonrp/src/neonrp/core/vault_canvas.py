"""`世界.canvas` — the world drawn as containment, not as a flat graph.

Obsidian's graph view puts every note on one plane; a world is not flat.
Places contain people, the world contains places: "把我们
的数据能兼顾通过层级来显示包容关系,而不是直接把所有可视化都统一成平级
关系" — and it should show the pictures.

JSON Canvas (`.canvas`, a core Obsidian feature, open spec) gives both with
no plugin: a **group** node encloses whatever lies inside its rectangle, a
**file** node renders a note or an image as a card. So the hierarchy is
geometry — this module is a small deterministic layout engine:

    world group
      ├─ cover image
      ├─ place group ─ place card · soul cards (portrait renders in the card)
      ├─ place group ─ …
      └─ 在路上 group ─ souls whose location resolves to no place page

plus edges: soul → soul for relationships (labelled with the disposition) and
place → place for roads. Ids are hashes of stable keys so a re-projection
changes only what moved.

Sizes are in canvas units (pixels at zoom 1). Cards are portrait-shaped so a
soul's picture sits above its facts the way a character sheet would.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

CANVAS_FILENAME = "世界.canvas"

CARD_W = 300
CARD_H = 380
PLACE_CARD_H = 200
COVER_W = 360
COVER_H = 360
GAP = 40
PAD = 40
LABEL_H = 56  # room under a group's label so cards do not overlap it
CARDS_PER_ROW = 4
UNPLACED_LABEL = "在路上"

# Obsidian's six preset colours: "1" red · "2" orange · "3" yellow · "4" green
# · "5" cyan · "6" purple. Named here once so the palette is one decision.
_COLOR_WORLD = "5"
_COLOR_PLACE = "4"
_COLOR_UNPLACED = "2"


@dataclass
class SoulCard:
    key: str
    note: str
    name: str


@dataclass
class PlaceBox:
    key: str
    label: str
    note: str | None  # None: a named spot with no location page of its own
    souls: list[SoulCard] = field(default_factory=list)
    connections: list[str] = field(default_factory=list)  # other place keys


def _nid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _card(kind: str, key: str, x: int, y: int, w: int, h: int, **extra: Any) -> dict[str, Any]:
    node = {"id": _nid(kind, key), "x": x, "y": y, "width": w, "height": h}
    node.update(extra)
    return node


def _layout_box(
    label: str,
    key: str,
    place_note: str | None,
    souls: list[SoulCard],
    color: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One group with its cards laid out inside, positioned at the origin.

    Returns the group node (to be offset by the caller) and its children,
    all relative to (0, 0).
    """
    items: list[tuple[str, str, int]] = []  # (kind, key, height)
    if place_note:
        items.append(("place", key, PLACE_CARD_H))
    for soul in sorted(souls, key=lambda s: (s.name, s.key)):
        items.append(("soul", soul.key, CARD_H))
    cols = max(1, min(CARDS_PER_ROW, len(items)))
    rows = max(1, math.ceil(len(items) / cols))
    inner_w = cols * CARD_W + (cols - 1) * GAP
    inner_h = rows * CARD_H + (rows - 1) * GAP if items else 80
    width = inner_w + 2 * PAD
    height = LABEL_H + inner_h + PAD

    children: list[dict[str, Any]] = []
    soul_by_key = {s.key: s for s in souls}
    for index, (kind, item_key, h) in enumerate(items):
        col, row = index % cols, index // cols
        x = PAD + col * (CARD_W + GAP)
        y = LABEL_H + row * (CARD_H + GAP)
        if kind == "place":
            children.append(_card("place", item_key, x, y, CARD_W, h, type="file", file=place_note))
        else:
            children.append(
                _card("soul", item_key, x, y, CARD_W, h, type="file", file=soul_by_key[item_key].note)
            )
    if not items:
        children.append(
            _card("empty", key, PAD, LABEL_H, CARD_W, 60, type="text", text="此刻无人")
        )
        width = CARD_W + 2 * PAD
    group = _card("group", key, 0, 0, width, height, type="group", label=label, color=color)
    return group, children


def _offset(nodes: list[dict[str, Any]], dx: int, dy: int) -> None:
    for node in nodes:
        node["x"] += dx
        node["y"] += dy


def build_canvas(
    world_name: str,
    cover: str | None,
    places: list[PlaceBox],
    unplaced: list[SoulCard],
    relations: list[tuple[str, str, str]],
) -> dict[str, Any]:
    """Assemble the canvas document. Pure: same input, same bytes."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    boxes: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for place in sorted(places, key=lambda p: (p.label, p.key)):
        boxes.append(_layout_box(place.label, place.key, place.note, place.souls, _COLOR_PLACE))
    if unplaced:
        boxes.append(_layout_box(UNPLACED_LABEL, "__unplaced__", None, unplaced, _COLOR_UNPLACED))

    # Flow the boxes into a near-square grid inside the world group.
    x0 = PAD
    y0 = LABEL_H
    if cover:
        nodes.append(_card("cover", "world", x0, y0, COVER_W, COVER_H, type="file", file=cover))
        y0 += COVER_H + GAP
    per_row = max(1, math.ceil(math.sqrt(len(boxes)))) if boxes else 1
    x, y = x0, y0
    row_h = 0
    max_x = x0 + (COVER_W if cover else 0)
    for index, (group, children) in enumerate(boxes):
        if index and index % per_row == 0:
            x = x0
            y += row_h + GAP
            row_h = 0
        _offset([group, *children], x, y)
        nodes.append(group)
        nodes.extend(children)
        x += group["width"] + GAP
        row_h = max(row_h, group["height"])
        max_x = max(max_x, group["x"] + group["width"])
    world_w = max_x + PAD
    world_h = y + row_h + PAD if boxes else y0 + PAD
    nodes.insert(
        0,
        _card("world", "world", 0, 0, world_w, world_h, type="group", label=world_name, color=_COLOR_WORLD),
    )

    # Roads between places, each pair once.
    place_keys = {p.key for p in places}
    seen: set[tuple[str, str]] = set()
    for place in places:
        for other in place.connections:
            if other not in place_keys or other == place.key:
                continue
            pair = tuple(sorted((place.key, other)))
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(
                {
                    "id": _nid("road", *pair),
                    "fromNode": _nid("group", pair[0]),
                    "toNode": _nid("group", pair[1]),
                    "fromEnd": "none",
                    "toEnd": "none",
                    "label": "通向",
                }
            )

    # Relationships, soul → soul, only when both stand somewhere on the canvas.
    soul_keys = {s.key for p in places for s in p.souls} | {s.key for s in unplaced}
    for src, dst, label in sorted(relations):
        if src not in soul_keys or dst not in soul_keys or src == dst:
            continue
        edge = {"id": _nid("rel", src, dst), "fromNode": _nid("soul", src), "toNode": _nid("soul", dst)}
        if label:
            edge["label"] = label
        edges.append(edge)

    return {"nodes": nodes, "edges": edges}


def contains(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
    """Geometric containment — the only kind Obsidian knows."""
    return (
        outer["x"] <= inner["x"]
        and outer["y"] <= inner["y"]
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
    )
