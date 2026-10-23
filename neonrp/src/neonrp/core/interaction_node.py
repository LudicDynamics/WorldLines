"""Interactions — the graphical game loop's interactions as node kinds (niko 10-10/11; in the open engine since 10-19,
it used to be a private-layer plugin).

A game client (a Godot / TS town) owns the frame: walking, collision, the camera, the rings. Every time the
player crosses out of a scene, touches someone or something, it sends one interaction; this node takes that turn and
runs that interaction's own small graph — receive → judge → land → lines → settle — instead of the world host's
free narration. The host stays in the background (the clock, people elsewhere, story triggers).

The line the client sends::

    <interaction>{"kind": "move", "to": "T001/main_street"}</interaction>
    <interaction>{"kind": "approach", "target": "NPC004", "approach": "persuade"}</interaction>Let me through — here is why: …

kinds      judge (code / model)                 land                           lines
  move      linked? the template's gates         move_to · triggers             a short arrival scene (model)
  examine   —                                    triggers (the line as said)    what you see (model)
  talk      —                                    triggers                       the person (their own agent)
  approach  the template's approach rules: a     the result's state             the person's reaction
            check, the person's cares / resist                                  (their own agent)
  encounter is it a fight?                       the combat layer (harness      —
                                                 state machine switch)
Anything else (a move inside a fight, an unknown kind) falls through to the plain turn: the active layer runs it.

The person speaks with their own agent: a soul through its own dialogue lane (light_chat — persona, memory, thread);
a townsperson without a soul folder through one shared bit-part actor that reads their sheet
(``npcs.json``: traits · persuade.cares / resist · secrets). The rules are template data —
``game/meta/interactions.json``::

    {"gates": {"T001/road_camp": {"if": [<trigger conditions>], "refuse": "…"}},
     "links": [["T001/road_camp", "D001/D001_R001"]],
     "approaches": {"persuade": {"check": "resist", "bonus_cares": 20, "on_ok": [{"flag": "persuaded.{who}"}]},
                    "steal": {"check": 50, "night": 15, "alert_cost": 10, "on_fail": [{"var": "town.alert", "add": 1}]},
                    "recruit": {"check": null, "on_ok": [{"flag": "{sid}_joined"}]}}}

Every word the engine writes or asks the model is in the run's language: ``prompts/interaction.<lang>.json``.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def _t(root: Path) -> dict[str, Any]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.prompts import strings

    return strings("interaction", prompt_lang(root))


TAG = re.compile(r"^\s*<interaction>(.*?)</interaction>\s*(.*)$", re.S)
KINDS = ("move", "examine", "talk", "approach", "encounter")


def parse(text: str) -> tuple[dict[str, Any] | None, str]:
    m = TAG.match(text or "")
    if not m:
        return None, text
    try:
        ev = json.loads(m.group(1))
    except ValueError:
        return None, text
    return (ev if isinstance(ev, dict) and ev.get("kind") else None), m.group(2).strip()


def _data(root: Path) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    try:
        return json.loads((root / get_data_dir_name(root) / "meta" / "interactions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _adapter(root: Path) -> Any:
    from neonrp.core import light_chat

    return light_chat._adapter(root)


def _ask_model(root: Path, system: str, user: str) -> str:
    from neonrp.core.llm import Message

    try:
        res = _adapter(root).chat([Message(role="system", content=system), Message(role="user", content=user)])
        msg = getattr(res, "message", None)
        return str(getattr(msg, "content", None) or (msg if isinstance(msg, str) else "") or "").strip()
    except Exception:  # noqa: BLE001 — a line failing never undoes what landed
        logger.warning("interaction line failed", exc_info=True)
        return ""


def _here(root: Path) -> str:
    from neonrp.core import sdk

    p = sdk.pack(root)
    return p.here.id if p.here else ""


def _person(root: Path, reg: Any, target: str) -> dict[str, Any]:
    """{id, name, kind: soul | npc, iid?, sheet?} for an id, a sid or a name."""
    t = str(target or "")
    for e in reg.entries.values():
        if e.cls == "soul" and (e.id == t or e.name == t or str(e.props.get("sid", "")) == t or t in e.aliases):
            return {"id": e.id, "name": e.name, "kind": "soul", "iid": e.id}
    for e in reg.entries.values():
        if e.cls == "npc" and (e.id == t or e.name == t or e.name.split("(")[0] == t or t in e.aliases):
            town = reg.entries.get(str(e.parent or "").split("/")[0])   # where they live: the town their place is in
            return {"id": e.id, "name": e.name.split("(")[0], "kind": "npc", "sheet": {**dict(e.props), **_sheet(root, e.id)},
                    "where": town.name if town is not None and town.id != e.id else ""}
    return {"id": t, "name": t, "kind": "npc", "sheet": {}}


def _sheet(root: Path, npc_id: str) -> dict[str, Any]:
    """The townsperson's own sheet (npcs.json: traits · persuade.cares / resist · secrets) — the registry keeps only part."""
    from neonrp.core.paths import get_data_dir_name

    for f in (root / get_data_dir_name(root) / "towns").glob("*/npcs.json"):
        try:
            for n in json.loads(f.read_text(encoding="utf-8")).get("npcs") or []:
                if str(n.get("id")) == npc_id:
                    return dict(n)
        except (OSError, ValueError):
            continue
    return {}


