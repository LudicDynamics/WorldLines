"""Contract 1.0 beat events (R6, the handover 10-06): what a heavy front end / SDK subscribes to, derived from the turn
traces a player line produced — one list per line, in order.

    node.enter / node.leave   the graph node the world entered / left (plan · resolve · a mode layer)
    plan.beat                 the planning beat: host lines, who was asked, the board, the agreed checks
    resolve.beat              the resolve beat: what advanced it, the prose, the options
    dice                      every die the beat rolled (request + answer)
    tool                      every other tool the beat called
    state.changed             what landed (variables from → to, moves, new / patched / removed things) + gained / lost:
                              what changed hands, who has it now, where it came from (core/holdings.py)
    run.settled               the run reached its exit (settlement.json written)

10-14 (the standard front end, docs/planning/STANDARD-FRONTEND-1014.md §5):

    party.join / party.leave  a soul came along with the player / stayed behind  {sid, iid, name, why}
    stage.changed             a plot's stage variable moved  {plot, var, from, to, name, cg?: {slot, image, video, caption, camera}}
    show                      a template picture to put on screen now: the host's [~show …] (by: host) or a plot picture
                              hung where the player just arrived (by: arrive)  {slot, template, cls, inst, label, …}

10-15:

    place.discovered          a place the player learned of: {addr, name, parent, by: grow | arrive | reveal}
    achievement.unlocked      an achievement the beat unlocked {id, title, desc, scope, points} (core/achievements)
    reward.granted            a world's reward card the beat earned {id, kind, world, title, desc, rarity, image?}
                              (core/rewards, 10-18; kept in the player's record, never taken back)
    milestone                 an open-adventure milestone reached {id, type: place | job | day | stretch, label, points,
                              art: {kind: cg, slot} | {kind: composite, scene, souls, caption}, generate: {scene, caption}}
                              (core/milestones; settled when the player leaves)
    soul.mind                 what a character present made of this beat (from her own turn's judgment): {iid, sid, name,
                              attitude, attitude_label, thought?, intent, move_to?, follow, stay, trust_delta?} — the
                              「心思」 the screen may show; the reasoning behind it stays in the turn record
    audio.cue                 what plays changed: {music: {id, url, mood, title?} | null, ambient: {id, url} | null, mood:
                              calm | tense | crisis, by: default | place | stage | trigger | mood, fade_ms, place} (core/audio;
                              the current one any time: GET /api/v1/play/engine/audio)

Each beat's events go out as the beat lands (engine/beat; /events and the browser's onEvent forward them then): a
planning talk that ends in the switch arrives as its own plan.beat — with ``ended_by``, the Resolve still to come —
before the Resolve's prose streams (10-14).

plan.beat / resolve.beat carry ``mentions`` ([{id, cls, name, span}] in ``text``, core/mentions.py); the opening plan.beat
carries ``cg`` (the template's opening CG, in play order); a resolve the player's structured action produced carries
``action`` ({kind: inspect | pick, target}).

Names match TESTBENCH-AUTOVIEW-1005 so the Hub replay can reuse the per-round bundle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.core.beat_display import outcome_level

EVENTS = ("node.enter", "node.leave", "plan.beat", "resolve.beat", "dice", "tool", "state.changed", "run.settled",
          "party.join", "party.leave", "stage.changed", "show", "soul.mind",
          "place.discovered", "achievement.unlocked", "reward.granted", "milestone", "audio.cue")
_DICE = ("dice", "roll", "referee", "san")
_DICE_KEYS = ("rolls", "total", "vs", "passed", "under", "reason", "dice", "level", "label", "who",
              "crit_max", "fumble_min")  # level: crit / success / fail / fumble (pct); the bands say why


def live_dice(ev: dict[str, Any]) -> dict[str, Any] | None:
    """A die the moment its tool returns (core/tool_watch's event for dice / san) → ``dice.rolled``: the same numbers
    as the beat's ``dice`` event, sent before the prose lands so a front end plays it right away (niko 10-17). Not part
    of the trace: the beat's own ``dice`` event still comes when the beat lands (a front end that played this one skips
    that one by total / vs). None when it is not a roll (a bad spec, no total)."""
    r = ev.get("result") if isinstance(ev.get("result"), dict) else {}
    if not r.get("ok") or r.get("total") is None:
        return None
    a = ev.get("args") if isinstance(ev.get("args"), dict) else {}
    out = {"kind": "dice.rolled", "turn": ev.get("turn"), "source": ev.get("source"), "live": True,
           "request": str(r.get("request") or ev.get("tool") or "dice"), "answer": r.get("text")}
    out.update({k: r.get(k) for k in _DICE_KEYS if r.get(k) is not None})
    for k in ("who", "label", "reason"):
        if out.get(k) in (None, "") and a.get(k) not in (None, ""):
            out[k] = a[k]
    return out


def _opening_cg(root: Path | None) -> list[dict[str, Any]]:
    if root is None:
        return []
    try:
        from neonrp.core.show import _j, _meta

        rec = _j(_meta(Path(root)) / "template.json", {}) or {}
        op = rec.get("opening") if isinstance(rec, dict) else None
        if not isinstance(op, dict):
            return []
        from neonrp.core.scene_cg import for_companion
        from neonrp.template import run_companion

        sid = run_companion(Path(root))  # the picture of the companion the player picked, where there is one (10-15)
        return [dict(for_companion(c, str(c.get("slot") or ""), sid), template=rec.get("id")) for c in (op.get("cg") or []) if isinstance(c, dict)]
    except Exception:  # noqa: BLE001
        return []


def _clean_script(script: list[Any]) -> list[Any]:
    """The planning beat's lines as the screen shows them: a character's reply without its machine blocks
    (``<lines>`` / ``<fields>`` / ``<draft>``, core/soul_result.clean_line) — 10-15."""
    import re

    if not any(isinstance(x, dict) and re.search(r"</?(lines|fields|draft)\s*>", str(x.get("text") or ""), re.IGNORECASE) for x in script):
        return script
    from neonrp.core.soul_result import clean_line

    return [{**x, "text": clean_line(str(x.get("text") or ""))} if isinstance(x, dict) and x.get("text") else x for x in script]


def _minds(ap: dict[str, Any], turn: Any, root: Path | None) -> list[dict[str, Any]]:
    """One ``soul.mind`` per character whose turn this beat judged (``apply.reports[].judgment``)."""
    reps = [r for r in ap.get("reports") or [] if isinstance(r, dict) and isinstance(r.get("judgment"), dict) and r.get("iid")]
    if not reps:
        return []
    lang, sids = "zh", {}
    try:
        from neonrp.core import holdings
        from neonrp.core.output_lang import prompt_lang

        if root is not None:
            lang, sids = prompt_lang(Path(root)), {k: v.get("sid") for k, v in holdings._souls(Path(root)).items()}
    except Exception:  # noqa: BLE001
        pass
    from neonrp import prompts

    att = prompts.strings("soul_step", lang).get("ATTITUDES") or {}
    out = []
    for r in reps:
        j = r["judgment"]
        sid = str(sids.get(r["iid"]) or "")
        delta = sum((int(a.get("to") or 0) - int(a.get("from") or 0)) for a in ap.get("applied") or []
                    if isinstance(a, dict) and sid and a.get("var") == f"trust.{sid}" and isinstance(a.get("to"), (int, float))
                    and isinstance(a.get("from"), (int, float)))
        a = str(j.get("attitude") or "")
        m: dict[str, Any] = {"turn": turn, "iid": r["iid"], **({"sid": sid} if sid else {}), "name": r.get("name") or "",
                             "attitude": a or None, "attitude_label": str(att.get(a) or "") if a else "",
                             "intent": str(r.get("kind") or ""), "follow": j.get("follow") or 0.0, "stay": j.get("stay") or 0.0}
        if j.get("thought"):
            m["thought"] = str(j["thought"])
        mv = r.get("proposed_move") or (j.get("move_to") if j.get("want_move") else None)
        if mv:
            m["move_to"] = mv
        if delta:
            m["trust_delta"] = delta
        out.append(m)
    return out


def from_traces(traces: list[dict[str, Any]], prev_node: str | None = None, *, root: Path | None = None) -> tuple[list[tuple[str, dict[str, Any]]], str | None]:
    """[(event, data)] for these traces, and the node the world is left in. ``root`` (the run) fills what a trace did not
    keep: the opening CG, and the mentions of a beat recorded before they were (against the registry as it is now)."""
    out: list[tuple[str, dict[str, Any]]] = []
    node = prev_node
    reg_now: list[Any] = []

    def mentions(ap: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(ap.get("mentions"), list):
            return ap["mentions"]
        if root is None or not ap.get("narration_plain"):
            return []
        try:
            from neonrp.core import mentions as _mn
            from neonrp.core.registry import load_registry

            if not reg_now:
                reg_now.append(load_registry(Path(root)))
            return _mn.find(reg_now[0], str(ap.get("narration_plain") or ""))
        except Exception:  # noqa: BLE001
            return []

    for tr in traces:
        ap = tr.get("apply") or {}
        beat = ap.get("beat") if isinstance(ap.get("beat"), dict) else {}
        kind = str(beat.get("kind") or "resolve")
        kind = "plan" if kind in ("plan", "opening") else kind
        turn = tr.get("turn_seq")
        if kind != node:
            if node:
                out.append(("node.leave", {"node": node, "turn": turn}))
            out.append(("node.enter", {"node": kind, "turn": turn}))
            node = kind
        if kind == "plan":
            opening = beat.get("kind") == "opening" or bool(ap.get("opening"))
            ev = {"turn": turn, "script": _clean_script(beat.get("script") or []), "mic": beat.get("asked") or beat.get("mic") or [],
                  "board": beat.get("board") or {}, "checks": beat.get("checks") or [], "opening": opening,
                  "text": ap.get("narration_plain") or "", "mentions": mentions(ap)}
            if beat.get("ended_by"):  # the talk ended in the switch: the Resolve beat follows (10-14: shown first, on its own)
                ev["ended_by"] = beat["ended_by"]
            if opening and (cg := ap.get("cg") if isinstance(ap.get("cg"), list) else _opening_cg(root)):
                ev["cg"] = cg
            out.append(("plan.beat", ev))
        else:
            ev = {"turn": turn, "advanced_by": beat.get("advanced_by"), "text": ap.get("narration_plain") or "",
                  "options": ap.get("options") or [], "rolled": beat.get("rolled") or [],
                  # the panels the beat drew — [~map] / [~sheet] (async, drawn after the write-down) and a
                  # layer's <formation>: {id: {id, format, source, text | data | fallback}} (10-08)
                  "panels": ap.get("panels") or {}, "mentions": mentions(ap)}
            if isinstance(ap.get("action"), dict):  # the player's structured action (core/player_action.py)
                ev["action"] = ap["action"]
            out.append(("resolve.beat", ev))
        out += [("soul.mind", m) for m in _minds(ap, turn, root)]
        for d in (beat.get("dice") or []) if kind != "plan" else []:  # the checks agreed in the talk, rolled before the prose (10-17)
            if isinstance(d, dict):
                out.append(("dice", {"turn": turn, "request": str(d.get("request") or "dice"), "answer": d.get("text"), "async": False, "ok": True,
                                     **{k: d.get(k) for k in _DICE_KEYS if d.get(k) is not None}}))
        # a one-shot layer's own requests (the combat layer's [dice]) ride its reply: each is an event of its own, after it
        rows = [x for t in ap.get("tool_returns") or [] for x in [t, *[a for a in t.get("answers") or [] if isinstance(a, dict)]]]
        for t in rows:
            req = str(t.get("request") or "")
            name = req.split(" ", 1)[0]
            if name == "show":  # the host put a template picture on screen (core/show.py); a refused one stays a tool event
                if t.get("ok") and isinstance(t.get("show"), dict):
                    out.append(("show", {"turn": turn, **t["show"]}))
                    continue
            ev = {"turn": turn, "request": req, "answer": t.get("text"), "async": bool(t.get("async")), "ok": t.get("ok")}
            if name in _DICE:  # the numbers, so a renderer can draw the die without parsing the answer (10-08)
                ev.update({k: t.get(k) for k in _DICE_KEYS if t.get(k) is not None})
                if not ev.get("level") and outcome_level(t):  # a pack that names no tier: the plain one (a renderer reads both)
                    ev["level"] = outcome_level(t)
            out.append(("dice" if name in _DICE else "tool", ev))
        applied = ap.get("applied") or []
        if applied or ap.get("created") or ap.get("gained") or ap.get("lost"):
            out.append(("state.changed", {"turn": turn, "applied": applied, "created": ap.get("created") or [], "refused": ap.get("refused") or [],
                                          "gained": ap.get("gained") or [], "lost": ap.get("lost") or []}))
        for name, key in (("party.join", "joined"), ("party.leave", "left")):
            for p in ap.get(key) or []:
                out.append((name, {"turn": turn, **p}))
        for st in ap.get("stages") or []:
            out.append(("stage.changed", {"turn": turn, **st}))
        for sh in ap.get("shows") or []:
            out.append(("show", {"turn": turn, **sh}))
        for pl in ap.get("discovered") or []:  # 10-15: a place the player learned of (grow · arrive · reveal)
            out.append(("place.discovered", {"turn": turn, **pl}))
        for ms in ap.get("milestones") or []:
            out.append(("milestone", {"turn": turn, **ms}))
        for a in ap.get("achievements") or []:
            out.append(("achievement.unlocked", {"turn": turn, **a}))
        for rw in ap.get("rewards") or []:
            out.append(("reward.granted", {"turn": turn, **rw}))
        if isinstance(ap.get("audio"), dict):
            out.append(("audio.cue", {"turn": turn, **ap["audio"]}))
        if ap.get("settled"):
            out.append(("run.settled", {"turn": turn, **(ap["settled"] if isinstance(ap["settled"], dict) else {})}))
        mode = ap.get("mode") if isinstance(ap.get("mode"), dict) else None
        if mode and mode.get("name") and mode["name"] != node:
            out.append(("node.leave", {"node": node, "turn": turn}))
            out.append(("node.enter", {"node": mode["name"], "turn": turn}))
            node = mode["name"]
    return out, node
