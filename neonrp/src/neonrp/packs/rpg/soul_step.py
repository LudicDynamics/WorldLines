"""S-judge soul step (ENGINE-V3-MASTER-PLAN §2, variant S-judge).

A soul's turn is *judge + speak*: the closed-schema judgment (attitude,
register, urgency, want_move / move_to, needs_free_action) is answered by the
judge (Jev, or its fallbacks), then **one** LLM call writes 1–3 sentences with
the judgment baked in — the model no longer decides, it voices. ``gesture``
costs no LLM at all (a small register table). ``needs_free_action`` above the
escalation threshold falls back to today's agent loop (rare path).

The judged ``move_to`` is returned as a proposal; ``turn_v3.solve_turn`` runs
it through the same verify (judge_move) as world ops, so a soul's move is a
proposal like any other, never a direct write.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from neonrp.core import engine_config
from neonrp.core import system_one as s1
from neonrp.core.registry import Registry, load_registry

logger = logging.getLogger(__name__)

def _S(lang: str | None) -> dict[str, Any]:
    """This module's strings (src/neonrp/prompts/soul_step.<lang>.json)."""
    from neonrp import prompts

    return prompts.strings("soul_step", lang or "zh")


def _f(s: str, /, **kw: Any) -> str:
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


# the codes (keys) are the protocol; the zh labels stay as the module's constants for old importers
ATTITUDES: dict[str, str] = _S("zh")["ATTITUDES"]
REGISTERS: dict[str, str] = _S("zh")["REGISTERS"]
URGENCY: dict[str, str] = _S("zh")["URGENCY"]
_GESTURES: dict[str, str] = _S("zh")["GESTURES"]


@dataclass
class SoulJudgment:
    iid: str
    name: str
    attitude: str | None
    register: str | None
    urgency: int
    want_move: bool
    move_to: str | None
    needs_free_action: float
    source: str
    confidence: float
    ms: float
    decision: dict[str, Any] | None = None  # persuasion adjudication (公开的思考链)
    answers: dict[str, Any] | None = None  # every judge answer, value + confidence (中间过程)
    confides: float = 0.0  # E7 A5: the player is opening up / showing weakness — meet it before business
    follow: float = 0.0  # E1 v3-split T4: the player walked on to the inn, she stayed on main street — would she follow?
    stay: float = 0.0  # E5 C3a: 「你在这里等我」— Jev read follow .64 anyway; an explicit "told to stay" question gates it
    thought: str | None = None  # 10-15: one line of what she is thinking (S-direct's optional `thought:`) — the screen's 「心思」

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def baked(self, lang: str = "zh") -> str:
        """The judgment as a prompt line for the speech call — outcome, not mechanics
        (「给结局不给措辞」). The dice / thresholds stay in the trace; the line only learns what she
        decided, roughly how she feels, and whether the player is confiding."""
        S = _S(lang)
        parts = []
        d = self.decision
        if d and d.get("stakes") in ("light", "heavy"):
            parts.append(_f(S["baked_decision"], d=S["d_comply"] if d['outcome'] == 'comply' else (S["d_partial"] if d['outcome'] == 'partial' else S["d_refuse"])))
        hints = []
        if self.attitude:
            hints.append(S["ATTITUDES"].get(self.attitude, self.attitude))
        if self.register:
            hints.append(_f(S["tone"], r=S["REGISTERS"].get(self.register, self.register)))
        if self.urgency >= 2:
            hints.append(S["URGENCY"].get(str(self.urgency), str(self.urgency)))
        if hints:
            parts.append(S["roughly"] + S["hint_sep"].join(hints))
        if self.want_move and self.move_to:
            parts.append(_f(S["leaving"], to=self.move_to))
        if self.confides >= 0.6:
            parts.append(S["confides"])
        return S["baked_sep"].join(parts)


STAKES: dict[str, str] = _S("zh")["STAKES"]



# The souls play like the player — both get the world agent's view and act on it. The soul is not the
# player's answering machine: words are not always meant for her, she owns only her own things, knows only what she met.
ACT_RULE = _S("zh")["act_rule"]  # the zh original; prompts use act_rule(lang)