def _lines_from(res: Any) -> list[str]:
    out = []
    for f in getattr(res, "triggered", None) or []:
        for e in f.get("emitted") or f.get("then") or []:
            if isinstance(e, dict) and e.get("to") == "narration" and e.get("text"):
                out.append(str(e["text"]))
    return out


def _land(root: Path, reg: Any, ops: list[dict[str, Any]], *, turn: int, says: str = "", narration: str = "") -> Any:
    from neonrp.core import sdk

    vr = sdk.verify(root, ops, reg) if ops else None
    accepted = list(getattr(vr, "accepted", None) or []) if vr is not None else []
    refused = list(getattr(vr, "refused", None) or []) if vr is not None else []
    return sdk.apply(root, accepted, reg, turn=turn, refused=refused, narration=narration, player_says=says)


def _effects(spec: list[dict[str, Any]], who: dict[str, Any]) -> list[dict[str, Any]]:
    ops = []
    for e in spec or []:
        fill = {"who": who.get("id", ""), "sid": str(who.get("name", "")), "name": who.get("name", "")}
        if "flag" in e:
            ops.append({"op": "flag", "key": str(e["flag"]).format(**fill)})
        elif "var" in e:
            ops.append({"op": "add", "var": str(e["var"]).format(**fill), "delta": e["add"]} if "add" in e
                       else {"op": "set", "var": str(e["var"]).format(**fill), "value": e.get("set")})
    return ops


# ── the five graphs ─────────────────────────────────────────────────────────────────────────────────────────────
def do_move(session: Any, reg: Any, ev: dict[str, Any], words: str, turn: int) -> dict[str, Any]:
    from neonrp.core import sdk
    from neonrp.core import triggers as _tr

    root = session.root
    T = _t(root)
    to = str(ev.get("to") or "")
    here = _here(root)
    data = _data(root)
    pack = sdk.pack(root)
    linked = {e.id for e in pack.exits} | {b for a, b in data.get("links", []) if a == here} | {a for a, b in data.get("links", []) if b == here}
    dest = reg.entries.get(reg.resolve(to) or "")
    if dest is None:
        return {"ok": False, "reason": T["no_place"].format(to=to)}
    if dest.id not in linked and dest.id != here:
        return {"ok": False, "reason": T["cant_reach"].format(here=pack.here.name if pack.here else T["here"], dest=dest.name)}
    gate = (data.get("gates") or {}).get(dest.id) or {}
    if gate.get("if"):
        snap = _tr.snapshot(reg)
        ok, _was, _why = _tr._if(reg, gate["if"], snap, snap, {"player": words, "narration": ""}, {})
        if not ok:
            return {"ok": False, "reason": str(gate.get("refuse") or T["gate_closed"].format(dest=dest.name))}
    res = _land(root, reg, [{"op": "move_to", "who": "player", "to": dest.id}], turn=turn, says=words or T["go_to"].format(dest=dest.name))
    lines = _lines_from(res)
    scene = _ask_model(root, T["scene_system"], _scene_prompt(root, dest, came_from=here, extra=lines))
    return {"ok": True, "res": res, "lines": lines, "scene": scene, "to": dest.id}


def do_examine(session: Any, reg: Any, ev: dict[str, Any], words: str, turn: int) -> dict[str, Any]:
    root = session.root
    T = _t(root)
    what = str(ev.get("what") or ev.get("target") or "")
    says = words or str(ev.get("says") or T["looked_at"].format(what=what))
    res = _land(root, reg, [], turn=turn, says=says)
    lines = _lines_from(res)
    here = reg.entries.get(_here(root) or "")
    seen = _ask_model(root, T["scene_system"], T["examine_user"].format(place=here.name if here else "", what=what, says=says,
                                                                        happened=T["happened_sep"].join(lines) or T["none"]))
    return {"ok": True, "res": res, "lines": lines, "scene": seen}


