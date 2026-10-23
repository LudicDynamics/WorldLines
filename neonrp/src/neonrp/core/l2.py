"""L2 — the semantic audit of a solve output (blueprint ④).

Two kinds of checks, both producing the same refusal dicts the ④ loop already feeds back:

deterministic (always on, zero calls)
  - a menu / option list written into the prose        → fixable: rewrite without it (choices go in the block)
  - a present soul's line repeated twice in the prose  → fixable: once is enough

Jev (``turn.verify.l2 = jev``; one batch, ≈0.6 s; asked only where the ops leave a gap)
  - moved.<id>     the prose moved someone the ops did not move          → fixable: add the move_to
  - answered       the player asked / requested and nobody answered      → fixable: answer it (or ask a soul)
  - grounded.<i>   an op the prose does not support                      → dropped (not fixable), reason recorded

Nothing here writes state; it only shapes what ④ accepts and what the loop feeds back.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from neonrp.core import engine_config, system_one as s1
from neonrp.core.registry import Registry

logger = logging.getLogger(__name__)

# 1. 2. 3. / ①②③ / A. B. / 「选项」「你可以:」 at line starts — a menu, not narration
_MENU_RE = re.compile(r"(?m)^\s*(?:[1-9][.、)]\s*\S|[①②③④⑤⑥]\s*\S|[A-DＡ-Ｄ][.、)]\s*\S|(?:选项|可选行动|你可以)[:：])")
_QUOTE_RE = re.compile(r"[「“\"]([^」”\"]{6,})[」”\"]")
_ASKS_RE = re.compile(r"[?？]|吗[。」”]?$|请|帮我|能不能|可以.*吗|告诉我|问")


def _norm(t: str) -> str:
    return re.sub(r"[\s,,。.!!??;;::、—\-…]", "", t or "")


def deterministic(narration: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lines = [ln for ln in (narration or "").splitlines() if _MENU_RE.match(ln)]
    if len(lines) >= 2:
        out.append({"index": -1, "op": {"op": "menu"}, "scope": "world", "field": "narration",
                    "why": "the narration carries a menu of options (" + " | ".join(ln.strip()[:18] for ln in lines[:3]) + "). The prose only says what happens; possible actions go in the choices field, not in the prose",
                    "allowed": [], "fixable": True})
    flat = _norm(narration)
    for r in reports:
        if r.get("kind") not in ("speak", "act", "need") or not r.get("text"):
            continue
        m = _QUOTE_RE.search(str(r["text"]))
        if not m:
            continue
        key = _norm(m.group(1))
        probe = key[:12] if len(key) > 12 else key
        if probe and flat.count(probe) >= 2:
            out.append({"index": -1, "op": {"op": "speech", "who": r.get("iid")}, "scope": "world", "field": "narration",
                        "why": f"{r.get('name')}'s same line appears twice in the narration (“{m.group(1)[:30]}…”). Keep it once; the narrator does not repeat what she just said",
                        "allowed": [], "fixable": True})
    return out


_GO_RE = r"[去回往到进赶奔]\s*(?:了|回|到)?\s*"


def intended_move(reg: Registry, user_text: str, narration: str, accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The player said 去/回/往/到 <a place the registry knows> and the prose did not refuse it, but ops carry no move for the
    player → one fixable refusal (adv7 C3c: 「我回公会去找艾琳娜」narrated at the guild, 0 ops, the state stayed at the inn).
    Deterministic and cheap: alias table × one regex; a place the player already stands in is skipped."""
    import re

    if not user_text or any(o.get("op") == "move_to" and o.get("who") == "player" for o in accepted):
        return []
    here = reg.player_location or ""
    hits: list[tuple[str, str]] = []
    for env in reg.entries.values():
        if env.cls not in ("place", "town") or env.id == here or env.id == here.split("/")[0]:
            continue
        for name in {env.name, *(getattr(env, "aliases", None) or [])}:
            if name and len(name) >= 2 and re.search(_GO_RE + re.escape(name), user_text):
                hits.append((env.id, name))
                break
    if not hits:
        return []
    eid, name = hits[0]
    if any(k in (narration or "") for k in ("没去", "没有去", "走不了", "拦住", "拦下", "留在")):
        return []  # the prose says the move did not happen — that is a legitimate answer
    return [{"index": -1, "op": {"op": "move_to", "who": "player", "to": eid}, "scope": "world", "field": "ops",
             "why": f"the player said they go to {name} ({eid}) and the lines have them going, but ops has no move player {eid}. Add it; if they did not get there after all, the lines must say why",
             "allowed": [eid], "fixable": True}]


def _op_text(o: dict[str, Any], reg: Registry) -> str:
    op = o.get("op")
    who = o.get("who")
    name = reg.entries[who].name if who in reg.entries else ("the player" if who == "player" else str(who))
    if op == "move_to":
        to = o.get("to")
        tn = reg.entries[to].name if to in reg.entries else str(to)
        return f"{name} moved to {tn}"
    if op in ("set", "add"):
        return f"variable {o.get('var')} became / changed by {o.get('value', o.get('delta'))}"
    if op == "flag":
        return f"'{o.get('key')}' happened"
    if op == "new":
        return f"a new {o.get('class')} '{o.get('name')}' appeared"
    if op == "patch":
        return f"{name}'s {', '.join(o.get('props', {}))} changed"
    return f"{op} {who or ''}"