def act_rule(lang: str) -> str:
    return _S(lang)["act_rule"]


def _beat_of(situation: str) -> dict[str, str] | None:
    """Her own beat (the soul_view narration) — the soul call then speaks to her as a player, and remembers the event."""
    from neonrp.core.soul_view import has_own, split_beat

    if not has_own(situation):
        return None
    _scene, seen = split_beat(situation)
    return {"event": seen}


def _idle(line: str) -> bool:
    """「—」 (or nothing but dashes / dots): she does nothing this beat."""
    return not line.strip().strip("「」").strip("—-–.。… ")

def questions_for(name: str, exits: dict[str, str], lang: str = "zh") -> dict[str, s1.Q]:
    S = _S(lang)
    qs: dict[str, s1.Q] = {
        # E6 run1: a single "分量" choice misfiled light asks as none and an apology as heavy —
        # two plain yes/no questions classify better than one three-way label.
        "asked": s1.noul(_f(S["q_asked"], name=name)),
        "costly": s1.noul(_f(S["q_costly"], name=name)),
        "why_costly": s1.choice(S["q_why"], dict(S["WHY_CHOICE"])),
        "willingness": s1.noul(_f(S["q_willingness"], name=name)),
        "attitude": s1.choice(_f(S["q_attitude"], name=name), dict(S["ATTITUDES"])),
        "register": s1.choice(_f(S["q_register"], name=name), dict(S["REGISTERS"])),
        "urgency": s1.choice(_f(S["q_urgency"], name=name), dict(S["URGENCY"])),
        "confides": s1.noul(_f(S["q_confides"], name=name)),
        "follow": s1.noul(_f(S["q_follow"], name=name)),
        "stay": s1.noul(_f(S["q_stay"], name=name)),
        "want_move": s1.noul(_f(S["q_want_move"], name=name)),
        "free": s1.noul(_f(S["q_free"], name=name)),
    }
    if len(exits) >= 2:
        qs["move_to"] = s1.choice(_f(S["q_move_to"], name=name), {k: v for k, v in list(exits.items())[:8]})
    elif len(exits) == 1:
        qs["move_to"] = s1.choice(_f(S["q_move_to"], name=name), {**{k: v for k, v in exits.items()}, "stay": S["stay_here"]})
    return qs