def _speak(session: Any, reg: Any, who: dict[str, Any], said: str, situation: str = "") -> str:
    """The person answers with their own agent: a soul's dialogue lane, or the shared bit-part actor reading their sheet."""
    root = session.root
    if who["kind"] == "soul":
        from neonrp.core import light_chat

        r = light_chat.light_chat_reply(root, str(who["iid"]), (situation + "\n" if situation else "") + said)
        if r.get("ok"):
            return str(r.get("reply") or "")
    T = _t(root)
    sheet = who.get("sheet") or {}
    p = sheet.get("persuade") or {}
    system = T["npc_system"].format(at=T["npc_at"].format(where=who["where"]) if who.get("where") else "", name=who["name"],
                                    role=sheet.get("role", ""), traits=T["list_sep"].join(sheet.get("traits") or []),
                                    cares=T["list_sep"].join(p.get("cares") or []) or T["cares_default"],
                                    secrets=T["secrets_sep"].join(s.get("text", "") for s in sheet.get("secrets") or []) or T["none"])
    reply = _ask_model(root, system, (situation + "\n" if situation else "") + T["npc_user"].format(said=said))
    try:
        from neonrp.core import light_chat

        light_chat._append_pending(root, T["pending"].format(name=who["name"], said=said[:120], reply=reply[:160]))
    except Exception:  # noqa: BLE001
        pass
    return reply


def do_talk(session: Any, reg: Any, ev: dict[str, Any], words: str, turn: int) -> dict[str, Any]:
    who = _person(session.root, reg, str(ev.get("target") or ""))
    said = words or str(ev.get("says") or _t(session.root)["talk_up"].format(name=who["name"]))
    reply = _speak(session, reg, who, said)
    res = _land(session.root, reg, [], turn=turn, says=said, narration=reply)
    return {"ok": True, "res": res, "lines": _lines_from(res), "who": who, "reply": reply}


def do_approach(session: Any, reg: Any, ev: dict[str, Any], words: str, turn: int) -> dict[str, Any]:
    root = session.root
    T = _t(root)
    who = _person(root, reg, str(ev.get("target") or ""))
    aid = str(ev.get("approach") or "talk")
    rule = ((_data(root).get("approaches") or {}).get(aid)) or {}
    said = words or str(ev.get("says") or "")
    sheet = who.get("sheet") or {}
    roll = None
    if rule.get("check") is not None:
        cares = list((sheet.get("persuade") or {}).get("cares") or [])
        target = 100 - int((sheet.get("persuade") or {}).get("resist", 50)) if rule["check"] == "resist" else int(rule["check"])
        hit = None
        if rule.get("bonus_cares") and cares and said:   # the model says which care the reason touches; the code checks it is one
            ans = _ask_model(root, T["judge_system"], T["judge_user"].format(name=who["name"], said=said,
                                                                             cares="\n".join(f"{i + 1}. {c}" for i, c in enumerate(cares))))
            m = re.search(r"\d+", ans or "")
            n = int(m.group()) if m else 0
            hit = cares[n - 1] if 1 <= n <= len(cares) else None
            if hit:
                target += int(rule["bonus_cares"])
        if rule.get("night"):
            clock = str(reg.variables.get("time.clock").value if "time.clock" in reg.variables else "12:00")
            if int(clock.split(":")[0] or 12) >= 20 or int(clock.split(":")[0] or 12) < 5:
                target += int(rule["night"])
        if rule.get("alert_cost") and "town.alert" in reg.variables:
            target -= int(rule["alert_cost"]) * int(reg.variables["town.alert"].value or 0)
        target = max(5, min(95, target))
        r = random.randint(1, 100)
        roll = {"request": f"roll {aid} {who['name']}", "rolls": [r], "total": r, "vs": target, "passed": r <= target, "under": True,
                "reason": f"{rule.get('label', aid)} · {who['name']}" + (T["hit"].format(hit=hit) if hit else ""), "ok": True}
    ok = roll["passed"] if roll else True
    ops = _effects(rule.get("on_ok") if ok else rule.get("on_fail"), who)
    situation = T["situation"].format(label=rule.get("label", aid), result=T["result_ok"] if ok else T["result_fail"],
                                      roll=T["situation_roll"].format(total=roll["total"], vs=roll["vs"]) if roll else "")
    # an unnoticed theft has nobody to react: the person only speaks when they know (rule "react": "on_fail")
    quiet = ok and str(rule.get("react") or "") == "on_fail"
    reply = "" if quiet else _speak(session, reg, who, said or f"({rule.get('label', aid)})", situation)
    res = _land(root, reg, ops, turn=turn, says=said, narration=reply)
    return {"ok": ok, "res": res, "lines": _lines_from(res), "who": who, "reply": reply, "roll": roll, "approach": aid}


