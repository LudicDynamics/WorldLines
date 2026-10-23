"""Mechanics — the template's seams, resolved by name (design §9, 「rpg = template」).

The engine core knows only that these hooks exist; which function fills each one is a
registration in the template pack (``Pack.mechanics``), ``game/meta/mechanics.json`` or
``manifest.json["mechanics"]``. The core's defaults are GENERIC (no map, no souls, no towns):

    contract      ③ world-side system prompt       fn(root, reg, structured) -> str
    soul_turn     ② one soul's turn                fn(root, iid, *, situation, depth, provider, mode, registry, variant) -> report
    observe       ② what a soul sees (o_i)         fn(root, iid) -> str
    settle        ⑤ write the soul's closed schema  fn(root, *, reports, narration, turn, registry, ask) -> list
    participation ② who takes part                 fn(root, reg, iid) -> bool
    load          registry: the template's own world layout      fn(reg, root) -> None
    pack_hints    ① extra text appended to the pack (rpg: 远行段) fn(root, reg) -> str
    companions    ④ extra ops after verify (rpg: follow)          fn(root, reg, accepted, reports) -> list[op]
    speech_rule   ④ extra fixable refusals (rpg: quoted line)     fn(root, reg, narration, reports) -> list
    after_turn    ⑥ work after the reply (rpg: place grown places)  fn(root, *, created, narration) -> callable | None
    roll_check    a check agreed while talking, rolled at Resolve     fn(root, reg, check, *, seed) -> result
    plan_event    an outside event that will not wait for the talk    fn(root) -> str | None
    sheet         the player's sheet named for a front end (core/sheet)   fn(root, reg, sheet, lang) -> sheet
    skill_check   a skill the player used by command (core/player_action)  fn(root, reg, check, *, seed) -> dice result | None

``builtin:none`` returns None everywhere (callers treat None as empty). Actions' ``validator`` /
``handler`` are the remaining seam and live in actions.json (core/handlers.py).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from neonrp.core.handlers import BUILTIN, resolve
from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger(__name__)

SEAMS = ("contract", "soul_turn", "observe", "settle", "participation", "load", "pack_hints", "companions", "speech_rule", "gate", "post_solve", "understand", "after_turn", "roll_check", "plan_event", "run_outputs", "sheet", "skill_check")
DEFAULTS: dict[str, str] = {
    "contract": "builtin:contract.generic",
    "soul_turn": "builtin:none",
    "observe": "builtin:observe.pack",
    "settle": "builtin:none",
    "participation": "builtin:everyone",
    "load": "",
    "pack_hints": "builtin:none",
    "companions": "builtin:none",
    "speech_rule": "builtin:none",
    "post_solve": "builtin:none",
    "understand": "builtin:none",  # before ②: fn(root, reg, user_text) → {refs, attempt, block} — the player's words as an attempt, checked against the world  # after ③, before the loop decides: fn(root, reg, narration, turn) → fixable refusals (template rules on the prose)
    "after_turn": "builtin:none",
    "roll_check": "builtin:none",
    "run_outputs": "builtin:none",  # at the run's exit: fn(root, reg, contract) → {output: value} the pack alone knows (who was accused, every role) — 10-08 E4
    "sheet": "builtin:none",  # none → the raw keys, no descriptions (10-14)
    "skill_check": "builtin:none",  # none → the host is told the skill and rolls by the world's own rules (10-14)
    "plan_event": "builtin:none",  # none → core/plan_loop rolls a plain d20 against the difficulty  # after the reply: fn(root, *, created, narration) → a zero-arg callable to run on a thread, or None
    "gate": "builtin:none",  # before ③: the engine may force a mode (combat) or pre-rule the player's move (referee) — fn(root, reg, user_text=…, intent_kind=…, turn=…) → {mode, note, returns}
}


def _read(path: Path) -> dict[str, Any]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def spec(root: Path) -> dict[str, str]:
    """Registered names for every seam: defaults < pack < manifest.json["mechanics"] < game/meta/mechanics.json."""
    from neonrp.packs import resolve as _resolve_pack

    out = dict(DEFAULTS)
    out.update({k: v for k, v in _resolve_pack(root).mechanics.items() if k in SEAMS and v})  # the template's own seams
    man = _read(root / "manifest.json").get("mechanics")
    if isinstance(man, dict):
        out.update({k: str(v) for k, v in man.items() if k in SEAMS and v})
    meta = _read(root / get_data_dir_name(root) / "meta" / "mechanics.json")
    out.update({k: str(v) for k, v in meta.items() if k in SEAMS and v})
    return out


def get(root: Path, seam: str) -> Callable[..., Any]:
    if seam not in SEAMS:
        raise KeyError(f"unknown mechanic seam {seam!r}; one of {SEAMS}")
    return resolve(spec(root)[seam] or "builtin:none")


# ── generic built-ins (template-free) ────────────────────────────────────────

def _none(*_a: Any, **_k: Any) -> None:
    return None


def _everyone(root: Path, reg: Any, iid: str) -> bool:
    return True


def _observe_pack(root: Path, iid: str) -> str:
    from neonrp.core.sdk import pack, render_pack

    return render_pack(pack(root, viewer=iid))


def _contract_generic(root: Path, reg: Any, structured: str = "together") -> str:
    """A contract built from the tables alone, in the ADV shape: <lines> one message per line, <ops> one op per line
    (`<op> <field1> <field2> …` in the op's field order), <options> 2–4."""
    ops = [a for a in reg.actions.values() if a.scope == "world" and a.enabled]
    grammar = "\n".join(f"{a.op} " + " ".join(f"<{f}>" for f in a.fields) + (f"    {a.doc}" if a.doc else "") for a in ops)
    vars_ = "、".join(k for k, v in reg.variables.items() if not v.readonly)
    return ("你是这个世界的主持人。按下面四个块输出,块外不写字:\n"
            "<cot>\n一到三行,给引擎看的思路。\n</cot>\n"
            "<lines>\n画面上按顺序显示的消息,一句一行;台词整行用「」包住,地文不带「」。\n</lines>\n"
            "<ops>\n这一回合的状态变化,一行一个,字段按顺序空格分开;没有变化就写 无变化:\n" + grammar + "\n</ops>\n"
            "<options>\n玩家接下来可能说的话或做的事,2–4 个,一行一个,20 字以内。\n</options>\n"
            + f"能改的变量只有:{vars_ or '(无)'};lines 里发生的事 ops 里一一对应;ops 里不要写 lines 里没发生的事。")


BUILTIN.update({
    "none": _none,
    "everyone": _everyone,
    "observe.pack": _observe_pack,
    "contract.generic": _contract_generic,
})
