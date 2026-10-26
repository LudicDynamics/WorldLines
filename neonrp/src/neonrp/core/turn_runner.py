"""The turn as steps (10-17 batch 4 · S3, the strangler): sections of ``ConversationSession._run_multi_agent_turn`` moved
here verbatim, one function per step of core/turn_steps, sharing the turn's state through a :class:`TurnCtx`. The turn
still calls them in today's fixed order; S4 runs them off the graph's node steps. ``self`` is the session.

Behaviour is held to tests/golden/turns (the golden record of the turn): a move here must not change a byte of it.
"""
from __future__ import annotations

import json
import logging
import os
import time
from types import SimpleNamespace
from typing import Any

from neonrp.core import engine_config as _ecfg  # the old function imported it in the S1 section; S2 reads it too

logger = logging.getLogger("neonrp.core.conversation")


class TurnCtx(SimpleNamespace):
    """What the turn's steps hand each other (the old function's locals, by their old names)."""



def s1_plan(self: Any, c: TurnCtx) -> None:
    """S1 · the turn plan (Jev first; the fallback plan without it) — and the v3 switch that forces it on."""
    playthrough = c.playthrough
    scene_packet = c.scene_packet
    player_intent = c.player_intent
    _understanding = c._understanding
    user_text = c.user_text
    _trace = c._trace
    _ma_t_start = c._ma_t_start
    # ── S1 / S2 (exp/jev-system-one) ──────────────────────────────
    # NEONRP_SYSTEM_ONE: "" = off (today's V2b roll-call: the host names who acts), "observe" = plan
    # only (record the prediction, change nothing), "1" = plan + run the
    # planned souls IN PARALLEL before the world-agent, which then
    # integrates instead of hosting a serial tool loop.
    _s1_mode = os.environ.get("NEONRP_SYSTEM_ONE", "").strip().lower()
    # engine v3 (five-phase loop) needs the souls to run BEFORE solve —
    # force the S1/S2 block on; without Jev it is the all-present-act
    # fallback plan. Spans (§11) are timed from here.
    from neonrp.core import engine_config as _ecfg

    _v3 = _ecfg.v3_enabled(self.root)
    _v3_spans: list[dict[str, Any]] = []
    _v3_t_base = _ma_t_start
    if _v3 and _s1_mode != "1":
        _s1_mode = "1"
    _s1_plan: Any = None
    _s1_handled: dict[str, dict[str, Any]] = {}
    _s1_hb_lines: dict[str, str] = {}
    _s1_disable_tools: set[str] = set()
    _s1_timing: dict[str, Any] = {}
    if _s1_mode in ("1", "observe"):
        _s1_t0 = time.monotonic()
        _s1_timing["t_s1"] = round((_s1_t0 - _ma_t_start) * 1000, 1)
        try:
            from neonrp.core.turn_plan import build_turn_plan

            _s1_plan = build_turn_plan(
                self.root, playthrough, scene_packet, player_intent, _understanding,
                user_text=user_text or "",
            )
        except Exception:  # noqa: BLE001 — a plan failure is the old path
            logger.debug("S1 plan failed", exc_info=True)
            _s1_plan = None
        _s1_timing["plan_ms"] = round((time.monotonic() - _s1_t0) * 1000, 1)
        if _s1_plan is not None:
            _trace.plan = _s1_plan.to_dict()
    c._v3 = _v3
    c._v3_spans = _v3_spans
    c._v3_t_base = _v3_t_base
    c._s1_mode = _s1_mode
    c._s1_plan = _s1_plan
    c._s1_handled = _s1_handled
    c._s1_hb_lines = _s1_hb_lines
    c._s1_disable_tools = _s1_disable_tools
    c._s1_timing = _s1_timing


