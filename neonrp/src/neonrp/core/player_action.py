"""The player's structured actions from a front end (10-14, the standard front end §5.6): a click on a thing is
「查看」 (inspect) or 「拿起」 (pick) — the engine lands it itself, no model in between and no line said for the player.

    POST /cmd {"action": "inspect" | "pick", "target": "<entry id or name>"}     (also /session/<sid>/turn[/stream])
      → the session's input is the marker ``[inspect I701]`` (kept in the history so the host knows what happened)
      → the ``act`` node takes the turn: the op lands through ``sdk.apply`` (triggers, ledger, gained / lost, party …)
      → one resolve beat: ``advanced_by`` = the action, ``action`` = {kind, target, ok, why?}, the text below

What each does, in any world (the world's own rules come first):

- a pack that registers its own ``inspect`` / ``pick`` op: that op lands it (its handler, its rules)
- the world's triggers see the action: ``when: {"entry": "I701", "event": "pick"}`` (or ``"inspect"``), and the
  ``text`` rules see the thing's name as what the player turned to (末班车's 「笔记本」 rule fires on a click on it)
- inspect: the thing's own description (``summary`` / ``desc`` / ``description`` / ``detail`` …, or the one core/inspect
  wrote for this run); a person's one-line intro + appearance (what the player may know, core/inspect); then what the
  triggers said
- pick: a thing (not a person, not a place, not an effect, not ``fixed``) where the player stands goes into their hands
  (its parent becomes the player, kept in ``<data>/meta/entries.json``) → state.changed ``gained`` with how ``picked``

Reach: the target is where the player stands (or inside it), carried by the player, a person here — or, for inspect,
the place itself. Anything else answers 「不在这里」 and changes nothing.

Commands that hand the beat on to the host (10-14, §5.13) — :func:`prepare` reads them before the turn starts:

    POST /cmd {"action": "skill", "skill": "侦查", "target": "井口"}      → the marker ``[skill 侦查]井口``
    text 「/侦查 井口」 (a skill / attribute on the player's sheet, by any of its names)
    text 「/go 3车」 (a play action of the world's ``game/meta/actions.json``) → its prompt, 「我去3车。」

- a skill: the pack's ``skill_check`` seam rolls it now when the sheet alone decides it (pct: d100 under the skill) —
  the roll is this beat's first tool return (a ``dice`` event) and the host is told the result; a pack without the
  seam, or a name it does not know → the host is told the player used the skill and rolls by the world's own rules
- the player's words for the beat become 「我用「侦查」:井口。」 (the history keeps what was sent)
- a world action: its prompt with the arguments, sent as the player's own line (the TUI's `/` commands, same table)
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KINDS = ("inspect", "pick")
MARK = re.compile(r"^\s*\[(inspect|pick)\s+(.+?)\]\s*$", re.DOTALL)
SKILL_MARK = re.compile(r"^\s*\[skill\s+([^\]]+?)\]\s*(.*)$", re.DOTALL)
SLASH = re.compile(r"^\s*/(\S+)\s*(.*)$", re.DOTALL)
DESC_KEYS = ("summary", "desc", "description", "detail", "text", "note")


def marker(kind: str, target: str) -> str:
    return f"[{kind} {str(target).strip()}]"


def parse(text: str) -> tuple[str, str] | None:
    m = MARK.match(text or "")
    return (m.group(1), m.group(2).strip()) if m else None


def skill_marker(skill: str, target: str = "") -> str:
    return f"[skill {str(skill).strip()}]{str(target or '').strip()}"


def from_body(body: Any) -> str | None:
    """A request body ``{"action", "target"}`` (or ``{"action": "skill", "skill", "target"?}``) → the marker; None when
    it is not one."""
    if not isinstance(body, dict):
        return None
    kind, target = str(body.get("action") or "").strip().lower(), str(body.get("target") or "").strip()
    if kind == "skill":
        skill = str(body.get("skill") or body.get("name") or "").strip().lstrip("/")
        return skill_marker(skill, target or str(body.get("text") or "")) if skill and "]" not in skill else None
    return marker(kind, target) if kind in KINDS and target else None


def _T(root: Path) -> dict[str, Any]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.prompts import strings

    return strings("player_action", prompt_lang(root))


def _within(reg: Any, eid: str | None, place: str | None) -> bool:
    """``eid`` is ``place`` or sits somewhere under it."""
    seen = set()
    while eid and eid not in seen:
        if eid == place:
            return True
        seen.add(eid)
        e = reg.entries.get(eid)
        eid = e.parent if e is not None else None
    return False


def reach(reg: Any, kind: str, eid: str) -> str | None:
    """None = the player can do this to ``eid``; else the reason key (not_here / have_it / cannot_pick)."""
    from neonrp.core.holdings import PLACE_CLASSES

    e = reg.entries.get(eid)
    here = reg.player_location
    if e is None:
        return "not_found"
    mine = reg.owner_of(e) == "player"
    place = e.cls in PLACE_CLASSES
    if kind == "inspect":
        return None if mine or (place and eid == here) or _within(reg, e.parent, here) else "not_here"
    if mine:
        return "have_it"
    spec = reg.classes.get(e.cls)
    if place or reg.is_person(e.cls) or (spec is not None and getattr(spec, "effect", False)) or e.props.get("fixed") or e.props.get("portable") is False:
        return "cannot_pick"
    owner = reg.owner_of(e)
    if owner and owner != "player":  # someone else's: asking them is a line for the host, not a click
        return "cannot_pick"
    return None if _within(reg, e.parent, here) else "not_here"


def describe(e: Any) -> str:
    from neonrp.core.inspect import own_desc

    return own_desc(e) or str(e.name or e.id)


def land(root: Path, reg: Any, res: Any, o: dict[str, Any]) -> None:
    """Called by ``sdk.apply`` for the core ``inspect`` / ``pick`` op (a pack's own op of the name lands through its handler)."""
    kind, eid = str(o.get("op")), str(o.get("what") or "")
    e = reg.entries.get(eid)
    if e is None:
        res.refused.append({"op": o, "scope": "entity", "field": "what", "why": f"{eid} is not in the world"})
        return
    why = reach(reg, kind, eid)
    if why:
        res.refused.append({"op": o, "scope": "world", "field": "what", "why": why})
        return
    if kind == "pick":
        frm = e.parent
        _set_parent(root, e, "player")
        res.applied.append({"op": "pick", "who": "player", "what": eid, "from": frm, "handler": "player.pick"})
    else:
        res.applied.append({"op": "inspect", "who": "player", "what": eid, "handler": "player.inspect"})


def _set_parent(root: Path, e: Any, parent: str) -> None:
    """Where a thing is, kept in the entries overlay (read last by the registry, so it wins over the world's files)."""
    from neonrp.core.paths import get_data_dir_name

    p = root / get_data_dir_name(root) / "meta" / "entries.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    cur = data.get(e.id) if isinstance(data.get(e.id), dict) else {}
    data[e.id] = {**cur, "class": cur.get("class") or e.cls, "parent": parent}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    e.parent = parent


def perform(root: Path, kind: str, target: str, *, turn: int) -> dict[str, Any]:
    """Land one structured action: {"text", "action", "apply" (the ApplyResult)}. No model — except an inspect of something
    nothing was written about yet (core/inspect writes its few lines once)."""
    from neonrp.core import sdk
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    T = _T(root)
    eid = target if target in reg.entries else reg.resolve(target)
    if not eid or eid not in reg.entries:
        res = sdk.apply(root, [], reg, turn=turn)
        return {"text": str(T["not_found"]).format(target=target), "action": {"kind": kind, "target": target, "ok": False, "why": "not_found"}, "apply": res}
    e = reg.entries[eid]
    names = " ".join(dict.fromkeys([str(e.name or "")] + sorted(str(a) for a in e.aliases if isinstance(a, str) and a != e.id)))
    why = reach(reg, kind, eid)
    ops = [] if why else [{"op": kind, "who": "player", "what": eid}]
    res = sdk.apply(root, ops, reg, turn=turn, narration="", player_says=names if not why else "")
    said = [str(x.get("text") or "") for f in res.triggered for x in f.get("emitted") or [] if x.get("to") == "narration" and x.get("text")]
    if why:
        head = str(T.get(why) or T["not_here"]).format(name=e.name or eid, target=target)
    elif kind == "inspect":  # a person's intro + appearance, a thing's / a place's description (core/inspect: written now, once, if there was none)
        from neonrp.core import inspect as _inspect

        head = _inspect.text(root, reg, e, write=True)
    else:
        head = str(T["picked"]).format(name=e.name or eid)
        desc = describe(e)
        if desc != (e.name or eid):
            head += " " + desc
    text = "\n\n".join([head] + said)
    return {"text": text, "action": {"kind": kind, "target": eid, "ok": not why, **({"why": why} if why else {})}, "apply": res}


class _PlayerActionNode:
    """The ``player_action`` node kind (``act`` before 10-19, still read): a structured action marker takes the turn
    (before any talk — it is the player's own move, already decided: ``order`` 0, core/node_kinds.turn_order)."""

    kind = "player_action"
    order = 0

    def active(self, root: Path, user_text: str) -> bool:
        return parse(user_text) is not None

    def take_turn(self, session: Any, *, user_text: str, trace: Any, run_id: Any, on_chunk: Any) -> Any:
        from neonrp.core.conversation import ConversationTurnResult
        from neonrp.core.llm import Message
        from neonrp.core.mentions import find
        from neonrp.core.orchestration_trace import append_turn_trace
        from neonrp.core.registry import load_registry
        from neonrp.core.session import append_message
        from neonrp.core.turn_settlement import _bump_turn_count

        kind, target = parse(user_text) or ("inspect", "")
        out = perform(session.root, kind, target, turn=int(trace.turn_seq or 0))
        text = out["text"]
        if on_chunk is not None:
            on_chunk(text)
        trace.apply = {**out["apply"].to_dict(), "narration_plain": text, "options": [], "action": out["action"],
                       "beat": {"kind": "resolve", "advanced_by": kind, "rolled": []}}
        try:
            trace.apply["mentions"] = find(load_registry(session.root), text)
        except Exception:  # noqa: BLE001
            pass
        msg = Message(role="assistant", content=text)
        session.messages.append(msg)
        append_message(session.root, session.branch, msg, run_id=run_id)
        session._persisted_up_to = len(session.messages)
        append_turn_trace(session.root, session.branch, trace)
        session._emit_beats(trace)
        _bump_turn_count(session.root, int(trace.turn_seq or 0))
        return ConversationTurnResult(success=True, run_id=run_id, assistant_message=text, route_decision="action",
                                      active_agent=session.agent_id)


_ActNode = _PlayerActionNode  # the old name


# ── commands that hand the beat on (skill · world action) ────────────────────────────────────────────────────────────

def prepare(root: Path, text: str, *, turn: int) -> dict[str, Any] | None:
    """Before a turn: a skill command / a world action → {say, action, facts?, tool_returns?}; None = plain words.
    ``say`` replaces the player's words for the beat; ``facts`` go to the host; ``tool_returns`` lead the beat's."""
    m = SKILL_MARK.match(text or "")
    if m:
        return skill_turn(root, m.group(1).strip(), m.group(2).strip(), turn=turn)
    m = SLASH.match(text or "")
    if not m:
        return None
    word, rest = m.group(1), m.group(2).strip()
    from neonrp.core import play_menu
    from neonrp.core import sheet as _sheet

    body = str(text).strip()[1:]
    sh = _sheet.sheet(root)
    names = sorted({str(n) for kind in ("skills", "attrs") for r in sh.get(kind) or []
                    for n in [r.get("key"), r.get("name"), r.get("label"), *(r.get("aliases") or [])] if n}, key=len, reverse=True)
    for n in names:  # the longest name the line starts with (「/First Aid 她」), then a space or the end
        if body.casefold().startswith(n.casefold()) and (len(body) == len(n) or body[len(n)].isspace()):
            return skill_turn(root, n, body[len(n):].strip(), turn=turn)
    row = next((r for r in play_menu.world_actions(root) if word.casefold() in (r["name"].casefold(), r["label"].casefold())), None)
    if row is not None:
        return {"say": play_menu.expand(row, rest), "action": {"kind": "action", "name": row["name"], "args": rest}}
    return None


def skill_turn(root: Path, name: str, target: str, *, turn: int) -> dict[str, Any]:
    from neonrp.core import mechanics
    from neonrp.core import sheet as _sheet
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    T = _T(root)
    row = _sheet.find(_sheet.sheet(root, reg=reg), name)
    label = str((row or {}).get("label") or name)
    what = str(T["skill_what"]).format(target=target) if target else ""
    res = None
    try:
        res = mechanics.get(root, "skill_check")(root, reg, {"who": "player", "skill": str((row or {}).get("name") or (row or {}).get("key") or name),
                                                             "label": label, "target": target}, seed=f"{turn}:skill")
    except Exception:  # noqa: BLE001 — a pack's roll failing leaves the host to roll
        logger.warning("skill_check failed; the host rolls", exc_info=True)
    action: dict[str, Any] = {"kind": "skill", "skill": label, **({"key": row.get("key")} if row else {}), "target": target,
                              "rolled": isinstance(res, dict)}
    out: dict[str, Any] = {"say": str(T["skill_say"]).format(name=label, what=what), "action": action}
    if isinstance(res, dict):
        lab = str(res.get("label") or label)
        out["facts"] = str(T["skill_rolled"]).format(name=label, what=what, label=lab, result=str(res.get("text") or res.get("total")))
        out["tool_returns"] = [{"request": str(res.get("request") or f"dice {lab}"), **{k: v for k, v in res.items() if k != "request"}}]
        action.update({k: res.get(k) for k in ("total", "vs", "passed", "level") if res.get(k) is not None})
    else:
        out["facts"] = str(T["skill_unrolled"]).format(name=label, what=what)
    return out
