"""Two rpg-only turn rules, bound from the pack's seams:

``companions`` — after verify, a present soul whose judgment says follow ≥ .6 and stay < .5 walks
to the player's ACTUAL landing (E7 / final2: Elena kept standing where the player left her).
``speech_rule`` — L2 rule 0: a present soul's quoted line must appear once in the prose.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from neonrp.core.registry import Registry

_QUOTE_RE = re.compile(r"[「“\"]([^」”\"]{6,})[」”\"]")


def missing_speech(root: Path, reg: Registry, narration: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Present souls whose spoken line (first quoted clause ≥ 6 chars) is absent from the prose."""
    out: list[dict[str, Any]] = []
    flat = re.sub(r"[\s,,。.!!??;;::、—\-…]", "", narration or "")
    for r in reports:
        if r.get("kind") not in ("speak", "act", "need") or not r.get("text"):
            continue
        m = _QUOTE_RE.search(str(r["text"]))
        if not m:
            continue
        line = m.group(1).strip()
        key = re.sub(r"[\s,,。.!!??;;::、—\-…]", "", line)
        probe = key[:12] if len(key) > 12 else key
        if probe and probe not in flat:
            out.append({"iid": r.get("iid"), "name": r.get("name"), "line": line[:60]})
    return out


FOLLOW_AT = 0.6
STAY_AT = 0.5


def _player_lines(reg: Registry, talk: list[str], user_text: str) -> str:
    """What the player said in the talk (``{who}:{text}`` lines) plus this beat's line."""
    from neonrp.core import soul_view

    pname = soul_view.player_name(reg)
    mine = []
    for ln in talk:
        who, sep, text = ln.replace("\uff1a", ":").partition(":")
        if sep and who.strip() == pname:
            mine.append(text)
    return "\n".join([*mine, user_text or ""])


def follow(root: Path, reg: Registry, ops: list[dict[str, Any]], reports: list[dict[str, Any]], *,
           talk: list[str] | None = None, user_text: str = "", judged: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Companions walk with the player unless they said otherwise (E1 v3-split T3–T5: the player
    walked on to the inn, the model moved only the player, Elena's state stayed on main street while
    the prose had her upstairs). S-judge answers ``follow`` per soul; ≥ FOLLOW_AT and no move of her
    own in this batch, and not told to stay (``stay`` < STAY_AT) → she gets a move_to to the player's
    verified landing (cross-town: the clamped gate, like the player).

    A Resolve after a talk (``talk`` given): the people present took no turn, so each is judged here over
    the whole talk; with no judge, the player naming her is the answer (PL12 watch4 10-17). ``judged``
    collects every decision for the trace."""
    pm = next((o for o in ops if o.get("op") == "move_to" and str(o.get("who") or "").strip().casefold() in {"player", "玩家", "you", "你"}), None)
    if pm is None or not reg.player_location:
        return []
    dest = reg.resolve(str(pm.get("to") or ""), cls="place") or str(pm.get("to") or "")  # verified ops carry the landing (clamped if cross-town)
    if not dest or dest == reg.player_location:
        return []
    out: list[dict[str, Any]] = []
    moved = {reg.resolve(str(o.get("who") or "")) for o in ops if o.get("op") == "move_to"}
    by_iid = {r.get("iid"): r for r in reports if r.get("iid")}
    said = "\n".join([*(talk or []), user_text or ""]).strip() if talk is not None else ""
    named = _player_lines(reg, talk or [], user_text) if talk is not None else ""
    for env in reg.of_class("soul"):
        iid = env.id
        if env.parent != reg.player_location or iid in moved or int(env.props.get("dead") or 0):
            continue
        jd = (by_iid.get(iid) or {}).get("judgment") or {}
        if "follow" in jd:
            src = "turn"
        elif talk is not None and said:
            from neonrp.packs.rpg.soul_step import judge_follow

            jd, src = judge_follow(root, reg, iid, said) or {}, "talk"
            if not jd:  # no judge: the player named her in what he said → she comes
                jd, src = ({"follow": 1.0, "stay": 0.0} if env.name and env.name in named else {"follow": 0.0, "stay": 0.0}), "named"
        else:
            continue
        follow, stay = float(jd.get("follow") or 0.0), float(jd.get("stay") or 0.0)
        go = follow >= FOLLOW_AT and stay < STAY_AT
        if judged is not None:
            judged.append({"iid": iid, "name": env.name, "follow": follow, "stay": stay, "src": src, "moved": go})
        if go:
            out.append({"op": "move_to", "who": iid, "to": dest, "_from": "follow", "_why": f"follow {follow:.2f} ≥ {FOLLOW_AT}, stay {stay:.2f} < {STAY_AT} ({src})"})
    return out


