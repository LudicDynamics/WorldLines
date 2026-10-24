"""The RPG reference template — the registrations the engine ran on before templates existed.
Nothing here is engine: a world that names another template never sees these."""
from __future__ import annotations

from neonrp import prompts
from neonrp.core.registry import ActionSpec, ClassSpec
from neonrp.packs.rpg import atlas

def _T(key: str) -> dict:
    """{lang: text} of one rpg_pack string (prompts/rpg_pack.<lang>.json); the engine picks the run's language (10-06)."""
    return prompts.by_lang("rpg_pack", key)


CLASSES: dict[str, ClassSpec] = {
    "world": ClassSpec("world", None, ["name"], []),
    "town": ClassSpec("town", "world", ["name"], ["parent_exists"], _T("town_render")),
    "place": ClassSpec("place", "town", ["name"], ["parent_exists", "links_symmetric"], _T("place_render")),
    "region": ClassSpec("region", "world", ["name"], []),
    "player": ClassSpec("player", None, ["name"], ["location_exists"]),
    # Whether a character has an hp bar is the schema's — rpg declares it for both; a world's schema may drop it
    # (then that class is judged only able / down). The run's values live in game/states/<id>.json (character_state.py)
    "soul": ClassSpec("soul", None, ["name"], ["location_exists"], props={"hp": {"type": "int", "min": 0}, "max_hp": {"type": "int", "min": 0}}),
    "npc": ClassSpec("npc", None, ["name"], [], props={"hp": {"type": "int", "min": 0}, "max_hp": {"type": "int", "min": 0}}),
    "item": ClassSpec("item", None, ["name"], []),
    # `job` not `quest`: authors register their own `quest` class (SCHEMA-AND-SDK §2b); the guild board is the template's
    # the seats v2's sub-agents read from (the pack was hollow — rules / quests / dungeons never reached the model)
    "job": ClassSpec("job", "town", ["name"], ["parent_exists"], _T("job_render"),
                       scope="town", tier=2, title=_T("job_title"), packed=True),
    "dungeon": ClassSpec("dungeon", "world", ["name"], [], _T("dungeon_render"),
                         scope="world", tier=2, title=_T("dungeon_title"), packed=True),
    "road": ClassSpec("road", "world", ["name"], [], _T("road_render"), scope="world", tier=0, title=_T("road_title"), packed=True),
    "room": ClassSpec("room", "dungeon", ["name"], ["parent_exists", "links_symmetric"],
                      _T("room_render"),
                      scope="place", tier=1, title=_T("room_title"), packed=True),
    # 10-01 open schema on the player's own files (no migration): each list item is an entry the narrator can
    # new / patch / remove; `status` is an effect class (core/effects.py counts it down, applies `each`, adds `check`).
    "carry": ClassSpec("carry", None, ["name"], [], _T("carry_render"), folder="game/player/inventory.json#items", scope="world", tier=1,
                       id_prefix="IT", props={"qty": {"type": "int", "min": 0}}, mutable=["qty"], title=_T("carry_title")),
    # An effect is one free rule line (data/status.<lang>.md / the world's rules/status.md); the engine reads
    # only the countdown (turns, or hours on the clock — effects_clock.py) and the per-resolve change (each) from it;
    # the rest of the line is for the narrator and the host (who writes check modifiers into the checks it agrees)
    "status": ClassSpec("status", None, ["name"], [], _T("status_render"),
                        folder="game/player/stats.json#status_effects", scope="world", tier=0, id_prefix="ST",
                        props={"turns": {"type": "int", "min": 0}, "check": {"type": "int"}, "each": {"type": "str"}, "note": {"type": "str"},
                               "rule": {"type": "str"}, "hours": {"type": "float", "min": 0}, "until": {"type": "int", "min": 0},
                               "until_text": {"type": "str"}, "on": {"type": "str"}},  # the player's own; others' states are their own props (10-02)
                        mutable=["turns", "check", "each", "note", "rule", "hours", "until", "until_text", "on"], title=_T("status_title"), effect=True),
}

_OPS = {lg: prompts.strings("rpg_pack", lg) for lg in ("zh", "en", "ja", "ko")}  # op docs the model reads each turn


def _op_zh(key: str) -> str:
    return _OPS["zh"][key]


def _op_i18n(key: str) -> dict[str, str]:
    return {lg: _OPS[lg][key] for lg in ("en", "ja", "ko")}