def judge_soul(root: Path, iid: str, *, situation: str, exits: dict[str, str] | None = None,
               registry: Registry | None = None, ask: Any = None, turn: int | None = None,
               reaction: str | None = None, adjudicate_dice: bool = True) -> SoulJudgment:
    reg = registry or load_registry(root)
    env = reg.entries.get(iid)
    name = env.name if env else iid
    if turn is None:
        tv = reg.variables.get("turn")
        turn = int(tv.value or 0) if tv and isinstance(tv.value, (int, float)) else 0
    if exits is None:
        exits = {e.id: e.name for e in reg.exits(env.parent)} if env and env.parent else {}
    # E6 run2: with the player's line buried at the end of a 1.5k situation, Jev under-read it
    # (asked ≈ .08 for a plain request). Put it first and on its own; keep the scene short.
    from neonrp.core.soul_view import has_own, split_beat

    if has_own(situation):  # 10-02: the world's prose for her — the player's beat is its last paragraph
        scene, player_says = split_beat(situation)
        _sep = "beat"
    else:
        scene, _sep, player_says = situation.partition("玩家这一拍:") if "玩家这一拍:" in situation else situation.partition("玩家此刻:")
    if not _sep:
        scene, player_says = situation, ""
    state = {
        "player_says": player_says.strip()[:900] or situation[-400:],  # the attempt + what the world says about it (P0 understanding)
        "soul": name, "mood": (env.props.get("mood") if env else None), "persona": str(env.props.get("persona") or "")[:600] if env else "",
        "rules": str(env.props.get("rules") or "")[:400] if env else "", "goals": (env.props.get("goals") if env else None),
        "recent": (env.props.get("recent") if env else None), "scene": scene.strip()[:800], "exits": exits,
        **({"her_reaction": reaction[:600]} if reaction else {}),  # S-free: Jev reads the closed schema off what she said
    }
    t0 = time.monotonic()
    answers = None
    for attempt in range(2):  # E6 adv1 N1 / adv4 N4: the chain came back empty once per few dozen calls — ask once more
        try:
            answers = (ask or s1.ask)(state, questions_for(name, exits, _plang(root)))
        except Exception:  # noqa: BLE001
            logger.debug("judge_soul ask failed (attempt %d)", attempt + 1, exc_info=True)
            answers = None
        if answers:
            break
    src = s1.backend_name() if answers else "off"
    j = SoulJudgment(iid, name, None, None, 0, False, None, 0.0, src, 0.0, 0.0)
    if answers:
        j.answers = {k: {"v": (round(a.value, 3) if isinstance(a.value, float) else a.value), "c": round(float(a.confidence), 3)} for k, a in answers.items()}
        a = answers.get("attitude")
        if a is not None and s1.confidence_ok(a) and str(a.value) in ATTITUDES:
            j.attitude, j.confidence = str(a.value), float(a.confidence)
        a = answers.get("register")
        if a is not None and s1.confidence_ok(a) and str(a.value) in REGISTERS:
            j.register = str(a.value)
        a = answers.get("urgency")
        if a is not None and str(a.value) in URGENCY:
            j.urgency = int(str(a.value))
        a = answers.get("confides")
        if a is not None:
            j.confides = round(a.yes, 3)  # value, not gated: final1 09-27 the .7 gate zeroed it and A5 empathy fell to .11–.38
        a = answers.get("stay")
        if a is not None:
            j.stay = round(a.yes, 3)
        a = answers.get("follow")
        if a is not None:
            # Jev's noul confidences sit around .5–.65 (E0); the .7 gate would zero this every time
            # (speed 09-27: follow .79 / .81 with conf .58 / .62). The value is the read; the
            # threshold (turn_v3.FOLLOW_AT) is where the decision lives.
            j.follow = round(a.yes, 3)
        a = answers.get("want_move")
        if a is not None:
            # Q10 (09-27) tried value-only: E5 final1 C2c she wandered to main street on want_move .64 / conf .28
            # while the player went to the guild → reverted per the rule (乱走就 revert). Her own move needs a
            # confident read AND no intention to follow the player this turn.
            j.want_move = a.yes >= 0.6 and s1.confidence_ok(a) and j.follow < 0.5
        a = answers.get("move_to")
        if j.want_move and a is not None and str(a.value) in exits:
            j.move_to = str(a.value)
        else:
            j.want_move = False
        a = answers.get("free")
        if a is not None:
            j.needs_free_action = float(a.yes)
        if int(engine_config.get(root, "turn.parallel.souls.adjudicate", 1)):
            j.decision = adjudicate(answers, trust=(env.props.get("trust") if env else None), seed=f"{_seed_salt(root)}:{iid}:{turn}:{situation[:80]}",
                                    heavy_at=float(engine_config.get(root, "turn.parallel.souls.heavy_at", 0.4)), dice=adjudicate_dice)
            if reaction is not None and j.decision is not None:
                j.decision["post_hoc"] = True  # read off her words after the fact: no dice, cannot change what she said
        else:
            j.decision = None  # ablation: judgment chain without the persuasion verdict
    j.ms = round((time.monotonic() - t0) * 1000, 1)
    return j


def judge_follow(root: Path, reg: Registry, iid: str, said: str, *, ask: Any = None) -> dict[str, float] | None:
    """Does she walk with the player? Only the two questions the companions rule reads, over what was said
    (a Resolve after a talk: she took no turn of her own, so there is no judgment yet — PL12 watch4 10-17:
    the player said they would go together and went alone). ``None`` when the judge does not answer."""
    env = reg.entries.get(iid)
    name = env.name if env else iid
    S = _S(_plang(root))
    state = {"player_says": said.strip()[-1500:], "soul": name,
             "persona": str(env.props.get("persona") or "")[:600] if env else "",
             "goals": (env.props.get("goals") if env else None)}
    qs = {"follow": s1.noul(_f(S["q_follow"], name=name)), "stay": s1.noul(_f(S["q_stay"], name=name))}
    try:
        a = (ask or s1.ask)(state, qs)
    except Exception:  # noqa: BLE001
        logger.debug("judge_follow ask failed", exc_info=True)
        a = None
    if not a or "follow" not in a:
        return None
    return {"follow": round(a["follow"].yes, 3), "stay": round(a["stay"].yes, 3) if "stay" in a else 0.0}


