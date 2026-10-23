"""pct — percentile investigation (BRP), built on rpg.

Everything rpg has stays (map, places, people, items, plots, the status table, Character State, the turn
loop, the combat layer's machinery); what changes is the dice: checks are d100 under a skill or an attribute × 5,
sanity has its own tool, dying is a CON check each resolve (down_rule ``pct``), combat runs on attack / dodge
percentages. Rules data in ``packs/pct/data/``, words in ``src/neonrp/prompts/pct.<lang>.json`` and
``packs/pct/prompts/``.
"""
from __future__ import annotations

import copy
from dataclasses import replace

from neonrp import prompts
from neonrp.core.registry import ActionSpec
from neonrp.packs.rpg import pack as _rpg

_LANGS = ("en", "ja", "ko")


def _doc(key: str) -> tuple[str, dict[str, str]]:
    return prompts.strings("pct", "zh")[key], {lg: prompts.strings("pct", lg)[key] for lg in _LANGS}


def _actions() -> list[ActionSpec]:
    out: list[ActionSpec] = []
    for a in _rpg.ACTIONS:
        a = copy.copy(a)
        if a.op == "dice":
            zh, i18n = _doc("doc_dice")
            a = replace(a, handler="neonrp.packs.pct.tools:dice", doc=zh, doc_i18n=i18n)
        elif a.op == "referee":
            a = replace(a, handler="neonrp.packs.pct.referee:ruling")
        out.append(a)
    zh, i18n = _doc("doc_san")
    out.append(ActionSpec("san", "tool", "neonrp.packs.pct.tools:san", ["spec"], doc=zh, doc_i18n=i18n))
    return out


def _modes() -> dict[str, dict]:
    m = {k: dict(v) for k, v in _rpg.MODES.items()}
    c = m["combat"]
    c.update({"spawn": "neonrp.packs.pct.combat:spawn", "state": "neonrp.packs.pct.combat:state_block",
              "ops": list(c.get("ops") or []) + ["san"],
              "tail": prompts.md_by_lang("pct_combat_tail"), "require_why": prompts.md_by_lang("pct_combat_require")})
    return m


MECHANICS = {**_rpg.MECHANICS, "roll_check": "neonrp.packs.pct.rules:roll_check", "load": "neonrp.packs.pct.loaders:load",
             "sheet": "neonrp.packs.pct.rules:sheet", "skill_check": "neonrp.packs.pct.rules:skill_check"}


def _pack():
    p = copy.copy(_rpg.PACK)
    p.name = "pct"
    p.base = "rpg"
    p.classes = dict(_rpg.CLASSES)
    p.actions = _actions()
    p.mechanics = dict(MECHANICS)
    p.modes = _modes()
    p.ticks = list(_rpg.PACK.ticks) + ["neonrp.packs.pct.tick:tick"]
    p.doc = "percentile investigation (pct): d100 skills, composure, dying CON checks, percentile combat — built on rpg"
    p.loop = copy.deepcopy(_rpg.PACK.loop)
    return p


PACK = _pack()