def away_turn(root: Any, iid: str, *, provider: str | None, mode: str, cs: dict[str, Any]) -> dict[str, Any]:
    """One character elsewhere takes her own turn where she is, off the player's screen (S2's away path, the fifth
    characters' orchestration; core/world_exec calls it too): what she observes there · S-direct, one call — no
    soul_turn mechanic = she answers in her voice. ``{ok, name, text, proposed_move}``; never raises."""
    from neonrp.core.light_chat import ask_soul_deliver

    try:
        from neonrp.core import mechanics as _mech_a

        _note_a = _mech_a.get(root, "observe")(root, iid)
    except Exception:  # noqa: BLE001
        _note_a = ""
    _note_a += cs["away_note"]
    from neonrp.core.adv import soul_lang_line as _sll

    _note_a += "".join("\n\n" + x for x in (_sll(root),) if x)  # C3-2: her lines are shown as written
    try:
        from neonrp.core import mechanics as _mech_b

        _r_a = _mech_b.get(root, "soul_turn")(
            root, iid, situation=_note_a, depth="speak",
            provider=provider, mode=mode, variant="S-direct",
        )
        if not isinstance(_r_a, dict):  # no soul_turn mechanic (builtin:none): she just answers in her voice
            _r_d = ask_soul_deliver(root, iid, _note_a + cs["away_ask"], asker="world-agent")
            _r_a = {"ok": bool(_r_d.get("ok")), "name": _r_d.get("name"), "text": str(_r_d.get("answer") or ""),
                    "proposed_move": None}
        return _r_a
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def s2_souls(self: Any, c: TurnCtx) -> None:
    """S2 · the characters act in parallel at the depth S1 gave (present · away); their reports are collected."""
    playthrough = c.playthrough
    player_intent = c.player_intent
    user_text = c.user_text
    soul_status = c.soul_status
    _emit_status = c._emit_status
    cap = c.cap
    _active_iid_set = c._active_iid_set
    _soul_responses = c._soul_responses
    scene = c.scene
    _v3 = c._v3
    _s1_plan = c._s1_plan
    _s1_handled = c._s1_handled
    _s1_hb_lines = c._s1_hb_lines
    _s1_timing = c._s1_timing
    from concurrent.futures import ThreadPoolExecutor

    from neonrp.core.engage import engage_soul_run, heartbeat_soul_run
    from neonrp.core.light_chat import ask_soul_deliver

    _said_now = (getattr(player_intent, "declared_action", "") or user_text or "")[:300]
    _understood_block = ""
    if _v3:  # P0 (10-01): the player is one actor among the souls — their words reach the souls as an attempt,
        # with what the world says about each thing they mention (nobody vouches for a phantom)
        try:
            from neonrp.core import mechanics as _mech_u
            from neonrp.core.registry import load_registry as _load_reg_u

            _understood_block = str((_mech_u.get(self.root, "understand")(self.root, _load_reg_u(self.root), user_text or "") or {}).get("block") or "")
        except Exception:  # noqa: BLE001 — understanding is a help, never a failure
            _understood_block = ""
    _situation = self._cs()["situation"].replace("{scene}", str(scene)) + (_understood_block or _said_now)
    self._gate_now = None
    _seen_now = ""
    if _v3:  # 10-02: the player and the souls are players alike — each reads the world's prose and acts.
        # The gate runs before the souls: its ``seen`` is the player's beat as a bystander meets it.
        try:
            from neonrp.core import player_gate as _pg_s, soul_view as _sv
            from neonrp.core.registry import load_registry as _load_reg_s

            _reg_s = _load_reg_s(self.root)
            _hist_s = [{"assistant": str(m.content or "")} for m in self.messages if getattr(m, "role", "") == "assistant" and m.content][-3:]
            self._gate_now = _pg_s.gate(self.root, _reg_s, user_text or "", _hist_s, branch=self.branch) if (user_text or "").strip() else None
            _seen_now = str((self._gate_now or {}).get("seen") or "") or _sv.seen_fallback(_said_now, _sv.player_name(_reg_s), self.root)
        except Exception:  # noqa: BLE001 — never blocks the souls
            logger.debug("pre-soul gate skipped", exc_info=True)
            _seen_now = ""

    def _soul_situation(iid: str) -> str:
        # v3: the soul's observation o_i is an engine-scoped pack view
        # (its own location, who is there, its own state) — not the
        # GM scene text. Falls back to the plain situation line.
        if not _v3:
            return _situation
        if _seen_now:  # 10-02: the world's prose for her + the player's beat + her own context — not a block dump
            try:
                from neonrp.core import soul_view as _sv2
                from neonrp.core.registry import load_registry as _lr2

                return _sv2.beat_text(self.root, _lr2(self.root), iid, seen=_seen_now)
            except Exception:  # noqa: BLE001
                logger.debug("soul beat text failed; pack view", exc_info=True)
        try:
            from neonrp.core import mechanics as _mech

            return _mech.get(self.root, "observe")(self.root, iid) + "\n\n" + _situation
        except Exception:  # noqa: BLE001
            return _situation

    # 10-04, "in principle every character needs its 1 turn": in a talked-over Resolve only the characters who were in the talk
    # (here, with the player) skip their own turn — their part was agreed (D7) and they carry it out in the prose;
    # everyone elsewhere takes her turn as usual, in parallel (she was not in the talk, nothing was agreed for her)
    _talked_here: set[str] = set()
    _away_now: set[str] = set()
    if getattr(self, "_pl_resolve", None):
        try:
            from neonrp.core.registry import load_registry as _lr_here

            _reg_here = _lr_here(self.root)
            _here = _reg_here.player_location
            _souls_here = {e.id for e in _reg_here.of_class("soul") if _here and e.parent == _here}
            if self._pl_resolve.get("advanced_by") != "world:trivial":
                _talked_here = _souls_here
            # 10-05, "Elena just stands still in the adventurers' guild": away souls were always `silent` (turn_plan) and never acted.
            # In a Resolve each takes her own turn where she is — off the player's screen (she is not written into
            # the player's prose); what she does lands as her own move + her memory, and shows as an "away" line.
            _away_now = {e.id for e in _reg_here.of_class("soul") if e.id not in _souls_here}
        except Exception:  # noqa: BLE001
            _talked_here = set(_active_iid_set)
    _jobs: list[tuple[Any, str]] = []
    try:  # the dead take no turn (packs/rpg/downed.py — a world's state, read through the registry)
        from neonrp.core.registry import load_registry as _lr_dead

        _dead = {e.id for e in _lr_dead(self.root).of_class("soul") if int(e.props.get("dead") or 0)}
    except Exception:  # noqa: BLE001
        _dead = set()
    for _s in playthrough.souls:
        if _s.instance_id not in _active_iid_set or _s.instance_id in _dead:
            continue
        _d = _s1_plan.depth_of(_s.instance_id)
        if _v3 and _s.instance_id in _away_now and _d == "silent":
            _d = "away"
        if _d == "silent" or _s.instance_id in _talked_here:
            continue
        _jobs.append((_s, _d))
    _engage_max = int(os.environ.get("NEONRP_S1_ENGAGE_TURNS", "3") or 3)
    _variant_default = str(_ecfg.get(self.root, "turn.parallel.souls.default_variant", "legacy")) if _v3 else "legacy"
    _variant_per = _ecfg.get(self.root, "turn.parallel.souls.per_soul", {}) if _v3 else {}

    def _variant_of(iid: str, sid: str) -> str:
        if isinstance(_variant_per, dict):
            return str(_variant_per.get(iid) or _variant_per.get(sid) or _variant_default)
        return _variant_default

    # which variant each soul's turn ran under (the trace's timing.soul_variants; the bench's in_world node shows the setting)
    _s1_timing["soul_variants"] = {_s.instance_id: ("S-direct" if _d == "away" else _variant_of(_s.instance_id, _s.sid)) for _s, _d in _jobs}

    def _run_job(job: tuple[Any, str]) -> tuple[Any, str, dict[str, Any]]:
        _js, _jd = job
        if _jd == "away":  # her own place, her own time — she did not see the player's beat
            return _js, _jd, away_turn(self.root, _js.instance_id, provider=self.provider, mode=self.mode, cs=self._cs())
        _note = _soul_situation(_js.instance_id)
        from neonrp.core.adv import soul_lang_line as _sll2

        _note += "".join("\n\n" + x for x in (_sll2(self.root),) if x)  # C3-2: cross-language runs only
        try:
            _variant = _variant_of(_js.instance_id, _js.sid)
            if _variant in ("S-judge", "S-direct", "S-free"):
                from neonrp.core import mechanics as _mech

                return _js, _jd, _mech.get(self.root, "soul_turn")(
                    self.root, _js.instance_id, situation=_note, depth=_jd,
                    provider=self.provider, mode=self.mode, variant=_variant,
                )
            if _jd == "act":
                return _js, _jd, engage_soul_run(
                    self.root, _js.instance_id, note=_note,
                    provider=self.provider, mode=self.mode, max_turns=_engage_max,
                )
            if _jd == "speak":
                return _js, _jd, ask_soul_deliver(
                    self.root, _js.instance_id, _note + self._cs()["respond_or_do"],
                    asker="world-agent",
                )
            return _js, _jd, heartbeat_soul_run(self.root, _js, _note)
        except Exception as exc:  # noqa: BLE001 — one soul failing never kills S2
            return _js, _jd, {"ok": False, "error": str(exc)[:200]}

    _s2_t0 = time.monotonic()
    _results: list[tuple[Any, str, dict[str, Any]]] = []
    if _jobs:
        for _js, _jd in _jobs:
            soul_status[_js.instance_id]["state"] = "running"
        _emit_status()
        from neonrp.core import beat_budget as _bb_s2

        # the characters' own turns are one beat (10-14: ~10 s, never over 20 s) — a soul still talking when it
        # ends gets no more model calls: her turn is skipped (degraded), the world settles without it
        with _bb_s2.beat("souls", root=self.root, reserve=_bb_s2.world_reserve_s(self.root)), ThreadPoolExecutor(
            max_workers=min(max(1, cap), len(_jobs)), thread_name_prefix="neonrp-s2"
        ) as _ex:
            _results = list(_ex.map(_bb_s2.carry(_run_job), _jobs))
    _seq = 0
    self._away_turns = []
    for _js, _jd, _out in _results:
        _iid = _js.instance_id
        if not _out.get("ok"):
            soul_status[_iid]["state"] = "degraded"
            continue
        if _jd == "away":  # off the player's screen: not a report for the narrator, only her move + a side line
            self._away_turns.append({"iid": _iid, "name": _out.get("name") or _iid, "text": str(_out.get("text") or ""),
                                     "move_to": _out.get("proposed_move")})
            soul_status[_iid]["state"] = "completed"
            continue
        if _out.get("judgment") is not None:
            _k = str(_out.get("kind") or _jd)
            _text = str(_out.get("text") or "")
            _s1_handled[_iid] = {"kind": _k, "text": _text, "name": _out.get("name"),
                                 "judgment": _out.get("judgment"), "proposed_move": _out.get("proposed_move")}
            _seq += 1
            _mv = self._cs()["going"].replace("{to}", str(_out['proposed_move'])) if _out.get("proposed_move") else ""
            _soul_responses.append((_seq, {"instance_id": _iid, "digest": f"{_out.get('name')}{_mv}:{_text}", "feeds_world": True}))
            soul_status[_iid]["state"] = "completed" if _k != "gesture" else "heartbeat"
            continue
        if _jd == "act":
            _text = str(_out.get("digest") or "")
            _s1_handled[_iid] = {"kind": "act", "text": _text, "name": _out.get("name")}
            _seq += 1
            _soul_responses.append((_seq, {"instance_id": _iid, "digest": _text, "feeds_world": True}))
            soul_status[_iid]["state"] = str(_out.get("state") or "completed")
        elif _jd == "speak" and not _out.get("idle"):  # idle = she chose to do nothing this beat (10-02)
            _text = str(_out.get("answer") or "")
            _s1_handled[_iid] = {"kind": "speak", "text": _text, "name": _out.get("name")}
            _seq += 1
            _soul_responses.append(
                (_seq, {"instance_id": _iid, "digest": self._cs()["only_spoke"].replace("{name}", str(_out.get('name'))).replace("{text}", _text), "feeds_world": True})
            )
            soul_status[_iid]["state"] = "completed"
        else:
            _s1_hb_lines[_iid] = str(_out.get("line") or "")
            _s1_handled[_iid] = {"kind": "gesture", "text": _out.get("line"), "name": _out.get("name")}
            soul_status[_iid]["state"] = "heartbeat"
    _emit_status()
    _s1_timing["souls_ms"] = round((time.monotonic() - _s2_t0) * 1000, 1)
    _s1_timing["souls"] = {i: h["kind"] for i, h in _s1_handled.items()}