def _plang(root: Path) -> str:
    from neonrp.core.output_lang import prompt_lang

    return prompt_lang(root)


def _lang(root: Path) -> str:
    """The run's language for the soul's line (adversarial2 H1: an English player line turned her English), said in
    the prompt's own language (10-05: the prompt follows the run's language too)."""
    from neonrp.core.adv import lang_rule

    return lang_rule(root, _plang(root), soul=True)


def _seed_salt(root: Path) -> str:
    """Per-playthrough salt for the dice (written once): a replay of the same
    playthrough reproduces its rolls, two playthroughs of the same world do not
    share luck. Lives with the run, not with the template."""
    import json
    import secrets

    from neonrp.core.paths import get_data_dir_name

    p = root / get_data_dir_name(root) / "meta" / "engine_seed.json"
    try:
        return str(json.loads(p.read_text(encoding="utf-8"))["salt"])
    except (OSError, ValueError, KeyError, TypeError):
        salt = secrets.token_hex(8)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"salt": salt, "note": "dice seed for this playthrough"}) + "\n", encoding="utf-8")
        except OSError:
            pass
        return salt


WHY = _S("zh")["WHY"]


def adjudicate(answers: dict[str, s1.Answer], *, trust: Any = None, seed: str = "", dice: bool = True,
               light_threshold: float = 0.5, heavy_at: float = 0.4) -> dict[str, Any]:
    """玩家与角色之间的裁决.

    * ``none``  — nothing was asked; no decision.
    * ``light`` — the soul's own judgment: willingness (Jev probability, trust-shifted) against a threshold.
    * ``heavy`` — a dice roll (percentile roll-under d100, target = willingness×100 + trust×3), seeded per
      turn so a replay reproduces it, random across turns. ``partial`` on a hard success / near miss.

    The whole chain (stakes, willingness, trust, target, roll, tier, outcome) is returned so it can be
    logged and shown — the visible "thinking".
    """
    asked = answers.get("asked")
    costly = answers.get("costly")
    st = answers.get("stakes")  # legacy three-way label, still accepted
    why = answers.get("why_costly")
    why_v = str(why.value) if why is not None and str(why.value) in WHY else None
    reasons: list[str] = []
    if asked is not None:
        p_asked, p_costly = float(asked.yes), (float(costly.yes) if costly is not None else 0.0)
        if p_asked < 0.5:
            stakes = "none"
            reasons.append(f"玩家没有在要求她做具体的事(asked {p_asked:.2f} < .5)→ 不裁决")
        elif p_costly >= heavy_at:
            stakes = "heavy"
            reasons.append(f"玩家在要求她(asked {p_asked:.2f});这件事有代价(costly {p_costly:.2f} ≥ {heavy_at}" + (f",{WHY[why_v]}" if why_v and why_v != "none" else "") + ")→ 重 → 掷骰")
        else:
            stakes = "light"
            reasons.append(f"玩家在要求她(asked {p_asked:.2f});代价小(costly {p_costly:.2f} < {heavy_at})→ 轻 → 她自己判")
    else:
        stakes = str(st.value) if st is not None and str(st.value) in STAKES else "none"
    w = answers.get("willingness")
    willingness = float(w.yes) if w is not None else 0.5
    t = int(trust or 0) if isinstance(trust, (int, float)) else 0
    d: dict[str, Any] = {"stakes": stakes, "willingness": round(willingness, 3), "trust": t,
                         "asked": (round(float(asked.yes), 2) if asked is not None else None),
                         "costly": (round(float(costly.yes), 2) if costly is not None else None),
                         "why": why_v, "reasons": reasons}
    if stakes == "none":
        d["outcome"] = None
        return d
    adj = min(0.98, max(0.02, willingness + 0.03 * t))
    reasons.append(f"意愿 {willingness:.2f}(按人设 / 目标 / 承诺 / 信任判)+ 信任 {t}×.03 = {adj:.2f}")
    if stakes == "light" or not dice:
        outcome = "comply" if adj >= light_threshold else ("partial" if adj >= light_threshold - 0.15 else "refuse")
        reasons.append(f"轻的不掷骰:{adj:.2f} {'≥' if adj >= light_threshold else '<'} 阈值 {light_threshold} → " + {"comply": "答应", "partial": "折中(差 .15 以内)", "refuse": "拒绝"}[outcome])
        d.update({"threshold": light_threshold, "adjusted": round(adj, 3), "roll": None, "outcome": outcome})
        return d
    import hashlib
    import random

    from neonrp.core.dice import roll_check

    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12], 16))
    target = int(round(adj * 100))
    r = roll_check("persuade", target, rng=rng, ruleset="brp")
    tier = str(getattr(r.outcome, "value", r.outcome))
    if tier in ("critical", "special", "success"):
        outcome = "comply" if tier != "success" or r.roll <= target - 10 else "partial"
    else:
        outcome = "refuse" if tier != "fail" or r.roll > target + 20 else "partial"
    reasons.append(f"重的掷骰(d100 低于目标为成功):目标 = {adj:.2f}×100 = {target};随机数按「本局盐 + 角色 + 回合」播种,同一局回放同一个数,不同局不同")
    reasons.append(f"骰 {r.roll} {'≤' if r.roll <= target else '>'} {target} → {tier};" + {"comply": "成功 → 答应", "partial": ("成功但只是勉强(差 10 以内)→ 折中" if r.roll <= target else "失败但差得不远(20 以内)→ 折中"), "refuse": "失败 → 拒绝"}[outcome])
    d.update({"target": target, "roll": r.roll, "tier": tier, "outcome": outcome})
    return d


