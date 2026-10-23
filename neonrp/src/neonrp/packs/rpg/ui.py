"""The rpg pack's declared presentation (Template v3 / Mock 3.0 「组装 · Lint」): asset slots, views, named
prompts, per-turn token budget. A template overrides by id; mixins add theirs (packs.compose).

Slots are CLASS-level (every instance of the class × the slot); builtin recipes (map / scene / portrait /
sprite) are core/worldmap.py's generators; any other recipe id is a named prompt → the image backend.
Views bind variables (``{town}`` = the player's town, ``*`` = one dotted segment) or ``class:<name>``; a ``title`` is a
string or ``{zh, en, ja}`` (the screen picks the run's language).
"""
from __future__ import annotations

from neonrp import prompts

UI: dict = {
    "slots": [
        {"cls": "level", "slot": "map", "kind": "image", "ratio": "3:2", "hotspots": True, "required": "publish", "recipe": "map"},
        {"cls": "soul", "slot": "portrait", "kind": "image", "ratio": "3:4", "required": "publish", "recipe": "portrait"},
        {"cls": "soul", "slot": "sprite", "kind": "image", "from": "portrait", "required": "optional", "recipe": "sprite"},
        {"cls": "place", "slot": "scene", "kind": "image", "ratio": "16:9", "required": "optional", "fallback": "map_crop", "recipe": "scene"},
        {"cls": "item", "slot": "icon", "kind": "icon", "required": "optional", "recipe": "item_icon"},
    ],
    "prompts": {
        "item_icon": "{inst.name}: {inst.summary}. A single item, centred, on a clean background; a game item icon, {style}.",  # English: the image backends read it best
    },
    "views": [
        {"id": "alert", "title": {"zh": "警戒", "en": "Alert", "ja": "警戒", "ko": "경계"}, "bind": ["town.alert"], "widget": "gauge", "layout": {"area": "right", "order": 1, "range": [0, 5]}},
        {"id": "purse", "title": {"zh": "钱袋", "en": "Purse", "ja": "財布", "ko": "지갑"}, "bind": ["player.gold", "player.silver", "player.copper"], "widget": "table", "layout": {"area": "right", "order": 2}},
    ],
    # panels: drawn by a layer block or a tool — the default wording / format; a template overrides by id
    "panels": [
        {"id": "formation", "tag": "formation", "format": "text",
         "prompt": prompts.by_lang("rpg_pack", "formation_short"),
         "schema": {"sides": [{"name": "str", "units": [{"id": "str", "name": "str", "hp": "int", "hp_max": "int", "pos": "str", "status": ["str"]}]}],
                    "round": "int", "note": "str"},
         "layout": {"area": "center", "order": 1}},
        {"id": "map", "tool": "map", "format": "text", "layout": {"area": "center", "order": 2}},
        {"id": "sheet", "tool": "sheet", "format": "text", "layout": {"area": "right", "order": 3}},
    ],
    "budget": 20000,
}