def jev_audit(root: Any, reg: Registry, *, narration: str, ops: list[dict[str, Any]], reports: list[dict[str, Any]],
              user_text: str, ask: Any = None) -> tuple[list[dict[str, Any]], list[int]]:
    """Returns (fixable refusals, indexes of ops to drop). Asks only where the ops leave a gap."""
    cfg = engine_config.engine_config(root)
    grounded_min = float(engine_config._get_path(cfg, "turn.verify.grounded_min", 0.5))
    missed_min = float(engine_config._get_path(cfg, "turn.verify.missed_min", 0.6))
    moved = {str(o.get("who")) for o in ops if o.get("op") == "move_to"}
    asked = any(o.get("op") == "need" for o in ops)
    qs: dict[str, s1.Q] = {}
    present = [("player", "the player")] + [(r.get("iid"), r.get("name")) for r in reports if r.get("iid") in reg.entries and reg.entries[r["iid"]].parent == reg.player_location]
    for iid, name in present:
        if iid not in moved:
            qs[f"moved.{iid}"] = s1.noul(f"By this narration, did {name} leave where they were and go somewhere else this turn? (only what the narration says; no guessing)")
    if not asked and _ASKS_RE.search(user_text or ""):
        qs["answered"] = s1.noul("Did anyone in the narration (a character / NPC / the world) answer the question or request in the player's line?")
    for i, o in enumerate(ops[:6]):
        if str(o.get("var") or "").startswith("time."):
            continue  # time advances implicitly; the prose rarely states the clock (l2a 09-27 dropped three honest time.clock sets)
        if o.get("op") in ("set", "add", "flag", "new", "patch") or (o.get("op") == "move_to" and o.get("who") != "player"):
            qs[f"grounded.{i}"] = s1.noul(f"Does this narration really show that {_op_text(o, reg)}? (not written, or only possible, counts as no)")
    if not qs:
        return [], []
    state = {"player_says": (user_text or "")[:300], "narration": (narration or "")[-1600:], "ops": [_op_text(o, reg) for o in ops[:6]]}
    try:
        answers = (ask or s1.ask)(state, qs) or {}
    except Exception:  # noqa: BLE001
        logger.debug("l2 jev audit failed", exc_info=True)
        return [], []
    fixable: list[dict[str, Any]] = []
    drops: list[int] = []
    for iid, name in present:
        a = answers.get(f"moved.{iid}")
        if a is not None and a.yes >= missed_min:
            exits = [f"{e.id}({e.name})" for e in reg.exits(reg.player_location or "")]
            fixable.append({"index": -1, "op": {"op": "move_to", "who": iid}, "scope": "world", "field": "ops",
                            "why": f"the narration has {name} leaving for somewhere else (Jev {a.yes:.2f}) but ops has no move_to for it. Add the move_to, or change the narration so they stay",
                            "allowed": exits, "fixable": True, "jev": round(a.yes, 3)})
    a = answers.get("answered")
    if a is not None and a.yes < 0.4:
        fixable.append({"index": -1, "op": {"op": "answer"}, "scope": "world", "field": "narration",
                        "why": f"the player's line is a question / request and nobody in the narration answers it (Jev {a.yes:.2f}). Let someone present take it; if a character must answer first, write ask",
                        "allowed": [], "fixable": True, "jev": round(a.yes, 3)})
    for i, o in enumerate(ops[:6]):
        a = answers.get(f"grounded.{i}")
        if a is not None and a.yes < grounded_min:
            drops.append(i)
    return fixable, drops


def owner_rule(reg: Registry, narration: str, ops: list[dict[str, Any]], *, ask: Any = None) -> list[dict[str, Any]]:
    """The prose shows someone other than the player changing in a lasting way — toward the player,
    or in their own condition — and nothing was written on anyone's record. One yes/no to the judge (Jev → LLM judge);
    the engine names no attitude or state: whatever the world calls it, it goes on that person's own record."""
    wrote_on_someone = any(o.get("op") in ("patch", "new_npc", "new", "write", "edit") and str(o.get("who") or "") not in ("player", "玩家")
                           and str(o.get("class") or "") not in ("status", "carry") for o in ops)
    if wrote_on_someone or not (narration or "").strip():
        return []
    qs = {"lasting": s1.noul("In this narration, does anyone other than the player change in a lasting way — in their attitude toward "
                             "the player, or in their own condition? (only what the narration says; a passing look or tone does not count)")}
    try:
        a = (ask or s1.ask)({"narration": narration[-1500:]}, qs) or {}
    except Exception:  # noqa: BLE001
        return []
    ans = a.get("lasting")
    if ans is None or ans.yes < 0.6:
        return []
    return [{"index": -1, "op": {"op": "patch"}, "scope": "world", "field": "ops",
             "why": "someone's attitude toward the player or their own condition changed for good in the narration, and it is on nobody's "
                    "record: write it on that person's own record — patch <that person> prop=value (someone who just appeared: new_npc "
                    "first, then patch in the same turn); not as a state on the player",
             "allowed": [], "fixable": True}]
