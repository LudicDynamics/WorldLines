"""The rpg map tool (「把这个连接图当成一个地图工具,做成 RPG 的一个子模块」).

One graph, kept drawable: towns hold places, places may hold places (layers), roads join one layer.
The narrator only proposes; every change is checked here and written by the engine.

    move.py    move <who> <where>: two-beat travel, dungeon entry, a place the map lacks grows first
    places.py  new_location (near / between / in / over) · link · unlink — validators and handlers
    graph.py   the town map's tree: edges, layers, re-hanging, the drawability check
    draw.py    [~map]: the level the player is on, from state
    fix.py     after the reply: places grown without a readable relation are placed from the prose

The ops below are this tool's registry entries; the rpg pack lists them in its ACTIONS.
"""
from __future__ import annotations

from neonrp import prompts
from neonrp.core.registry import ActionSpec

_OPS = {lg: prompts.strings("rpg_pack", lg) for lg in ("zh", "en", "ja", "ko")}  # op docs: prompts/rpg_pack.<lang>.json (four languages, 10-16)


def _op_zh(key: str) -> str:
    return _OPS["zh"][key]


def _op_i18n(key: str) -> dict[str, str]:
    return {lg: _OPS[lg][key] for lg in ("en", "ja", "ko")}


MOVE = ActionSpec("move_to", "action", "neonrp.packs.rpg.atlas.move:move", ["who", "to"], validator="neonrp.packs.rpg.atlas.move:judge", alias="move",
               doc=_op_zh("op_move_to"),
               doc_i18n=_op_i18n("op_move_to"))

NEW_LOCATION = ActionSpec("new_location", "action", "neonrp.packs.rpg.atlas.places:new_location", ["name", "parent", "links"], validator="neonrp.packs.rpg.atlas.places:judge_new_location",
               doc=_op_zh("op_new_location"),
               doc_i18n=_op_i18n("op_new_location"))

LINK = ActionSpec("link", "action", "neonrp.packs.rpg.atlas.places:link", ["a", "b"], validator="neonrp.packs.rpg.atlas.places:judge_link",
               doc=_op_zh("op_link"),
               doc_i18n=_op_i18n("op_link"))

UNLINK = ActionSpec("unlink", "action", "neonrp.packs.rpg.atlas.places:unlink", ["a", "b"], validator="neonrp.packs.rpg.atlas.places:judge_unlink",
               doc=_op_zh("op_unlink"),
               doc_i18n=_op_i18n("op_unlink"))

MAP = ActionSpec("map", "tool", "neonrp.packs.rpg.atlas.draw:draw_map", [], wait=False,
               doc=_op_zh("op_map"),
               doc_i18n=_op_i18n("op_map"))

ACTIONS = [MOVE, NEW_LOCATION, LINK, UNLINK, MAP]
