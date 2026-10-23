"""S1 · the turn plan — "Jev 先判,LLM 后说" (exp/jev-system-one).

One System One call before any LLM runs answers, for this turn:

- ``intent.kind``      choice   talk / act / move / observe / meta
- ``intent.addressee`` choice   which present character the player addresses
- ``intent.move``      choice   where the player is heading (adjacent exits)
- ``soul.<iid>.reacts`` noul    does this moment move that character
- ``soul.<iid>.depth``  choice  silent / gesture / speak / act
- ``scene.tension``     score   calm … danger
- ``away.<iid>.stir``   noul    should that off-scene character act now (CTB)

The plan drives S2 (souls run in parallel at the depth the plan says) and is
handed to the world-agent as facts so it integrates instead of hosting a
serial tool loop. A second, cheaper call (:func:`plan_followups`) decides
after the souls answered whether the world-agent still needs another
exchange with any of them — the "再次沟通是否需要" confidence.

No System One (key missing, timeout, flag off) ⇒ :func:`fallback_plan`, which
reproduces today's behaviour (every present soul gets a full turn, the
world-agent keeps every tool) so the experiment can never be worse than
the baseline. Thresholds live in env so the observation phase can tune them:
``NEONRP_S1_REACT`` (default 0.6), ``NEONRP_S1_CONFIDENCE`` (0.7).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neonrp.core import system_one as s1

DEPTHS: tuple[str, ...] = ("silent", "gesture", "speak", "act")
INTENTS: tuple[str, ...] = ("talk", "act", "move", "observe", "meta")
TENSION_LEVELS: tuple[str, ...] = ("calm, just everyday life", "some tension or suspense", "open conflict or strong emotion", "danger, someone may get hurt")  # judge labels: English in every run (10-16)


def _react_threshold() -> float:
    try:
        return float(os.environ.get("NEONRP_S1_REACT", "0.6") or 0.6)
    except ValueError:
        return 0.6


@dataclass
class SoulPlan:
    iid: str
    name: str
    present: bool
    reacts: float = 1.0
    depth: str = "act"
    confidence: float = 1.0
    stir: float = 0.0  # away souls: should act now (CTB)

    def to_dict(self) -> dict[str, Any]:
        return {"iid": self.iid, "name": self.name, "present": self.present, "reacts": round(self.reacts, 3), "depth": self.depth, "confidence": round(self.confidence, 3), "stir": round(self.stir, 3)}


@dataclass
class TurnPlan:
    source: str  # "jev" | "stub" | "fallback"
    intent_kind: str = "act"
    addressee: str | None = None  # iid
    move_target: str | None = None  # node id
    tension: float = 0.0
    souls: dict[str, SoulPlan] = field(default_factory=dict)
    intent_confidence: float = 0.0
    ms: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_fallback(self) -> bool:
        return self.source == "fallback"

    def depth_of(self, iid: str) -> str:
        sp = self.souls.get(iid)
        return sp.depth if sp else "act"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "intent": {"kind": self.intent_kind, "addressee": self.addressee, "move_target": self.move_target, "confidence": round(self.intent_confidence, 3)},
            "tension": round(self.tension, 3),
            "souls": {iid: sp.to_dict() for iid, sp in self.souls.items()},
            "ms": self.ms,
            "answers": {k: {"v": (round(v.value, 3) if isinstance(v.value, float) else v.value), "c": round(float(v.confidence), 3)}
                        for k, v in (self.raw or {}).items() if hasattr(v, "value")},
        }


# ── state assembly ───────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _last_event(soul_dir: Path) -> str:
    ev = _read_json(soul_dir / "short-term-memo" / "recent_events.json").get("events")
    if isinstance(ev, list) and ev:
        last = ev[-1]
        if isinstance(last, dict):
            return str(last.get("event") or last.get("my_reaction") or "")[:160]
    return ""


def _story_tail(root: Path, chars: int = 500) -> str:
    try:
        text = (root / "story.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[-chars:].strip()


def _exits(root: Path, player_node: str | None) -> dict[str, str]:
    """Adjacent places the player could walk to: id → name (from the registry's links; template-free)."""
    if not player_node:
        return {}
    try:
        from neonrp.core.registry import load_registry

        reg = load_registry(root)
        pid = reg.resolve(player_node, cls="place") or reg.player_location
        return {e.id.split("/")[-1]: e.name for e in reg.exits(pid or "")}  # bare ids, as the Jev choice options always were
    except Exception:
        return {}


def roster_rows(root: Path, playthrough: Any, understanding: Any) -> list[dict[str, Any]]:
    """Every soul with name / persona digest / last event / present flag."""
    from neonrp.core.light_chat import _display_name, _persona_digest

    away = {iid for iid, _n in (getattr(understanding, "away_roster", ()) or ())}
    # participation seam (mechanics.json): the RPG default keeps the scene's away roster (co-location by
    # location group); a template that registers its own predicate (werewolf: everyone) decides here.
    from neonrp.core import mechanics as _mech

    _part = None
    if _mech.spec(root).get("participation") != _mech.DEFAULTS["participation"]:
        from neonrp.core.registry import load_registry as _lr

        _reg = _lr(root)
        _fn = _mech.get(root, "participation")
        _part = lambda iid: bool(_fn(root, _reg, iid))  # noqa: E731
    rows: list[dict[str, Any]] = []
    for s in playthrough.souls:
        sdir = root / "souls" / f"{s.sid}-{s.instance_id}"
        if not sdir.is_dir():
            continue
        try:
            persona = _persona_digest(sdir)[:240]
        except Exception:
            persona = ""
        rows.append(
            {
                "iid": s.instance_id,
                "name": _display_name(sdir, s.sid),
                "present": _part(s.instance_id) if _part is not None else (s.instance_id not in away),
                "persona": persona,
                "last_event": _last_event(sdir),
                "role": str(getattr(s, "role", "") or "npc"),
            }
        )
    return rows


def build_state(root: Path, *, user_text: str, scene_packet: Any, player_intent: Any, rows: list[dict[str, Any]], exits: dict[str, str]) -> dict[str, Any]:
    return {
        "player_input": (user_text or "")[:800],
        "player_declared_action": str(getattr(player_intent, "declared_action", "") or "")[:400],
        "scene": str(getattr(scene_packet, "scene_label", "") or "")[:300],
        "scene_detail": (scene_packet.to_prompt_block() if hasattr(scene_packet, "to_prompt_block") else "")[:1500],
        "recent_story": _story_tail(root),
        "present_characters": [{k: r[k] for k in ("iid", "name", "persona", "last_event", "role")} for r in rows if r["present"]],
        "away_characters": [{k: r[k] for k in ("iid", "name", "persona", "last_event")} for r in rows if not r["present"]],
        "exits": exits,
    }


def build_questions(rows: list[dict[str, Any]], exits: dict[str, str]) -> dict[str, s1.Q]:
    present = [r for r in rows if r["present"]]
    qs: dict[str, s1.Q] = {
        "intent.kind": s1.choice(
            "Which kind is the player's input this turn",
            {
                "talk": "talks to a character: speaks, asks, answers",
                "act": "does a concrete action or uses an item (not just moving)",
                "move": "goes somewhere else / leaves this place",
                "observe": "observes, waits, does nothing, lets time pass",
                "meta": "a meta instruction outside the story (system settings, OOC, a pure rules question)",
            },
        ),
        "scene.tension": s1.score("The tension of the scene right now", list(TENSION_LEVELS)),
    }
    if present:
        addr = {r["iid"]: f"{r['name']}:{r['persona'][:60]}" for r in present}
        addr["none"] = "not addressing any particular character"
        qs["intent.addressee"] = s1.choice("Which present character is the player speaking to or acting toward", addr)
    if exits:
        mv = {nid: name for nid, name in exits.items()}
        mv["none"] = "not moving / no destination given"
        qs["intent.move"] = s1.choice("If the player moves, to which neighbouring place", mv)
    for r in present:
        qs[f"soul.{r['iid']}.reacts"] = s1.noul(
            f"Will the player's input this turn and what just happened make {r['name']} react",
            "named, seen, the matter touches someone or something they care about, or their nature will not let them keep still",
        )
        qs[f"soul.{r['iid']}.depth"] = s1.choice(
            f"How deeply does {r['name']} react this turn",
            {
                "silent": "no reaction, stays in the background",
                "gesture": "a gesture or a look, no words",
                "speak": "says a line or two, changes nothing",
                "act": "acts, decides, changes their own state or place",
            },
        )
    for r in rows:
        if not r["present"]:
            qs[f"away.{r['iid']}.stir"] = s1.noul(
                f"Given their goals and what just happened, will {r['name']}, who is not here, act on their own now (come over, get in touch, do their own thing)",
            )
    return qs


# ── planners ─────────────────────────────────────────────────────────────


def _fallback_depth() -> str:
    """Depth for present souls when no judge answers: ``act`` (today's agent
    loop, ≈15 s/soul in E1) or ``speak`` (one ask, ≈3 s). ``NEONRP_S1_FALLBACK_DEPTH``
    / engine.json ``turn.plan.fallback_depth``; decision-log R7."""
    raw = os.environ.get("NEONRP_S1_FALLBACK_DEPTH", "").strip().lower()
    return raw if raw in ("act", "speak", "gesture") else "act"


def fallback_plan(rows: list[dict[str, Any]], player_intent: Any, user_text: str) -> TurnPlan:
    """Today's behaviour as a plan: every present soul acts; nothing decided."""
    text = (user_text or "").casefold()
    depth = _fallback_depth()
    plan = TurnPlan(source="fallback", intent_kind="act" if getattr(player_intent, "kind", "") == "declared_action" else "observe")
    for r in rows:
        mentioned = bool(r["name"]) and r["name"].casefold() in text
        plan.souls[r["iid"]] = SoulPlan(
            iid=r["iid"], name=r["name"], present=r["present"],
            reacts=1.0 if r["present"] else 0.0,
            depth=depth if r["present"] else "silent",
            confidence=1.0,
        )
        if mentioned and r["present"] and plan.addressee is None:
            plan.addressee = r["iid"]
    return plan


def plan_from_answers(rows: list[dict[str, Any]], answers: dict[str, s1.Answer], *, source: str, ms: float) -> TurnPlan:
    thr = _react_threshold()
    plan = TurnPlan(source=source, ms=ms)
    k = answers.get("intent.kind")
    if k is not None and str(k.value) in INTENTS:
        plan.intent_kind = str(k.value)
        plan.intent_confidence = float(k.confidence)
    a = answers.get("intent.addressee")
    if a is not None and str(a.value) != "none" and s1.confidence_ok(a):
        plan.addressee = str(a.value)
    m = answers.get("intent.move")
    if m is not None and str(m.value) != "none" and plan.intent_kind == "move" and s1.confidence_ok(m):
        plan.move_target = str(m.value)
    t = answers.get("scene.tension")
    if t is not None:
        try:
            plan.tension = float(t.value) / max(1, len(TENSION_LEVELS) - 1)
        except (TypeError, ValueError):
            plan.tension = 0.0
    for r in rows:
        iid = r["iid"]
        if r["present"]:
            reacts = answers.get(f"soul.{iid}.reacts")
            depth = answers.get(f"soul.{iid}.depth")
            p = reacts.yes if reacts is not None else 1.0
            d = str(depth.value) if depth is not None and str(depth.value) in DEPTHS else "act"
            conf = min(float(reacts.confidence) if reacts else 1.0, float(depth.confidence) if depth else 1.0)
            if plan.addressee == iid:
                # Being spoken to always earns at least a spoken reply.
                p = max(p, 0.9)
                if d in ("silent", "gesture"):
                    d = "speak"
            elif not s1.confidence_ok(reacts):
                # No confident read on whether it reacts → the cheap safe
                # default is one spoken line, never a silent drop.
                d = "speak"
            elif p < thr and plan.tension < 0.7:
                d = "silent"
            elif p < thr:
                d = "speak"  # Q6 (09-27): E0 showed Jev judging `silent` with wolves closing in — high tension never goes silent
            elif not s1.confidence_ok(depth):
                # Unsure about depth → cheap spoken reply rather than a guess.
                d = "speak" if d in ("silent", "act") else d
            plan.souls[iid] = SoulPlan(iid=iid, name=r["name"], present=True, reacts=p, depth=d, confidence=conf)
        else:
            stir = answers.get(f"away.{iid}.stir")
            plan.souls[iid] = SoulPlan(iid=iid, name=r["name"], present=False, reacts=0.0, depth="silent", confidence=float(stir.confidence) if stir else 0.0, stir=stir.yes if stir else 0.0)
    plan.raw = {k: v.to_dict() for k, v in answers.items()}
    return plan


def build_turn_plan(root: Path, playthrough: Any, scene_packet: Any, player_intent: Any, understanding: Any, *, user_text: str) -> TurnPlan:
    rows = roster_rows(root, playthrough, understanding)
    exits = _exits(root, getattr(understanding, "player_node", None))
    if not s1.available() or not rows:
        return fallback_plan(rows, player_intent, user_text)
    state = build_state(root, user_text=user_text, scene_packet=scene_packet, player_intent=player_intent, rows=rows, exits=exits)
    questions = build_questions(rows, exits)
    answers = s1.ask(state, questions, log_dir=root / ".neonrp" / "logs")
    if not answers:
        return fallback_plan(rows, player_intent, user_text)
    call = s1.last_call()
    return plan_from_answers(rows, answers, source=str(call.get("backend") or "jev"), ms=float(call.get("ms") or 0.0))


def plan_followups(root: Path, responses: list[dict[str, Any]], *, user_text: str) -> dict[str, float]:
    """「再次沟通是否需要」— after the souls answered, does the
    world-agent still need another exchange with any of them before it can
    narrate? ``{iid: probability}``; empty when System One is unavailable
    (the caller then leaves the world-agent's tools untouched)."""
    if not s1.available() or not responses:
        return {}
    state = {
        "player_input": (user_text or "")[:600],
        "responses": [{"iid": r.get("iid"), "name": r.get("name"), "kind": r.get("kind"), "text": str(r.get("text") or "")[:500]} for r in responses],
    }
    qs = {
        f"followup.{r.get('iid')}": s1.noul(
            f"Before writing this turn's narration, must the host ask {r.get('name')} once more (their answer left a suspense, a counter-question or a choice only they can answer)",
            "yes only when the story cannot go on consistently without asking",
        )
        for r in responses
        if r.get("iid")
    }
    answers = s1.ask(state, qs, log_dir=root / ".neonrp" / "logs")
    if not answers:
        return {}
    out: dict[str, float] = {}
    for r in responses:
        iid = str(r.get("iid") or "")
        a = answers.get(f"followup.{iid}")
        if a is not None:
            out[iid] = a.yes if s1.confidence_ok(a) else 0.5
    return out