VARIANTS = ("S-judge", "S-direct", "S-free")


def soul_step(root: Path, iid: str, *, situation: str, depth: str, provider: str | None = None,
              mode: str = "play", registry: Registry | None = None, variant: str = "S-judge") -> dict[str, Any]:
    """One soul turn under one of the three closed-schema variants (blueprint ② / E2):

    S-judge   Jev judges first (attitude · register · asked / costly / willingness …) → engine adjudicates
              (light threshold / heavy dice) → one LLM call writes only the line, verdict baked in.
    S-direct  one LLM call returns the line AND the closed fields as JSON (no Jev on the soul side);
              adjudication is read off its own numbers without dice (post hoc: it already spoke).
    S-free    one LLM call writes only her reaction; Jev then classifies the closed fields from the text
              (post hoc, no dice). The line is the freest; the judgment cannot steer it.
    Returns the shape the S2 block consumes: ``{"ok", "kind", "text", "name", "judgment", "proposed_move"}``."""
    if variant == "S-judge" and _judge_is_llm():
        # 10-01: with Jev out (backend llm / off, or its quota spent) the 13 judgment questions would cost an extra
        # ~5 s LLM call per soul; her one generation call writes the same fields instead (S-direct, follow / stay incl.)
        variant = "S-direct"
    if variant == "S-direct":
        return _soul_step_direct(root, iid, situation=situation, depth=depth, provider=provider, mode=mode, registry=registry)
    if variant == "S-free":
        return _soul_step_free(root, iid, situation=situation, depth=depth, provider=provider, mode=mode, registry=registry)
    cfg = engine_config.engine_config(root)
    thr = float(engine_config._get_path(cfg, "turn.parallel.souls.escalate_at", 0.8))
    max_turns = int(engine_config._get_path(cfg, "turn.parallel.souls.escalate_turns", 3))
    j = judge_soul(root, iid, situation=situation, registry=registry)
    base = {"ok": True, "iid": iid, "name": j.name, "judgment": j.to_dict(), "proposed_move": j.move_to}
    if depth == "act" and j.needs_free_action >= thr:
        from neonrp.core.engage import engage_soul_run

        r = engage_soul_run(root, iid, note=situation, provider=provider, mode=mode, max_turns=max_turns)
        return {**base, **r, "kind": "act", "text": str(r.get("digest") or ""), "escalated": True}
    if depth == "gesture" or (depth == "speak" and j.attitude == "withdraw" and j.urgency == 0):
        S = _S(_plang(root))
        line = S["GESTURES"].get(j.attitude or "", S["silent_line"])
        return {**base, "kind": "gesture", "text": f"{j.name}{line}", "line": line}
    from neonrp.core.light_chat import ask_soul_deliver

    # A reading the judge is unsure of never decides a big branch — she decides in her own words,
    # and the engine reads the outcome off what she said (E5 jbjev C2a: follow .43 @ conf .14, willingness .32 @ .36
    # → 「拒绝」 was baked in, and one near-coin-flip sent the rest of the run down another branch).
    unsure = _unsure_reads(root, j)
    if "willingness" in unsure and j.decision and j.decision.get("outcome"):
        j.decision = {**j.decision, "outcome": None, "deferred": "willingness unsure → her own words"}
    lg = _plang(root)
    S = _S(lg)
    q = (situation + _f(S["judged"], baked=j.baked(lg))
         + S["act_rule"] + S["no_explain"]
         + (S["keep_decision"] if (j.decision or {}).get("outcome") else "")
         + (S["decide_yourself"] if unsure else "")
         + _lang(root))
    r = ask_soul_deliver(root, iid, q, asker="world-agent", beat=_beat_of(situation))
    if not r.get("ok"):
        return {**base, **r, "kind": "speak", "text": ""}
    line = clean_line(str(r.get("answer") or ""))
    if _idle(line):  # she chose to do nothing this beat
        return {**base, "kind": "gesture", "text": "", "line": "", "idle": True}
    if unsure and line.strip():
        _read_her_words(root, j, line, situation=situation, unsure=unsure)
        base = {**base, "judgment": j.to_dict()}
    return {**base, "kind": "speak", "text": line, "answer": r.get("answer")}