def followups(self: Any, c: TurnCtx) -> None:
    """S1 follow-up · after the souls answered: does the host still need to ask anyone (else the ask tools go)."""
    user_text = c.user_text
    _s1_plan = c._s1_plan
    _s1_handled = c._s1_handled
    _s1_disable_tools = c._s1_disable_tools
    _s1_timing = c._s1_timing
    # "is a second round of talk needed?" — unless a soul's answer left a question
    # only it can settle, the world-agent integrates (no re-engage).
    if os.environ.get("NEONRP_S1_KEEP_TOOLS", "") != "1":
        _fu: dict[str, float] = {}
        _resp = [
            {"iid": i, "name": h.get("name"), "kind": h["kind"], "text": h.get("text")}
            for i, h in _s1_handled.items()
            if h["kind"] in ("act", "speak")
        ]
        if _resp and not _s1_plan.is_fallback:
            _fu_t0 = time.monotonic()
            try:
                from neonrp.core.turn_plan import plan_followups

                _fu = plan_followups(self.root, _resp, user_text=user_text or "")
            except Exception:  # noqa: BLE001
                _fu = {}
            _s1_timing["followups_ms"] = round((time.monotonic() - _fu_t0) * 1000, 1)
        _s1_timing["followups"] = _fu
        if not any(p >= 0.7 for p in _fu.values()):
            _s1_disable_tools = {"engage_soul", "ask_soul"}
    c._s1_disable_tools = _s1_disable_tools


def s1_spans(self: Any, c: TurnCtx) -> None:
    """The S1 / S2 timing into the trace and the v3 span timeline."""
    _trace = c._trace
    _v3 = c._v3
    _v3_spans = c._v3_spans
    _s1_plan = c._s1_plan
    _s1_handled = c._s1_handled
    _s1_timing = c._s1_timing
    _trace.timing.update(_s1_timing)
    if _v3:
        _t_s1 = float(_s1_timing.get("t_s1", 0.0))
        _pm = float(_s1_timing.get("plan_ms") or 0.0)
        _sm = float(_s1_timing.get("souls_ms") or 0.0)
        _fm = float(_s1_timing.get("followups_ms") or 0.0)
        _src = str(getattr(_s1_plan, "source", "fallback") or "fallback")
        _v3_spans.append({"phase": "plan", "actor": "scene", "backend": "python", "t0": 0.0, "t1": _t_s1})
        _v3_spans.append({"phase": "plan", "actor": _src, "backend": "jev" if _src in ("jev", "proxy") else ("llm" if _src == "llm" else "python"),
                          "t0": _t_s1, "t1": _t_s1 + _pm})
        for _iid, _h in _s1_handled.items():
            _v3_spans.append({"phase": "parallel", "actor": f"soul:{_iid}", "backend": "llm" if _h["kind"] != "gesture" else "python",
                              "t0": _t_s1 + _pm, "t1": _t_s1 + _pm + _sm, "kind": _h["kind"]})
        if _fm:
            _v3_spans.append({"phase": "plan", "actor": "followups", "backend": "jev" if _src in ("jev", "proxy") else "llm",
                              "t0": _t_s1 + _pm + _sm, "t1": _t_s1 + _pm + _sm + _fm})


def intake(self: Any, c: TurnCtx) -> None:
    """The player's line at the raw-input boundary: a command that hands the beat on (core/player_action) · the inbox's directives · a plugin's before_turn · the player-agent's intake."""
    playthrough = c.playthrough
    user_text = c.user_text
    # M20 §3 step 1 — player-agent intake. The player-agent is a distinct
    # archetype/step even at N=1 (never inlined into the world-agent). It
    # owns the raw-input boundary; raw input dies here and never reaches
    # souls. Multi-player iterates players[]; v1 drives the first.
    from neonrp.core.player_agent import player_agents_for

    player_agents = player_agents_for(self.root, playthrough)
    # V0 inbox contract (DESIGN-VISIONRP §2) — out-of-band directives
    # written by other clients (Obsidian / Dashboard / Claude Code) join
    # the turn at the same raw-input boundary as typed input.
    from neonrp.core.player_artifacts import drain_inbox

    # A command that hands the beat on (core/player_action, 10-14): "/spot-hidden the well" is rolled now by the pack, the
    # host is told the result, and the beat reads the player's words as "I use Spot Hidden: the well."; "/go car 3" is the
    # world action's prompt.
    self._act_ctx = None
    try:
        from neonrp.core import player_action as _pa

        self._act_ctx = _pa.prepare(self.root, user_text or "", turn=self._multi_agent_turn_seq())
    except Exception:  # noqa: BLE001 — a command never blocks a turn: it goes on as plain words
        logger.warning("player command not read; plain words", exc_info=True)
        self._act_ctx = None
    if self._act_ctx and self._act_ctx.get("say"):
        user_text = str(self._act_ctx["say"])
    _inbox_notes = drain_inbox(self.root)
    # a node-kind plugin's step before the turn reads the world (node_kinds.call_all; none in the open engine, 10-18)
    from neonrp.core import node_kinds as _nk_bt

    _nk_bt.call_all("before_turn", self.root)
    if _inbox_notes:
        user_text = (user_text or "") + self._cs()["inbox_head"] + "\n".join(
            f"- {note}" for note in _inbox_notes
        )
    player_intent = player_agents[0].intake(user_text)
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_pa', 'player_agents', 'player_intent', 'user_text') if k in _out})


def clock(self: Any, c: TurnCtx) -> None:
    """The world clock moves before anyone perceives (not while the planning beat talks) · the scene packet."""
    build_scene_packet = c.build_scene_packet
    player_intent = c.player_intent
    user_text = c.user_text
    # M23 — engine world clock. Advance the SINGLE authoritative time
    # (run_state.time) by Δ BEFORE any perception is built, so souls, the
    # player, and away-location agents all see the same freshly-advanced
    # time this turn. Pure code, idempotent per turn, replay-safe — time is
    # no longer owned by an LLM (clock-keeper) at the turn's tail, which
    # caused one-turn perception lag + dual time sources + frozen away lines.
    from neonrp.core.world_clock import tick_world
    from neonrp.core import node_kinds as _nk_clk

    _pl_on = bool(_nk_clk.call("plan", "active", self.root, user_text, default=False))
    if not _pl_on:  # 10-03: while talking the clock stands still; a Resolve ticks it below
        tick_world(self.root)
    scene_packet = build_scene_packet(self.root, player_intent)
    scene = scene_packet.scene_label or self._cs()["scene_unreadable"]
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_pl_on', 'scene', 'scene_packet', 'tick_world') if k in _out})