ACTIONS: list[ActionSpec] = [
    atlas.MOVE,
    ActionSpec("engage", "action", "engage", ["who", "note"], parallel=True, enabled=False, doc=_op_zh("op_engage"), doc_i18n=_op_i18n("op_engage")),
    ActionSpec("need", "request", "need", ["who"], alias="ask", doc=_op_zh("op_need"),
               doc_i18n=_op_i18n("op_need")),
    ActionSpec("set", "update", "set_variable", ["var", "value"], doc=_op_zh("op_set"), doc_i18n=_op_i18n("op_set")),
    ActionSpec("add", "update", "add_variable", ["var", "delta"], doc=_op_zh("op_add"), doc_i18n=_op_i18n("op_add")),
    ActionSpec("flag", "update", "set_flag", ["key"], doc=_op_zh("op_flag"), doc_i18n=_op_i18n("op_flag")),
    atlas.NEW_LOCATION,
    atlas.LINK,
    atlas.UNLINK,
    ActionSpec("new_town", "action", "neonrp.packs.rpg.writers:new_town", ["name", "from", "days", "summary", "tags"], validator="neonrp.packs.rpg.writers:judge_new_town",
               doc=_op_zh("op_new_town"),
               doc_i18n=_op_i18n("op_new_town")),
    ActionSpec("new_npc", "action", "neonrp.packs.rpg.writers:new_npc", ["name", "at", "role"], doc=_op_zh("op_new_npc"), doc_i18n=_op_i18n("op_new_npc"), validator="neonrp.packs.rpg.writers:judge_new_npc"),
    ActionSpec("new", "action", "writer.new", ["class", "name"], doc=_op_zh("op_new"),
               doc_i18n=_op_i18n("op_new")),
    ActionSpec("patch", "update", "patch_props", ["who", "props"], doc=_op_zh("op_patch"), doc_i18n=_op_i18n("op_patch")),
    ActionSpec("remove", "update", "writer.remove", ["who"], doc=_op_zh("op_remove"), doc_i18n=_op_i18n("op_remove")),
    ActionSpec("write", "action", "worldfiles", ["path"], doc=_op_zh("op_write"),
               doc_i18n=_op_i18n("op_write")),
    ActionSpec("edit", "action", "worldfiles", ["path"], doc=_op_zh("op_edit"),
               doc_i18n=_op_i18n("op_edit")),
    ActionSpec("rm", "action", "worldfiles", ["path"], doc=_op_zh("op_rm"),
               doc_i18n=_op_i18n("op_rm")),
    ActionSpec("mkdir", "action", "worldfiles", ["path"], doc=_op_zh("op_mkdir"),
               doc_i18n=_op_i18n("op_mkdir")),
    ActionSpec("rmdir", "action", "worldfiles", ["path"], doc=_op_zh("op_rmdir"),
               doc_i18n=_op_i18n("op_rmdir")),
    ActionSpec("define", "action", "writer.define", ["kind", "name"],
               doc=_op_zh("op_define"),
               doc_i18n=_op_i18n("op_define")),
    ActionSpec("mood", "update", "soul_mood", ["who", "value"], scope="souls", doc=_op_zh("op_mood"), doc_i18n=_op_i18n("op_mood")),
    ActionSpec("roll", "tool", "neonrp.packs.rpg.tools:roll", ["dice"], doc=_op_zh("op_roll"),
               doc_i18n=_op_i18n("op_roll")),
    # 09-30: 裁判 / 战斗 / 骰子 — v2's sub-agents as requests and a mode layer
    ActionSpec("dice", "tool", "neonrp.packs.rpg.tools:dice", ["dice", "vs"],
               doc=_op_zh("op_dice"),
               doc_i18n=_op_i18n("op_dice")),
    atlas.MAP,
    ActionSpec("sheet", "tool", "neonrp.packs.rpg.tools:sheet", [], wait=False,
               doc=_op_zh("op_sheet"),
               doc_i18n=_op_i18n("op_sheet")),
    ActionSpec("referee", "tool", "neonrp.packs.rpg.referee:ruling", ["question"],
               doc=_op_zh("op_referee"),
               doc_i18n=_op_i18n("op_referee")),
    ActionSpec("combat", "tool", "neonrp.packs.rpg.combat:exchange", ["roster", "note"], validator="neonrp.packs.rpg.understand:combat_grounds",
               doc=_op_zh("op_combat"),
               doc_i18n=_op_i18n("op_combat")),
    ActionSpec("end_combat", "update", "neonrp.packs.rpg.combat:end", ["outcome"], scope="plugin", doc=_op_zh("op_end_combat"),
               doc_i18n=_op_i18n("op_end_combat")),
]