def _judge_is_llm() -> bool:
    """True when no fast judge (Jev / proxy) will answer this turn: backend llm or off, or the Jev quota is spent."""
    return not s1.fast_judge_available()


def _unsure_reads(root: Path, j: "SoulJudgment") -> set[str]:
    """Which deciding reads (follow / willingness) the judge answered below ``turn.parallel.souls.decide_conf``."""
    thr = float(engine_config.get(root, "turn.parallel.souls.decide_conf", 0.5))
    out = set()
    for k in ("follow", "willingness"):
        a = (j.answers or {}).get(k)
        if a is not None and float(a.get("c") or 0.0) < thr:
            out.add(k)
    return out


def _read_her_words(root: Path, j: "SoulJudgment", line: str, *, situation: str, unsure: set[str]) -> None:
    """Post hoc, from what she actually said: did she agree, will she come along, was she told to stay.
    Same judge chain as everything else (Jev → LLM judge); no answer → nobody follows on a guess."""
    name = j.name
    S = _S(_plang(root))
    qs = {"follow": s1.noul(_f(S["p_follow"], name=name)),
          "stay": s1.noul(_f(S["p_stay"], name=name))}
    if "willingness" in unsure:
        qs["agreed"] = s1.noul(_f(S["p_agreed"], name=name))
    from neonrp.core.soul_view import has_own, split_beat

    if has_own(situation):
        _scene, said = split_beat(situation)
    else:
        _scene, _sep, said = situation.partition("玩家这一拍:") if "玩家这一拍:" in situation else situation.partition("玩家此刻:")
    try:
        a = s1.ask({"player_says": (said or situation)[-600:], "soul": name, "her_words": line[:600]}, qs) or {}
    except Exception:  # noqa: BLE001
        a = {}
    if "follow" in a:
        j.follow = round(a["follow"].yes, 3)
    elif "follow" in unsure:
        j.follow = 0.0
    if "stay" in a:
        j.stay = round(a["stay"].yes, 3)
    if j.decision is not None and "agreed" in a:
        j.decision = {**j.decision, "outcome": "comply" if a["agreed"].yes >= 0.5 else "refuse", "post_hoc": True}
    j.answers = {**(j.answers or {}), **{f"post.{k}": {"v": round(v.yes, 3), "c": round(float(v.confidence), 3)} for k, v in a.items()}}


# ── S-direct / S-free (E2 arms; same output shape as S-judge) ────────────────