def scene_route(self: Any, c: TurnCtx) -> None:
    """Who is here: scene understanding writes the active souls by locality; clamped to the concurrent cap."""
    playthrough = c.playthrough
    scene_packet = c.scene_packet
    world_agent = c.world_agent
    # M18 §3 scene-understanding — the deterministic routing step. It runs
    # BEFORE any soul thinks and writes playthrough.json active_souls by
    # locality (souls co-located with the player are active; others are not
    # reached). This is file-as-router: the routing decision lands in a
    # file, not in the world-agent — the world-agent no longer routes.
    # Re-read the manifest so active_soul_refs() reflects what was written.
    from neonrp.core.playthrough import read_playthrough as _read_playthrough
    from neonrp.core.scene_understanding import broadcast, understand_scene  # noqa: F401 — broadcast rides on in _out = locals()

    _understanding = understand_scene(self.root, playthrough, scene_packet)
    playthrough = _read_playthrough(self.root) or playthrough

    active_refs = playthrough.active_soul_refs()
    # M18 §2.3 hard cap: never run more concurrent souls than the
    # ceiling. Over-listed active_souls is a content misconfig — clamp
    # (keep the game running) + warn, naming the deferred souls.
    cap = world_agent.concurrent_cap
    if len(active_refs) > cap:
        deferred = active_refs[cap:]
        logger.warning(
            "multi-agent: active_souls (%d) exceeds concurrent cap (%d); "
            "running first %d, deferring: %s",
            len(active_refs),
            cap,
            cap,
            ", ".join(s.instance_id for s in deferred),
        )
        active_refs = active_refs[:cap]
    logger.info(
        "multi-agent: %d/%d souls active this turn: %s",
        len(active_refs),
        len(playthrough.souls),
        ", ".join(s.instance_id for s in active_refs) or "<none>",
    )
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_understanding', 'active_refs', 'broadcast', 'cap', 'playthrough') if k in _out})