# the layers = v2 sub-agents as one-shot nodes the Resolve calls (10-18): their system.md from
# the world folder or the pack, reads packed by the engine, their dice thrown by the engine, writes through ops
MODES: dict[str, dict] = {
    "combat": {"title": _T("combat_title"), "prompt": "agents/combat-referee/system.md", "reads": ["rules"], "reads_title": _T("combat_reads_title"),
               "one_shot": True, "ops": ["dice", "roll", "flag"], "spawn": "neonrp.packs.rpg.combat:spawn",
               "blocks": ["lines", "formation", "ops"],
               "panels": {"formation": _T("formation")},
               "state": "neonrp.packs.rpg.combat:state_block",
               "require_tool": "dice", "require_why": _T("combat_require_why"), "hit_needs": ".hp",
               "tail": _T("combat_tail")},
    # a place-keyed layer: while the player stands in a dungeon room the narrator's whole prompt is the dungeon agent's (not persisted)
    "dungeon": {"title": _T("dungeon_mode_title"), "prompt": "agents/dungeon-agent/system.md", "reads": ["rules"], "here_class": "room", "ops": [],
                "tail": _T("dungeon_tail")},
    "referee": {"title": _T("referee_title"), "prompt": "agents/rules-referee/system.md", "reads": ["rules"], "output": "json", "one_shot": True,
                "strip": ["读写边界", "读什么文件", "语言匹配", "不出选项菜单", "Read/Write", "Language", "No menus"]},  # its 输出格式 (JSON ruling) stays
}

MECHANICS = {
    "contract": "neonrp.packs.rpg.contract:contract",
    "soul_turn": "neonrp.packs.rpg.soul_step:soul_step",
    "observe": "builtin:observe.pack",
    "settle": "neonrp.packs.rpg.soul_settle:settle_souls",
    "after_turn": "neonrp.packs.rpg.atlas.fix:after_turn",
    "roll_check": "neonrp.packs.rpg.referee:roll_check",
    "plan_event": "neonrp.packs.rpg.travel:plan_event",
    "participation": "neonrp.packs.rpg.atlas.move:colocated",
    "load": "neonrp.packs.rpg.loaders:load",
    "pack_hints": "neonrp.packs.rpg.contract:pack_hints",
    "companions": "neonrp.packs.rpg.rules:follow",
    "speech_rule": "neonrp.packs.rpg.rules:missing_speech",
    "gate": "neonrp.packs.rpg.gates:pre_turn",
    "post_solve": "neonrp.packs.rpg.travel:overshoot",
    "understand": "neonrp.packs.rpg.understand:understand",
    "sheet": "neonrp.packs.rpg.sheet:sheet",
}

FLAGS = {"path": "game/player/flags.json", "key": "story_flags"}  # where rpg worlds keep story flags


def _register_compat_names() -> None:
    """Old handler names (``builtin:map.judge`` …) keep resolving for worlds / tests that still use them."""
    from neonrp.core.handlers import BUILTIN
    from neonrp.packs.rpg import contract as _c, map as _m

    BUILTIN.update({"map.judge": _m.judge, "map.move": _m.move, "rpg.contract": _c.contract, "rpg.colocated": _m.colocated,
                    "rpg.observe": BUILTIN.get("observe.pack"), "rpg.pack_hints": _c.pack_hints})
    from neonrp.packs.rpg import soul_settle as _ss, soul_step as _st

    BUILTIN.update({"rpg.soul_turn": _st.soul_step, "rpg.settle": _ss.settle_souls})


_register_compat_names()


def _pack():
    from neonrp.packs import Pack

    p = Pack("rpg", dict(CLASSES), list(ACTIONS), {}, {}, dict(MECHANICS), "",
             "开放世界 RPG:镇 / 地点连通图、角色同地才同场、move_to 走图判定、道具 / 路人 / 剧情包。", "builtin")
    p.flags = dict(FLAGS)
    p.ticks = ["neonrp.packs.rpg.effects_clock:tick",  # effects that run out on the world clock (10-05)
               "neonrp.packs.rpg.travel:tick_souls",  # a character on her own road arrives when its days have passed (10-23)
               "neonrp.packs.rpg.downed:tick",  # hp 0 → down → the down rule each Resolve → stable / dead (10-05)
               "neonrp.packs.rpg.combat:tick"]  # a fight whose foes are all down / fled, or that the player left, is over (10-18)
    p.modes = {k: dict(v) for k, v in MODES.items()}
    p.loop = {k: dict(v) for k, v in LOOP.items()}
    from neonrp.packs.rpg.ui import UI

    p.ui = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v) for k, v in UI.items()}
    return p


# the agent loop the rpg template runs (「整套用全新的引擎」): v3 five-phase, closed-schema souls
# judged by S1 (S-judge, bench E2); S1 backend stays "auto" (Jev with a key, else the
# deterministic fallbacks). A world pins the old loop with game/meta/engine.json {"turn": {"mode": "v2b"}}.
LOOP: dict[str, dict] = {"turn": {"mode": "v3", "parallel": {"souls": {"default_variant": "S-judge"}}}}  # how the Resolve writes state: the graph's resolve node (core/orchestration)


PACK = _pack()