_DIRECT_FIELDS = ("speech", "thought", "attitude", "register", "urgency", "want_move", "move_to", "free", "asked", "costly", "why_costly", "willingness", "confides", "follow", "stay")


def _loose_json(text: str) -> dict[str, Any] | None:
    import json as _json

    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):] if "{" in t else t
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = _json.loads(t[i:j + 1])
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


def _fields_block(text: str) -> dict[str, Any] | None:
    """<fields> name: value lines (the ADV-era shape of S-direct; JSON is the fallback)."""
    import re as _re

    m = _re.search(r"<fields\s*>(.*?)(?:</fields\s*>|$)", text or "", _re.DOTALL | _re.IGNORECASE)
    if not m:
        return None
    out: dict[str, Any] = {}
    for ln in m.group(1).splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            v = v.strip()
            out[k.strip()] = (v.lower() == "true") if v.lower() in ("true", "false") else (None if v.lower() == "null" else v)
    return out


def clean_line(text: str) -> str:
    from neonrp.core.soul_result import clean_line as _clean

    return _clean(text)


def _lines_block(text: str) -> str:
    import re as _re

    m = _re.search(r"<lines\s*>(.*?)(?:</lines\s*>|$)", text or "", _re.DOTALL | _re.IGNORECASE)
    return "\n".join(ln.strip() for ln in m.group(1).splitlines() if ln.strip()) if m else ""