def v3_resolve(self: Any, c: TurnCtx) -> None:
    """Engine v3's Resolve beat: the narrator's one structured call (core/turn_v3.solve_turn: pack · understand · gate · layer · solve · verify · apply) streamed to the screen, then the souls settle and the after-turn jobs run."""
    from neonrp.core.conversation import ConversationTurnResult, Message, prompt_lang_of, v3_history_pairs  # the old function's module globals
    _s1_handled = c._s1_handled
    _s1_plan = c._s1_plan
    _trace = c._trace
    _v3 = c._v3
    _v3_spans = c._v3_spans
    _v3_t_base = c._v3_t_base
    on_chunk = c.on_chunk
    persist_message = c.persist_message
    run_id = c.run_id
    turn_seq = c.turn_seq
    user_text = c.user_text
    _v3_out: dict[str, Any] | None = None
    if _v3:
        # ③ SOLVE → ④ VERIFY → ⑤ APPLY through the SDK (engine v3). The
        # world-agent tool loop is not run; ops land via registered
        # handlers, the ApplyResult goes to the trace.
        from neonrp.core import turn_v3 as _turn_v3

        # The chat history as real chat turns (Yumina): the player's earlier lines and the narrator's earlier
        # outputs go to the model as alternating user / assistant messages, not as a pasted digest
        _v3_history = v3_history_pairs(self.messages, prompt_lang_of(self.root))
        _v3_history = _v3_history[-6:]
        try:  # the narrator reads its past turns annotated (requests, engine answers, state changes in place)
            from neonrp.core.orchestration_trace import read_turn_traces as _rtt

            _ann = {str((x.get("apply") or {}).get("narration_plain") or ""): str((x.get("apply") or {}).get("annotated") or "")
                    for x in (_rtt(self.root, self.branch, last=8) or [])}
            for _h in _v3_history:
                if _ann.get(_h["assistant"]):
                    _h["assistant"] = _ann[_h["assistant"]]
        except Exception:  # noqa: BLE001 — history falls back to the plain prose
            pass
        from neonrp.core import soul_remote as _sr

        _remote_iids = set(_sr.remote_iids())  # 10-10: a character played from elsewhere speaks / moves only through her own seat
        _s1_handled = {i: h for i, h in _s1_handled.items() if i not in _remote_iids}
        _v3_reports = [
            {"iid": i, "name": h.get("name"), "kind": h["kind"], "text": h.get("text"),
             **({"judgment": h["judgment"]} if h.get("judgment") else {}),
             **({"proposed_move": h["proposed_move"]} if h.get("proposed_move") else {})}
            for i, h in _s1_handled.items()
        ]
        if getattr(self, "_pl_resolve", None):  # what the node before agreed for each person present (the plugin says)
            from neonrp.core import node_kinds as _nk_rb

            _v3_reports += list(_nk_rb.call("plan", "reports", self._pl_resolve, self.root, default=[]) or [])
        else:  # gather (10-10): the people playing characters here say what they do this turn, before it settles
            try:
                from neonrp.core import gather as _gather

                _v3_reports += _gather.collect(self.root, user_text or "")
            except Exception:  # noqa: BLE001 — gathering never blocks the turn
                logger.warning("gather failed", exc_info=True)
        _v3_soul_ops = [
            {"op": "move_to", "who": i, "to": h["proposed_move"], "_from": "soul"}
            for i, h in _s1_handled.items() if h.get("proposed_move")
        ] + [
            {"op": "move_to", "who": a["iid"], "to": a["move_to"], "_from": "soul"}
            for a in (getattr(self, "_away_turns", None) or []) if a.get("move_to")
        ]
        _v3_facts = ""
        if getattr(self, "_pl_resolve", None):
            from neonrp.core import node_kinds as _nk_f

            _v3_facts = str(_nk_f.call("plan", "facts", self._pl_resolve, self.root, default="") or "") + "\n\n"
        # what the node before already ruled (its agreed payments): landed by the engine, not left to the prose (10-22)
        _v3_ruled = list(_nk_f.call("plan", "ruled", self._pl_resolve, self.root, default=[]) or []) if getattr(self, "_pl_resolve", None) else []
        if getattr(self, "_act_ctx", None) and self._act_ctx.get("facts"):  # the engine already rolled the player's skill
            _v3_facts += str(self._act_ctx["facts"]) + "\n\n"
        if _s1_plan is not None and not _s1_plan.is_fallback:
            _v3_facts += self._cs()["s1_head"].replace("{intent}", str(_s1_plan.intent_kind)).replace("{tension}", f"{_s1_plan.tension:.2f}") + (
                self._cs()["s1_move"].replace("{to}", str(_s1_plan.move_target)) if _s1_plan.move_target else "")

        _v3_exec_n: dict[str, int] = {}

        def _v3_ask(who: str, ctx: str) -> dict[str, Any]:
            from neonrp.core.light_chat import ask_soul_deliver as _ask

            if getattr(self, "_pl_resolve", None):
                # a Resolve from the talk: she carries out what she agreed — her own beat, at most twice
                # (the haggle read best with her own lines; it is acting, not another round of talk)
                from neonrp.core import node_kinds as _nk_x

                _c = _nk_x.call("plan", "carry", self._pl_resolve, self.root, who, ctx, _v3_exec_n)
                if _c is None:
                    return {"ok": False, "error": "she has acted twice this Resolve"}
                _iid_x, _q, _bt = _c
                return _ask(self.root, _iid_x, _q, asker="world-agent", beat=_bt)
            return _ask(self.root, who, ctx + self._cs()["respond"], asker="world-agent")

        try:
            # The prose reaches the screen as it is written (the narrate shape only: its prose is never
            # rewritten once shown). Header and the agreed dice first, tool answers where they happen, state at the end.
            from neonrp.core import beat_display as _bd_r
            from neonrp.core import node_kinds as _nk_r
            from neonrp.core import orchestration as _orch_r

            _r_streamed = False
            _r_stream = on_chunk is not None and _orch_r.solve_structured(self.root) in ("narrate", "describe", "jevjson", "jevjson-inline")
            _r_show = _bd_r.enabled(self.root)
            _turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
            if _r_stream:
                _head = []
                if _r_show:
                    _head.append(f"// {self._landing_header()}")
                if getattr(self, "_pl_resolve", None):
                    _head += list(_nk_r.call("plan", "head_lines", self._pl_resolve, self.root, default=[]) or [])
                if _head:
                    on_chunk("\n".join(_head) + "\n")

                try:
                    from neonrp.core.output_lang import prompt_lang as _r_pl

                    _r_lang = _r_pl(self.root)
                except Exception:  # noqa: BLE001
                    _r_lang = "zh"

                def _r_event(kind: str, data: dict[str, Any]) -> None:
                    if not _r_show:
                        return
                    line = _bd_r._dice_line(data, _bd_r._lang(self.root)) if kind == "tool" else None
                    on_chunk("\n" + (line or f"[{data.get('request')}] → {_bd_r._short(str(data.get('text') or data.get('why') or ''), 70)}") + "\n")

                _turn_v3.STREAM.update(on_text=on_chunk, on_event=_r_event)
            self._enter_beat("resolve", turn_seq)
            from neonrp.core import beat_budget as _bb_w

            try:
                # the world's beat: its prose ≤ the beat (and ends settle_s before the turn does), then it settles
                from neonrp.core.llm_openai import thinking as _think_w

                _bb_w.floor(_bb_w.world_floor_s(self.root), "world.floor")  # the prose's share + the transition's
                with _bb_w.beat("world", root=self.root, reserve=_bb_w.settle_s(self.root)), _think_w(_bb_w.narrate_thinking(self.root)):
                    _v3_out = _turn_v3.solve_turn(
                        self.root, user_text=user_text or "", provider=self.provider, turn=turn_seq,
                        soul_reports=_v3_reports, plan_facts=_v3_facts, history=_v3_history,
                        spans=_v3_spans, t_base=_v3_t_base, ask_soul=_v3_ask, soul_ops=_v3_soul_ops,
                        intent_kind=str(getattr(_s1_plan, "intent_kind", "") or ""), branch=self.branch,
                        gate=getattr(self, "_gate_now", None),
                        rolled=list((getattr(self, "_pl_resolve", None) or {}).get("rolled") or []),
                        talk=list((getattr(self, "_pl_resolve", None) or {}).get("talk") or []) if getattr(self, "_pl_resolve", None) else None,
                        ruled_ops=_v3_ruled,
                    )
                self._companions_judged = {str(j.get("iid")): j for j in _v3_out.get("companions") or []}
            finally:
                _r_streamed = bool(_turn_v3.STREAM.get("shown"))
                _turn_v3.STREAM.update(on_text=None, on_event=None, shown=False)
        except Exception as exc:  # noqa: BLE001 — fall back to the v2b world-agent
            if os.environ.get("NEONRP_V3_STRICT", "").strip() in ("1", "true", "on"):  # benchmarks / CI: a v3 crash is a failure, not a quiet fallback (10-02)
                raise
            logger.warning("engine v3 solve failed, falling back to world-agent: %s", exc, exc_info=True)
            _v3_out = None
        if _v3_out is not None:
            _narr = _v3_out["narration"]
            if getattr(self, "_pl_resolve", None):
                # the agreed checks, shown as dice lines before what happened (the TUI colours this skeleton)
                try:
                    from neonrp.core import node_kinds as _nk_d

                    _dl = list(_nk_d.call("plan", "head_lines", self._pl_resolve, self.root, default=[]) or [])
                    if _dl:
                        _narr = "\n".join(_dl) + "\n\n" + _narr
                except Exception:  # noqa: BLE001
                    logger.debug("dice lines skipped", exc_info=True)
            _m = Message(role="assistant", content=_narr)
            self.messages.append(_m)
            try:
                persist_message(_m)
            except Exception:  # noqa: BLE001
                logger.debug("v3 persist skipped", exc_info=True)
            _shown = _narr
            try:
                from neonrp.core import beat_display as _bd3

                if _bd3.enabled(self.root):
                    _shown = _bd3.resolve_text(self.root, _v3_out, self._landing_header(), _narr)
            except Exception:  # noqa: BLE001 — the display never breaks a turn
                logger.debug("beat display skipped", exc_info=True)
            # what the characters elsewhere did this beat (their own turns, off the player's prose) — a side line
            _away_lines: list[str] = []
            try:
                from neonrp.core import beat_display as _bd4
                from neonrp.core.registry import load_registry as _lr_aw

                from neonrp.core.output_lang import prompt_lang as _pl_aw

                from neonrp.core.turn_v3 import is_timeout_line as _tol

                _reg_aw = _lr_aw(self.root)
                # a beat that wrote nothing in time: no lines from elsewhere hung on its short notice (10-25)
                _away_lines = [] if _tol(_narr) else _bd4.away_lines(_reg_aw, getattr(self, "_away_turns", None) or [], _pl_aw(self.root))
                if _away_lines:  # the whole lines, ahead of the cut prose line: the TUI folds them (10-08)
                    from neonrp.core import topics as _tp_aw

                    self.bus().publish(_tp_aw.ENGINE_BEAT, {"kind": "away", "turn": turn_seq,
                                                            "items": _bd4.away_items(_reg_aw, getattr(self, "_away_turns", None) or [], _pl_aw(self.root))})
            except Exception:  # noqa: BLE001
                logger.debug("away lines skipped", exc_info=True)
            if _away_lines:
                _shown = _shown.rstrip("\n") + "\n\n" + "\n".join(_away_lines)
            if on_chunk is not None and _shown and _r_streamed:
                # the prose is already on screen: only what comes after it (the state line, the options)
                _tail = []
                try:
                    from neonrp.core.registry import load_registry as _lr_t

                    _st = _bd_r._state_line(_v3_out.get("apply"), _lr_t(self.root)) if _r_show else None
                    if _st:
                        _tail.append(_st)
                except Exception:  # noqa: BLE001
                    pass
                _tail += _away_lines
                _tail += [f"{i}. {o}" for i, o in enumerate(_v3_out.get("options") or [], 1)]
                if _tail:
                    on_chunk("\n" + "\n".join(_tail))
            elif on_chunk is not None and _shown:
                try:
                    on_chunk(_shown)
                except Exception:  # noqa: BLE001
                    logger.debug("v3 on_chunk failed", exc_info=True)
            _wa_result = ConversationTurnResult(
                success=True, run_id=run_id, assistant_message=_shown, assistant_speaker=self.agent_id,
                active_agent=self.agent_id, turns_used=1 + int(_v3_out["loops"]),
                tool_calls_made=[str(o.get("op")) for o in _v3_out["ops"]], usage=dict(_v3_out["usage"]),
                options=list(_v3_out.get("options") or []), panels=dict(_v3_out.get("panels") or {}),
            )
            _trace.apply = _v3_out["apply"].to_dict()
            if getattr(self, "_pl_resolve", None):  # the Resolve of a plan: report it, and the talk is consumed
                from neonrp.core import node_kinds as _nk_t

                _beat_t = _nk_t.call("plan", "finish", self._pl_resolve, self.root, _v3_out)
                if _beat_t:
                    _trace.apply["beat"] = _beat_t
                self._pl_resolve = None
            _trace.apply["options"] = list(_v3_out.get("options") or [])
            _trace.apply["panels"] = dict(_v3_out.get("panels") or {})
            _trace.apply["tool_returns"] = list(_v3_out.get("tool_returns") or [])  # [roll 1d6]-style requests the engine answered mid-turn
            if getattr(self, "_act_ctx", None):  # the player's structured action this beat carried on (its roll comes first)
                _trace.apply["tool_returns"] = list(self._act_ctx.get("tool_returns") or []) + _trace.apply["tool_returns"]
                _trace.apply["action"] = dict(self._act_ctx.get("action") or {})
                self._act_ctx = None
            _trace.apply["proposals"] = _v3_out.get("proposals") or []  # ③→④ intermediate outputs, every attempt
            _trace.apply["annotated"] = _v3_out.get("annotated") or ""  # prose + requests / answers / state changes in place
            _trace.apply["narration_plain"] = _narr
            try:  # the entities the prose names, with their spans (core/mentions.py, 10-14): the screen marks exactly these
                from neonrp.core import mentions as _mn
                from neonrp.core.registry import load_registry as _lr_mn

                _trace.apply["mentions"] = _mn.find(_lr_mn(self.root), _narr)
            except Exception:  # noqa: BLE001
                logger.debug("mentions skipped", exc_info=True)
            # the soul reports the solve saw (text + judgment) — the qualitative record
            _trace.apply["reports"] = [
                {k: v for k, v in r.items() if k in ("iid", "name", "kind", "text", "judgment", "proposed_move")}
                for r in _v3_out["reports"]
            ]
            try:  # a standalone character who answered the player: noted as talked (core/player_data, 10-15)
                from neonrp.core import player_data as _pd

                _pd.after_turn(self.root, _trace.apply["reports"])
            except Exception:  # noqa: BLE001 — the player's record never fails a turn
                logger.debug("player data skipped", exc_info=True)
            # soul closed-schema write-back, judged from the FINAL narration
            # mood / trust / important / intention + typed memo.
            try:
                from neonrp.core import mechanics as _mech

                _settle = _mech.get(self.root, "settle")
                _st0 = time.monotonic()
                from neonrp.core import system_one as _s1x

                if _s1x.fast_judge_available() or _s1x.backend_name() == "off":  # off answers instantly: inline, no thread
                    _settled = _settle(self.root, reports=_v3_out["reports"], narration=_narr, turn=turn_seq)
                    _trace.apply["souls"] = _settled
                    _v3_out["spans"].append({"phase": "settle", "actor": "souls", "backend": _settled[0]["source"] if _settled else "off",
                                             "t0": round((_st0 - _v3_t_base) * 1000, 1), "t1": round((time.monotonic() - _v3_t_base) * 1000, 1),
                                             "n": len(_settled)})
                else:
                    # 10-01: with an LLM judge this batch took 5–24 s; it only shapes the NEXT turn (mood / trust /
                    # memory), so it runs after the reply and the next send() waits for it before starting.
                    import threading as _thr

                    _rep, _nar, _ts = list(_v3_out["reports"]), _narr, turn_seq
                    self._deferred_settle = _thr.Thread(
                        target=lambda: _settle(self.root, reports=_rep, narration=_nar, turn=_ts),
                        name="neonrp-settle", daemon=False)
                    self._deferred_settle.start()
                    _trace.apply["souls"] = [{"deferred": True}]
                    _v3_out["spans"].append({"phase": "settle", "actor": "souls", "backend": "deferred",
                                             "t0": round((_st0 - _v3_t_base) * 1000, 1), "t1": round((time.monotonic() - _v3_t_base) * 1000, 1)})
            except Exception:  # noqa: BLE001 — memo is best-effort, never blocks the turn
                logger.debug("v3 soul settle skipped", exc_info=True)
            try:  # 10-02: the template's after-reply work (rpg map tool: place the places grown by default; [~move] is async)
                from neonrp.core import mechanics as _mech2

                _job0 = _mech2.get(self.root, "after_turn")(self.root, created=list(_v3_out["apply"].created), narration=_narr)
                # Each present soul gets this beat retold from where she stands (her next beat reads it)
                from neonrp.core import soul_view as _svw
                from neonrp.core.registry import load_registry as _lr_w
                from neonrp.core.sdk import strip_marks as _strip_w

                _reg_w = _lr_w(self.root)
                _present_w = [e.id for e in _reg_w.of_class("soul") if _reg_w.player_location and e.parent == _reg_w.player_location]
                _here_w = _reg_w.entries.get(_reg_w.player_location or "")
                _place_w = _here_w.name if _here_w is not None else ""
                _pname_w, _narr_w, _turn_w = _svw.player_name(_reg_w), _strip_w(_narr), turn_seq

                def _job() -> None:
                    if callable(_job0):
                        _job0()
                    _svw.write_views(self.root, narration=_narr_w, turn=_turn_w, iids=_present_w, place=_place_w, player=_pname_w)

                if callable(_job0) or _present_w:
                    import threading as _thr2

                    self._deferred_place = _thr2.Thread(target=_job, name="neonrp-after-turn", daemon=False)
                    self._deferred_place.start()
                    _trace.apply["after_turn"] = {"deferred": True}
            except Exception:  # noqa: BLE001
                logger.debug("after_turn skipped", exc_info=True)
            _trace.spans = list(_v3_out["spans"])
            _trace.timing["v3"] = {"loops": _v3_out["loops"], "pack_chars": _v3_out["pack_chars"],
                                   "usage": dict(_v3_out.get("usage") or {}),  # world-side tokens: Template Lint's per-turn budget
                                   "verify": {"accepted": len(_v3_out["verify"].get("accepted", [])),
                                              "refused": len(_v3_out["verify"].get("refused", []))}}
            for _o in _v3_out["ops"]:
                _trace.record_tool_call(f"op:{_o.get('op')}", {k: v for k, v in _o.items() if k != "op"})
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_s1_handled', '_v3_out', '_wa_result') if k in _out})