def do_encounter(session: Any, reg: Any, ev: dict[str, Any], words: str, turn: int) -> dict[str, Any]:
    """Switch the harness's state machine to the combat layer — the same as a landed [combat …], without waiting for
    the model to write it."""
    roster = str(ev.get("roster") or "").strip()
    note = str(ev.get("note") or words or "").strip()
    if not roster:
        return {"ok": False, "reason": _t(session.root)["no_rival"]}
    res = _land(session.root, reg, [{"op": "combat", "roster": roster, "note": note}], turn=turn, says=words)
    return {"ok": True, "res": res, "lines": _lines_from(res), "next": "combat"}


GRAPHS = {"move": do_move, "examine": do_examine, "talk": do_talk, "approach": do_approach, "encounter": do_encounter}



def _when(root: Path) -> str:
    from neonrp.core.paths import get_data_dir_name

    g = root / get_data_dir_name(root)
    try:
        rs = json.loads((g / "meta" / "run_state.json").read_text(encoding="utf-8")).get("time") or {}
    except (OSError, ValueError):
        rs = {}
    try:
        tl = json.loads((g / "timeline" / "current.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tl = {}
    return _t(root)["when"].format(day=rs.get("day", tl.get("day", "?")), clock=rs.get("clock", tl.get("clock", "")),
                                   period=rs.get("period", tl.get("period", "")), weather=tl.get("weather", ""))


def _people_at(root: Path, reg: Any, place_id: str) -> list[str]:
    node = place_id.split("/")[-1]
    out = [e.name.split("(")[0] for e in reg.entries.values() if e.cls == "npc" and str(e.parent or "").split("/")[-1] == node]
    from neonrp.core import sdk

    try:
        out += [e.name for e in sdk.pack(root).present if e.cls == "soul"]
    except Exception:  # noqa: BLE001
        pass
    return out


def _scene_prompt(root: Path, dest: Any, *, came_from: str, extra: list[str]) -> str:
    T = _t(root)
    desc = str(dest.props.get("description") or "")
    reg = _reg(root)
    return T["scene_user"].format(name=dest.name, desc=desc, when=_when(root), people=T["list_sep"].join(_people_at(root, reg, dest.id)) or T["nobody"],
                                  came_from=came_from, happened=T["happened_sep"].join(extra) or T["none"])


def _reg(root: Path) -> Any:
    from neonrp.core.registry import load_registry

    return load_registry(root)


MINUTES = {"move": 10, "examine": 5, "talk": 5, "approach": 10, "encounter": 0}


def _advance(root: Path, minutes: int) -> None:
    """An interaction is a turn of the world: the turn count goes up and the clock moves by what it took."""
    from neonrp.core.paths import get_data_dir_name
    from neonrp.core.world_clock import tick_world

    p = root / get_data_dir_name(root) / "meta" / "run_state.json"
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
        st["turn_count"] = int(st.get("turn_count") or 0) + 1
        p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        return
    if minutes:
        tick_world(root, delta_minutes=minutes)


# ── the node ────────────────────────────────────────────────────────────────────────────────────────────────────
class _InteractionNode:
    kind = "interaction"

    def active(self, root: Path, user_text: str) -> bool:
        ev, _ = parse(user_text)
        return ev is not None and str(ev.get("kind")) in GRAPHS and not (str(ev.get("kind")) in ("talk", "approach") and _in_fight(root))

    def take_turn(self, session: Any, *, user_text: str, trace: Any, run_id: Any, on_chunk: Any) -> Any:
        from neonrp.core import conversation as _cv
        from neonrp.core.llm import Message
        from neonrp.core.orchestration_trace import append_turn_trace
        from neonrp.core.registry import load_registry
        from neonrp.core.session import append_message

        ev, words = parse(user_text)
        kind = str(ev.get("kind"))
        reg = load_registry(session.root)
        turn = int(reg.variables["turn"].value or 0) if "turn" in reg.variables else int(getattr(trace, "turn_seq", 0) or 0)
        session._enter_beat(f"interaction.{kind}", trace.turn_seq)
        import time as _time

        _t0 = _time.perf_counter()
        try:
            out = GRAPHS[kind](session, reg, ev, words, turn)
        except Exception as exc:  # noqa: BLE001 — an interaction that breaks says so; the world is untouched
            logger.warning("interaction %s failed", kind, exc_info=True)
            out = {"ok": False, "reason": _t(session.root)["failed"].format(exc=exc)[:200]}
        if out.get("res") is not None:   # something happened: the world takes its turn and the clock moves (a refusal costs nothing)
            _advance(session.root, MINUTES.get(kind, 5))
        logger.info("interaction %s took %.1fs", kind, _time.perf_counter() - _t0)
        res = out.get("res")
        pieces: list[tuple[str, str]] = []   # (who, text): who "" = the scene
        if out.get("reason"):
            pieces.append(("", str(out["reason"])))
        for line in out.get("lines") or []:
            pieces.append(("", line))
        if out.get("scene"):
            pieces.append(("", str(out["scene"])))
        if out.get("reply"):
            pieces.append((str(out["who"]["name"]), str(out["reply"]).strip().strip("「」\"“”").strip()))
        for who, text in pieces:
            if on_chunk is not None:
                on_chunk(_cv._tag_sub_agent_event(who, text + "\n\n") if who else text + "\n\n")
        said_line = _t(session.root)["said_line"]
        narration = "\n\n".join(said_line.format(who=w, text=t) if w else t for w, t in pieces)
        settled = {"kind": kind, "ok": bool(out.get("ok")), "reason": out.get("reason"), "to": out.get("to"), "next": out.get("next"),
                   "approach": out.get("approach")}
        trace.apply = {"narration_plain": narration, "beat": {"kind": f"interaction.{kind}", "interaction": settled},
                       "applied": list(getattr(res, "applied", []) or []), "created": list(getattr(res, "created", []) or []),
                       "refused": list(getattr(res, "refused", []) or []), "options": [],
                       "tool_returns": [{**out["roll"], "text": f"{out['roll']['total']} / {out['roll']['vs']}"}] if out.get("roll") else [],
                       **({"settled": res.settled} if res is not None and getattr(res, "settled", None) else {})}
        msg = Message(role="assistant", content=narration)
        session.messages.append(msg)
        append_message(session.root, session.branch, msg, run_id=run_id)
        session._persisted_up_to = len(session.messages)
        append_turn_trace(session.root, session.branch, trace)
        session._emit_beats(trace)
        return _cv.ConversationTurnResult(success=True, run_id=run_id, assistant_message=narration,
                                          route_decision=f"interaction:{kind}", active_agent=session.agent_id)

    def on_kinds(self) -> dict[str, str]:
        return {"interaction": "a game client's interaction ({\"interaction\": \"move\" | \"examine\" | \"talk\" | \"approach\" | \"encounter\"})"}

    # Lint (10-17): the template's interaction nodes are run by this plugin (GRAPHS), not by a pack layer — say which
    # ones it runs, so the editor stops marking them dead. No graph() of its own: that would put them on every desk.
    def check_node(self, nid: str, node: dict[str, Any]) -> str | None:
        if nid == "interaction" and node.get("group"):
            return None
        kind = nid.split(".", 1)[1] if nid.startswith("interaction.") else ""
        return None if kind in GRAPHS else f"no interaction {kind or nid!r} — this plugin runs {' · '.join(KINDS)}"

    def check_edge(self, frm: str, to: str, kind: str) -> str | None | bool:
        if kind != "interaction":
            return False
        return None if to.startswith("interaction.") and to.split(".", 1)[1] in GRAPHS else \
            f"an interaction leads only into its own node (interaction.<{' | '.join(KINDS)}>)"

    # The nodes are the template's (a template's orchestration.json override adds them):
    # only a game client's template has them on its desk; every other template's graph is untouched.
    def ui_beats(self, lang: str = "zh") -> dict[str, Any]:
        from neonrp.prompts import strings

        T = strings("interaction", lang)
        return {"kinds": {f"interaction.{k}": {"label": T[f"t_{k}"], "tone": "res", "host": T[f"t_{k}"], "live": T[f"t_{k}"]} for k in KINDS}}


TOOLS = {"move": ["move_to", "gates", "triggers", "scene line"], "examine": ["triggers", "scene line"],
         "talk": ["the person's agent", "triggers"], "approach": ["check", "cares", "the person's agent", "effects"],
         "encounter": ["combat"]}


def _in_fight(root: Path) -> bool:
    from neonrp.core.modes import read_mode

    m = read_mode(root)
    return bool(m and m.get("name") == "combat")