def _num(v: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _escalate_or_gesture(root: Path, iid: str, j: "SoulJudgment", *, situation: str, depth: str, provider: str | None, mode: str) -> dict[str, Any] | None:
    cfg = engine_config.engine_config(root)
    thr = float(engine_config._get_path(cfg, "turn.parallel.souls.escalate_at", 0.8))
    max_turns = int(engine_config._get_path(cfg, "turn.parallel.souls.escalate_turns", 3))
    base = {"ok": True, "iid": iid, "name": j.name, "judgment": j.to_dict(), "proposed_move": j.move_to}
    if depth == "act" and j.needs_free_action >= thr:
        from neonrp.core.engage import engage_soul_run

        r = engage_soul_run(root, iid, note=situation, provider=provider, mode=mode, max_turns=max_turns)
        return {**base, **r, "kind": "act", "text": str(r.get("digest") or ""), "escalated": True}
    if depth == "gesture":
        S = _S(_plang(root))
        line = S["GESTURES"].get(j.attitude or "", S["silent_line"])
        return {**base, "kind": "gesture", "text": f"{j.name}{line}", "line": line}
    return None


def _soul_step_direct(root: Path, iid: str, *, situation: str, depth: str, provider: str | None, mode: str, registry: Registry | None) -> dict[str, Any]:
    from neonrp.core.light_chat import ask_soul_deliver

    reg = registry or load_registry(root)
    env = reg.entries.get(iid)
    name = env.name if env else iid
    exits = {e.id: e.name for e in reg.exits(env.parent)} if env and env.parent else {}
    j = SoulJudgment(iid, name, None, None, 0, False, None, 0.0, "llm-direct", 0.0, 0.0)
    if depth == "gesture":
        return _escalate_or_gesture(root, iid, j, situation=situation, depth=depth, provider=provider, mode=mode) or {"ok": True, "iid": iid, "name": name, "kind": "gesture", "text": f"{name}{_S(_plang(root))['silent_line']}", "judgment": j.to_dict(), "proposed_move": None}
    S = _S(_plang(root))
    q = (f"{situation}\n\n{S['act_rule']}"
         + _f(S["direct_fmt"], attitudes='|'.join(ATTITUDES), registers='|'.join(REGISTERS), exits='|'.join(exits) or 'null', why='|'.join(WHY))
         + _lang(root))
    t0 = time.monotonic()
    r = ask_soul_deliver(root, iid, q, asker="world-agent", beat=_beat_of(situation))
    raw = str(r.get("answer") or "") if r.get("ok") else ""
    d = _fields_block(raw) or _loose_json(raw) or {}
    speech = str(d.get("speech") or _lines_block(raw) or (raw if raw and not raw.strip().startswith(("{", "<")) else "")).strip()
    a = str(d.get("attitude") or "")
    j.attitude = a if a in ATTITUDES else None
    rg = str(d.get("register") or "")
    j.register = rg if rg in REGISTERS else None
    try:
        j.urgency = max(0, min(3, int(d.get("urgency", 0))))
    except (TypeError, ValueError):
        j.urgency = 0
    j.want_move = bool(d.get("want_move")) and str(d.get("move_to")) in exits
    j.move_to = str(d.get("move_to")) if j.want_move else None
    j.needs_free_action = _num(d.get("free"))
    j.confides = round(_num(d.get("confides")), 3)
    j.follow = round(_num(d.get("follow")), 3)  # 10-01: without these the no-judge path never moved a companion
    j.stay = round(_num(d.get("stay")), 3)
    th = str(d.get("thought") or "").strip().strip("「」\"")
    j.thought = th[:60] if th and th not in ("—", "-", "null") else None
    j.confidence = 1.0 if d else 0.0
    j.answers = {k: {"v": d.get(k), "c": 1.0} for k in _DIRECT_FIELDS if k in d}
    if d and int(engine_config.get(root, "turn.parallel.souls.adjudicate", 1)):
        why = str(d.get("why_costly") or "none")
        ans = {"asked": s1.Answer("noul", _num(d.get("asked")), {}, 1.0), "costly": s1.Answer("noul", _num(d.get("costly")), {}, 1.0),
               "willingness": s1.Answer("noul", _num(d.get("willingness")), {}, 1.0),
               "why_costly": s1.Answer("choice", why if why in WHY else "none", {}, 1.0)}
        j.decision = adjudicate(ans, trust=(env.props.get("trust") if env else None), seed="", dice=False,
                                heavy_at=float(engine_config.get(root, "turn.parallel.souls.heavy_at", 0.4)))
        j.decision["post_hoc"] = True
    j.ms = round((time.monotonic() - t0) * 1000, 1)
    esc = _escalate_or_gesture(root, iid, j, situation=situation, depth=depth, provider=provider, mode=mode)
    if esc is not None:
        return esc
    base = {"ok": True, "iid": iid, "name": name, "judgment": j.to_dict(), "proposed_move": j.move_to}
    if speech and _idle(speech):
        return {**base, "kind": "gesture", "text": "", "line": "", "idle": True}
    if not speech:
        return {**base, "kind": "speak", "text": "", "error": "S-direct: no speech in reply", "raw": raw[:300]}
    return {**base, "kind": "speak", "text": speech, "answer": speech, "raw": raw[:300] if not d else None}


def _soul_step_free(root: Path, iid: str, *, situation: str, depth: str, provider: str | None, mode: str, registry: Registry | None) -> dict[str, Any]:
    from neonrp.core.light_chat import ask_soul_deliver

    reg = registry or load_registry(root)
    env = reg.entries.get(iid)
    name = env.name if env else iid
    if depth == "gesture":
        j = judge_soul(root, iid, situation=situation, registry=reg)
        return _escalate_or_gesture(root, iid, j, situation=situation, depth=depth, provider=provider, mode=mode) or {"ok": True, "iid": iid, "name": name, "kind": "gesture", "text": f"{name}{_S(_plang(root))['silent_line']}", "judgment": j.to_dict(), "proposed_move": None}
    S = _S(_plang(root))
    q = f"{situation}\n\n{S['act_rule']}{S['no_explain']}" + _lang(root)
    r = ask_soul_deliver(root, iid, q, asker="world-agent", beat=_beat_of(situation))
    speech = clean_line(str(r.get("answer") or "")) if r.get("ok") else ""
    j = judge_soul(root, iid, situation=situation, registry=reg, reaction=speech or None, adjudicate_dice=False)
    j.source = f"{j.source}-after"
    esc = _escalate_or_gesture(root, iid, j, situation=situation, depth=depth, provider=provider, mode=mode)
    if esc is not None:
        return esc
    base = {"ok": True, "iid": iid, "name": name, "judgment": j.to_dict(), "proposed_move": j.move_to}
    if not speech:
        return {**base, "kind": "speak", "text": "", "error": str(r.get("error") or "S-free: empty reply")}
    return {**base, "kind": "speak", "text": speech, "answer": speech}