def render(self: Any, c: TurnCtx) -> None:
    """Each player-agent renders the world-truth; the narration published; the correction block pulled out of it (Pass A → B)."""
    from neonrp.core.conversation import _MISSING_BLOCK_REMINDER, _extract_corrections, _queue_location_judgment  # the old function's module globals
    _active_iids_for_trace = c._active_iids_for_trace
    _publish = c._publish
    _soul_corrections = c._soul_corrections
    _topics = c._topics
    _understanding = c._understanding
    _v3_out = c._v3_out
    player_agents = c.player_agents
    result = c.result
    turn_seq = c.turn_seq
    # M20 §3 step 6 — player-agent render. The world-agent produced
    # world-truth; each player-agent now owns its player's view + private
    # state (journal). v1 is a deterministic pass-through (world-agent
    # still authors prose ⇒ N=1 narration byte-identical, no regression);
    # the per-player perspective render is the C3 seam inside render().
    # Distinct + logged even at N=1 (M20: never inlined).
    # M18 §1/§6 — each player-agent is a bus node: it renders the
    # world-truth into its own PlayerOutputDirective stream and publishes it
    # to player/<pid>/output. Frontends subscribe to that topic and render
    # the directives — the engine no longer owns rendering. v1 is a
    # deterministic typewriter text directive (byte-identical narration at
    # N=1); the per-player perspective render is the C3 seam.
    for _pa in player_agents:
        _pa.render(result.assistant_message or "")
        for _directive in _pa.to_directives(result.assistant_message or ""):
            _publish(_topics.player_output(_pa.pid), _directive.to_dict())

    # M18 §1/§2.2 — the world-agent is a bus node: it publishes its raw
    # NarrativeMaterial to world/narration, tagged with the producing
    # world_agent_id. There is one world-agent today; when location /
    # character world-agents join the bus (the multi-world roadmap) they
    # publish the SAME topic with their own id — no pipeline rewrite.
    _narration_text = result.assistant_message or ""
    # Pass A→B bridge: pull the world-agent's OPTIONAL corrections block out
    # of the narration into `_soul_corrections`, then STRIP it so the
    # control block never reaches the player. Tolerant — a malformed block
    # is discarded but still stripped (nothing leaks), and the published /
    # persisted narration below is already clean.
    if "⟦CORRECTIONS⟧" not in _narration_text and _v3_out is None:
        # The settling duty was missed (a procedural check): no block = this turn's positions were not settled.
        # Queue a location-judgment note; next turn's preflight insists the settling is made up.
        _queue_location_judgment(self.root, _MISSING_BLOCK_REMINDER)
    _extracted_corrections, _narration_text = _extract_corrections(
        _narration_text, set(_active_iids_for_trace)
    )
    if _extracted_corrections:
        _soul_corrections.update(_extracted_corrections)
        # Surface the two-pass correction on the bus so it lands in the
        # turn trace (bus_messages) → the web-ui orchestration debug view
        # can SHOW the world-agent overriding a soul's proposed move.
        # Observability only — no subscriber acts on it (Pass B applies).
        _publish(
            "world/corrections",
            {
                "turn_seq": turn_seq,
                "world_agent_id": self.agent_id,
                "corrections": {
                    k: v.get("moved_to", "")
                    for k, v in _soul_corrections.items()
                },
            },
        )
    _publish(
        _topics.WORLD_NARRATION,
        {
            "turn_seq": turn_seq,
            "world_agent_id": self.agent_id,
            "speaker": getattr(result, "assistant_speaker", None) or self.agent_id,
            # M22: narration is location-scoped — this is the PLAYER
            # scene's narration; loc world-agents publish the same topic
            # with their own location (perspective feeds select by it).
            "location": _understanding.player_node,
            # NarrativeMaterial, capped so the recorded trace stays bounded.
            "text": _narration_text[:4000],
            "narration_chars": len(_narration_text),
        },
    )
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_narration_text',) if k in _out})


def corrections_land(self: Any, c: TurnCtx) -> None:
    """V2b's transitional settling: the corrections the model still writes land through the judges; the player's own landing."""
    from neonrp.core.conversation import _apply_player_move, _apply_soul_move, _judge_world_agent_move  # the old function's module globals
    _soul_corrections = c._soul_corrections
    _soul_name = c._soul_name
    playthrough = c.playthrough
    souls_root = c.souls_root
    # ── V2b transitional settling: when the model still writes ⟦CORRECTIONS⟧, land it as written (judged).
    # Under roll-call the souls do not pre-run, so there is no Pass A / pending; the new path is the world-agent
    # calling move_entity directly (the same judge inside the tool). The two are exclusive, never doubled: the
    # block only appears when the model did not use the tool.
    _by_iid = {s.instance_id: s for s in playthrough.souls}
    for _ciid, _corr in _soul_corrections.items():
        if _ciid == "player" or "moved_to" not in _corr:
            continue
        _cs = _by_iid.get(_ciid)
        if _cs is None:
            continue
        _cdir = souls_root / f"{_cs.sid}-{_cs.instance_id}"
        _cmove = _corr["moved_to"]
        if _cmove:
            _cmove = _judge_world_agent_move(
                self.root,
                _cdir,
                instance_id=_ciid,
                display_name=_soul_name(_cdir, _cs.sid),
                move=_cmove,
            )
        if _cmove and _apply_soul_move(
            _cdir, _cmove, root=self.root, allow_cross_town=True
        ):
            logger.info(
                "soul %s moved_to=%r (world-corrected, transitional block)",
                _ciid,
                _cmove,
            )

    # Player landing — the souls' adjudicated path, extended to the player
    # (P0, docs/POSITION-GROUND-TRUTH.md): the world-agent's "player"
    # correction is judged by the map, then written to game/meta/
    # run_state.json. Closes the "narration moved the player but state
    # never followed" desync — next turn's scene_understanding reads the
    # updated node, so presence/grouping stays consistent with the story.
    _pcorr = _soul_corrections.get("player")
    if _pcorr and _pcorr.get("moved_to"):
        if _apply_player_move(self.root, _pcorr["moved_to"]):
            logger.info(
                "player moved_to=%r (world-adjudicated, map-validated)",
                _pcorr["moved_to"],
            )


def soul_deltas(self: Any, c: TurnCtx) -> None:
    """V2b: the named souls' deltas · the observation face · a heartbeat for those present and an off-stage memo for those away."""
    from neonrp.core.conversation import _trace_judgment  # the old function's module globals
    CharacterDelta = c.CharacterDelta
    SoulTraceEntry = c.SoulTraceEntry
    _active_iids_for_trace = c._active_iids_for_trace
    _bus = c._bus
    _emit_status = c._emit_status
    _hash_soul_folder = c._hash_soul_folder
    _narration_text = c._narration_text
    _publish = c._publish
    _s1_handled = c._s1_handled
    _s1_hb_lines = c._s1_hb_lines
    _s1_mode = c._s1_mode
    _s1_plan = c._s1_plan
    _soul_name = c._soul_name
    _topics = c._topics
    _trace = c._trace
    _understanding = c._understanding
    append_turn_trace = c.append_turn_trace
    deltas = c.deltas
    drain_turn_engagements = c.drain_turn_engagements
    playthrough = c.playthrough
    result = c.result
    scene = c.scene
    soul_status = c.soul_status
    souls_root = c.souls_root
    user_text = c.user_text
    # ── V2b: the named souls' deltas land + the observation face is re-sent + an off-stage memo for the unnamed souls ──
    _engagements = drain_turn_engagements()
    _engaged_iids = {e["instance_id"] for e in _engagements}
    for _e in _engagements:
        deltas.append(
            CharacterDelta(
                sid=_e["sid"],
                instance_id=_e["instance_id"],
                version_hash=_e["version_hash"],
                state=_e["state"] or "completed",
                soul_folder_hash=_e["after_hash"],
            )
        )
        _publish(
            _topics.soul_response(_e["instance_id"]),
            {
                "sid": _e["sid"],
                "instance_id": _e["instance_id"],
                "state": _e["state"],
                "structured": True,
                "folder_changed": _e["before_hash"] != _e["after_hash"],
                "tool_calls": 0,
                "role": _e["role"],
                "feeds_world": True,
                "digest": _e["digest"],
                "inner_voice": _e["inner_voice"],
                "confidence": _e["confidence"],
                "urgency": _e["urgency"],
                "memory_delta": _e["memory_delta"],
            },
        )
        if _e["instance_id"] in soul_status:
            soul_status[_e["instance_id"]]["state"] = _e["state"] or "completed"
    _emit_status()

    # Unnamed souls: those **present** get one light heartbeat (M30 lifecycle; floor: cap HEARTBEAT_CAP, a
    # failure falls back to the memo); those away get a zero-LLM off-stage memo — memory stays continuous and
    # the delta still commits.
    from neonrp.core.engage import HEARTBEAT_CAP, heartbeat_soul_run

    _away_iids = {i for i, _n in getattr(_understanding, "away_roster", ())}
    _hb_enabled = os.environ.get("NEONRP_HEARTBEAT", "1") != "0"
    _hb_done = 0
    _narr_tail = (_narration_text or "")[-400:]
    for soul in playthrough.souls:
        if soul.instance_id in _engaged_iids:
            continue
        soul_dir = souls_root / f"{soul.sid}-{soul.instance_id}"
        rel = soul_dir / "short-term-memo" / "recent_events.json"
        _hb_line = ""
        if _s1_mode == "1" and _s1_plan is not None:
            # S2 already ran the gestures in parallel (and speak souls
            # talked); never a serial heartbeat call on this path.
            _hb = (
                {"ok": True, "line": _s1_hb_lines[soul.instance_id]}
                if _s1_hb_lines.get(soul.instance_id)
                else {"ok": False}
            )
        elif (
            _hb_enabled
            and soul.instance_id not in _away_iids
            and _hb_done < HEARTBEAT_CAP
        ):
            _hb = heartbeat_soul_run(self.root, soul, _narr_tail)
        else:
            _hb = {"ok": False}
        if True:
            if _hb.get("ok"):
                _hb_done += 1
                _hb_line = str(_hb["line"])
                _publish(
                    _topics.soul_response(soul.instance_id),
                    {
                        "sid": soul.sid,
                        "instance_id": soul.instance_id,
                        "state": "heartbeat",
                        "structured": False,
                        "folder_changed": True,
                        "tool_calls": 0,
                        "role": str(getattr(soul, "role", "") or "npc"),
                        "feeds_world": False,
                        "digest": _hb_line,
                        "inner_voice": "",
                        "confidence": 0.0,
                        "urgency": 0.0,
                        "memory_delta": "",
                    },
                )
                from neonrp.core.notes import post_note as _post_note

                _post_note(
                    self.root,
                    "heartbeat",
                    f"[{_soul_name(soul_dir, soul.sid)}] {_hb_line}",
                    sender=soul.instance_id,
                )
        try:
            doc = json.loads(rel.read_text(encoding="utf-8"))
            events = doc.get("events")
            if not isinstance(events, list):
                events = []
            _ev = {
                "kind": (
                    "heartbeat"
                    if _hb_line
                    else ("spoke" if _s1_handled.get(soul.instance_id, {}).get("kind") == "speak" else "off-stage")
                ),
                "scene": scene,
                "player_action": user_text[:160],
            }
            if _hb_line:
                _ev["my_reaction"] = _hb_line
            events.append(_ev)
            doc["events"] = events
            rel.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (OSError, ValueError):
            # A failed memo read/write loses only this memory, never the delta: the manifest needs a delta for
            # every soul every turn, otherwise compose's version_hash takes the fallback and no longer shares
            # its source with land (hash-first hypothesis ③), and a save missing a memo file could not land
            # from its very first turn.
            logger.debug(
                "off-stage memo skip for %s (no/invalid file)",
                soul.instance_id,
            )
        deltas.append(
            CharacterDelta(
                sid=soul.sid,
                instance_id=soul.instance_id,
                version_hash=soul.version_hash,
                state="completed",
                soul_folder_hash=_hash_soul_folder(soul_dir),
            )
        )
        if soul.instance_id in soul_status:
            soul_status[soul.instance_id]["state"] = "background"
    _emit_status()

    def _write_orchestration_trace(commit_id: str | None, landed_ok: bool | None) -> None:
        # Finalize + append the M18 §7 trace. Soul entries are derived
        # from the collected deltas (sid / instance_id / state); a soul
        # in active_souls is `activated`, an off-stage soul is not.
        try:
            _trace.world_commit_id = commit_id
            _trace.landed_ok = landed_ok
            _trace.narration_chars = len(getattr(result, "assistant_message", "") or "")
            for _d in deltas:
                _act = _d.instance_id in _active_iids_for_trace
                _h = _s1_handled.get(_d.instance_id) or {}
                _trace.souls.append(
                    SoulTraceEntry(
                        sid=_d.sid,
                        instance_id=_d.instance_id,
                        activated=_act,
                        reason=_understanding.reasons.get(
                            _d.instance_id,
                            "in active_souls" if _act else "off-stage",
                        ),
                        state=getattr(_d, "state", None),
                        speech=str(_h.get("text") or "")[:600],
                        judgment=_trace_judgment(_h.get("judgment"), (getattr(self, "_companions_judged", None) or {}).get(_d.instance_id)),
                    )
                )
            _publish(
                _topics.ENGINE_EVENT,
                {
                    "kind": "turn_committed",
                    "turn_seq": _trace.turn_seq,
                    "commit_id": commit_id,
                    "ok": landed_ok,
                },
            )
            # M18 §1/§2.2 — the world-agent node announces the turn's
            # world-state transition on world/state (commit + active set +
            # location), tagged with the producing world_agent_id. This is
            # the state-change event other nodes (player-agents, and future
            # location/character world-agents) subscribe to.
            _publish(
                _topics.WORLD_STATE,
                {
                    "turn_seq": _trace.turn_seq,
                    "world_agent_id": self.agent_id,
                    "world_location": _trace.world_location,
                    "active_souls": sorted(_active_iids_for_trace),
                    "commit_id": commit_id,
                    "landed_ok": landed_ok,
                },
            )
            # The recorded message stream IS the turn routed through the
            # broker — captured into the trace record (M18 §7 / §3).
            _trace.bus_messages = [m.to_dict() for m in _bus.drain_log()]
            from neonrp.core import beat_budget as _bb_t

            if _bb_t.hits():  # which beats ran out of time (core/beat_budget)
                _trace.timing["timeouts"] = _bb_t.hits()
            if _bb_t.calls():  # each model call of the turn: its beat, ms to the first chunk, ms in all (10-19)
                _trace.timing["llm_calls"] = _bb_t.calls()
            append_turn_trace(self.root, self.branch, _trace)
            self._emit_beats(_trace)
            # V0 player-facing artifacts (DESIGN-VISIONRP §2) — mirror the
            # landed turn into story.md / feed / tree.json for any file
            # client (Obsidian, visionRP shell, Claude Code).
            from neonrp.core.player_artifacts import append_turn_artifacts

            append_turn_artifacts(
                self.root,
                self.branch,
                turn_seq=_trace.turn_seq,
                player_input=user_text or "",
                narration=_narration_text,
                speaker=str(
                    getattr(result, "assistant_speaker", None) or self.agent_id
                ),
            )
        except Exception:  # noqa: BLE001 — trace must never break a turn
            logger.debug("orchestration trace finalize skipped", exc_info=True)
    _out = locals()
    c.__dict__.update({k: _out[k] for k in ('_write_orchestration_trace',) if k in _out})


def land(self: Any, c: TurnCtx) -> None:
    """The turn counter, the world commit (land_turn) and the trace — the turn's result."""
    from neonrp.core.conversation import _bump_turn_count  # the old function's module globals
    _ma_t_start = c._ma_t_start
    _trace = c._trace
    _v3 = c._v3
    _write_orchestration_trace = c._write_orchestration_trace
    deltas = c.deltas
    result = c.result
    scene_packet = c.scene_packet
    turn_seq = c.turn_seq
    world_agent = c.world_agent
    # Pure-code turn counter: advance run_state.json turn_count BEFORE the
    # land so the bump is part of this turn's world commit. The next
    # turn's scene/turn_seq then reflects reality even when the
    # world-agent forgot to write run_state itself.
    _bump_turn_count(self.root, scene_packet.turn_count)

    try:
        # asyncio.run: minimal sync->async bridge. land_turn owns the
        # §3.4 step 4-7 hash-first compose + committed land_commit IO
        # over the folder-hash-derived deltas (same M17 landing).
        import asyncio

        _land_t0 = time.monotonic()
        world_commit_id = asyncio.run(
            world_agent.land_turn(
                deltas, turn_seq=turn_seq, branch=self.branch
            )
        )
        if _v3:
            _trace.spans.append({"phase": "land", "actor": "engine", "backend": "python",
                                 "t0": round((_land_t0 - _ma_t_start) * 1000, 1), "t1": round((time.monotonic() - _ma_t_start) * 1000, 1)})
    except Exception as exc:
        # A land failure must not lose the narration the player already
        # saw. land_turn is hash-first: on failure nothing is appended
        # to the ref, so the working tree stays consistent. Report the
        # error on the otherwise-successful turn rather than crashing.
        logger.warning("multi-agent land_turn failed: %s", exc, exc_info=True)
        result.error = f"multi-agent commit failed: {exc}"
        result.success = False
        _write_orchestration_trace(None, False)
        c._ret = result
        return

    # The landed world commit id is the canonical turn identity;
    # surface it on the route_decision so the TUI/telemetry can see a
    # multi-agent turn closed (no schema change to ConversationTurnResult).
    result.route_decision = f"multi_agent_commit:{world_commit_id}"
    _write_orchestration_trace(world_commit_id, True)
    c._ret = result
    return
