"""The settlement's 「真相三问」 (PLATFORM-PLAY-RULES-1015 §5 §9, 10-15): a run of a sandbox mystery (沙盒跑团,
play contract ``mystery-trpg``) ends with three single-choice questions about its truth. All three right and the
author's chosen character comes home with this run's full memory; otherwise the floor is points (10-20: no more
「take one character home」 as the floor).

    GET  /api/v1/play/engine/settlement/quiz
    → {state: locked | open | answered | unavailable, lang, questions: [{id, q, options}], reward_soul: {iid, sid, name} | null,
       points: {settle, per_right, fallback}, result?: {...}}
    POST /api/v1/play/engine/settlement/quiz {answers: [i, i, i]}          (unavailable = no questions: {answers: []})
    → {score, total, all_right, right: [bool], answer: [i], gained: [{sid, name, memory, how}], delivered, fallback,
       no_questions, achievements: [...], rewards: [{id, kind: points, amount, status: pending}],
       platform: reported | own_key | local | free_zone | guest | none | off}   (what became of them on the account, 10-21)

- points, every run: ``settle + per_right × right``; and ``fallback`` on top when the reward character did not come home
  — not all right, a run with no questions, or three right but the character already home with full memory (one home
  *fresh* is upgraded to full memory = delivered). The amounts are data, never the engine's: the play contract's
  ``settlement.truth_quiz_points`` {settle, per_right, fallback}, a template's own (``template.json`` ``settlement.
  truth_quiz_points``, any of the three) over it; unsaid = 0 (lint ``truth_quiz.points`` warns). They are written as
  pending rewards (player_data.add_reward) — paying them out is the platform's

- **locked** until the run has settled (no question shows before the ending — the quiz is the truth itself)
- the questions: the plot's own ``truth_quiz.questions`` (the author's, ``q`` / ``options`` a string or ``{zh, en, ja,
  ko}``, ``answer`` the right index). A contract whose ``settlement.truth_quiz`` is ``required`` (``mystery-trpg``,
  10-16) **must** carry them: lint ``contract.truth_quiz`` / ``truth_quiz.*`` — 默认区 (reviewed) block, 自由区 warn
- the fallback, not the way (自由区 / an older template without them): three the engine writes once from the run's truth
  (the plot's ``reveal`` in the run's language, else ``game/lore/gm-truth.md``) through the run's own provider, kept in
  ``meta/truth_quiz.json``; a model that does not answer in shape leaves the quiz **unavailable** (the floor still stands)
- ``truth_quiz.reward_soul`` (a sid) — who comes home with full memory on three right; default the companion walking
  with the player at the ending (else the run's companion)
- answering is once (``meta/truth_quiz_result.json``); answering again returns the first result
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

N = 3
POINTS = ("settle", "per_right", "fallback")  # the amounts: settlement.truth_quiz_points (contract < template), see points()
CONTRACTS = ("mystery-trpg",)  # runs built before the contract said ``settlement.truth_quiz`` (their copy lacks it)
_CACHE = "truth_quiz.json"
_RESULT = "truth_quiz_result.json"


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta"


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _w(p: Path, d: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or v.get("zh") or next(iter(v.values()), ""))
    return str(v or "")


def _plots(root: Path) -> list[dict[str, Any]]:
    """The run's plots; the one whose ending the run reached first (a creator's plot added over a template carries its
    own truth and its own three questions — the creation desk, PLATFORM-PLAY-RULES §11)."""
    out = []
    for info in (_j(_meta(root) / "plots.json", {}) or {}).values():
        pdef = _j(Path(root) / str((info or {}).get("dir") or "") / "plot.json", {}) or {}
        if pdef:
            out.append(pdef)
    eid = str((_j(_meta(root) / "ending.json", {}) or {}).get("id") or "")
    return sorted(out, key=lambda p: not (eid and isinstance(p.get("endings"), dict) and eid in p["endings"]))


def _amounts(*layers: Any) -> dict[str, int]:
    out = {k: 0 for k in POINTS}
    for d in layers:
        d = ((d or {}).get("settlement") or {}).get("truth_quiz_points") if isinstance(d, dict) else None
        for k in POINTS:
            v = d.get(k) if isinstance(d, dict) else None
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                out[k] = v
    return out


def points(root: Path) -> dict[str, int]:
    """{settle, per_right, fallback} for this run: its contract's ``settlement.truth_quiz_points``, the template's over it."""
    from neonrp.template import contract as C

    return _amounts(C.run_contract(root), _j(_meta(root) / "template.json", {}) or {})


def spec(root: Path) -> dict[str, Any]:
    """The plot's ``truth_quiz`` (the reached ending's plot, else the first plot that has one), or {}."""
    return next((p["truth_quiz"] for p in _plots(root) if isinstance(p.get("truth_quiz"), dict)), {})


def required(c: dict[str, Any] | None) -> bool:
    """The contract asks every template under it to write its three questions (``settlement.truth_quiz: required``)."""
    st = (c or {}).get("settlement")
    return isinstance(st, dict) and st.get("truth_quiz") == "required"


def applies(root: Path) -> bool:
    """A sandbox mystery run (its contract), or one whose plot writes its own quiz."""
    from neonrp.template import contract as C

    c = C.run_contract(root) or {}
    return required(c) or str(c.get("id") or "") in CONTRACTS or bool(spec(root))


def validate(q: Any, where: str = "truth_quiz") -> list[str]:
    """Problems with a plot's ``truth_quiz`` (empty = ok) — the plot lint's half."""
    if not isinstance(q, dict):
        return [f"{where} must be an object {{questions?, reward_soul?}}"]
    probs = []
    qs = q.get("questions")
    if qs is not None:
        if not isinstance(qs, list) or len(qs) != N:
            probs.append(f"{where}.questions must be a list of {N}")
        for i, x in enumerate(qs if isinstance(qs, list) else []):
            w = f"{where}.questions[{i}]"
            if not isinstance(x, dict) or not x.get("q") or not isinstance(x.get("options"), list) or len(x["options"]) < 2:
                probs.append(f"{w} needs q + at least 2 options")
                continue
            a = x.get("answer")
            if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < len(x["options"]):
                probs.append(f"{w}.answer must be the index of the right option")
    if q.get("reward_soul") is not None and not str(q.get("reward_soul") or "").strip():
        probs.append(f"{where}.reward_soul must be a soul's sid")
    return probs


class _Src(str):
    """A text as the plot wrote it — still this after an i18n layer was merged over it = the layer left it untranslated."""


def _mark(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _mark(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_mark(x) for x in v]
    return _Src(v) if isinstance(v, str) else v


def _has(v: Any, lang: str, src: str) -> bool:
    if isinstance(v, dict):
        return bool(str(v.get(lang) or "").strip())
    if isinstance(v, _Src):
        return lang == src and bool(v.strip())
    return isinstance(v, str) and bool(v.strip())


def lint(t: Any, wdir: Path | None, c: dict[str, Any] | None) -> list[tuple[str, str, str, str]]:
    """(level, code, where, msg) for a template's 「真相三问」: a contract that requires them gets them (``contract.truth_quiz``),
    and every plot's ``truth_quiz`` is well formed (``truth_quiz.schema``), in all four languages — ``{zh,en,ja,ko}`` texts
    or ``i18n/<lang>/<plot>/plot.json`` layers (``truth_quiz.lang``) — with a ``reward_soul`` from the cast that may leave
    (``truth_quiz.reward_soul``). 默认区 (reviewed) block · 自由区 / unsaid warn."""
    from neonrp.template import i18n as I

    lvl = "block" if getattr(t, "zone", None) == "reviewed" else "warn"
    out: list[tuple[str, str, str, str]] = []
    one = I.norm_lang(getattr(t, "lang", ""))  # a localized copy (lint --i18n-deep): its layer is laid on, it plays in one language
    src, langs = (one, (one,)) if one else (I.source_lang(t), I.LANGS)
    found = False
    for rel in t.plots:
        base = (_j(t.dir / rel / "plot.json", {}) or {})
        if not isinstance(base, dict) or "truth_quiz" not in base:
            continue
        tq, where = base["truth_quiz"], f"{base.get('id') or rel}.truth_quiz"
        probs = validate(tq, where)
        out += [(lvl, "truth_quiz.schema", where, p) for p in probs]
        if probs or not isinstance(tq, dict):
            continue
        if not tq.get("questions"):
            continue  # reported below when the contract needs them
        found = True
        answers = [x["answer"] for x in tq["questions"]]
        for lang in langs:
            over = {} if one else (_j(t.dir / I.DIR / lang / rel / "plot.json", {}) or {})
            eff = I.merge(_mark(tq), over.get("truth_quiz")) if isinstance(over, dict) and "truth_quiz" in over else _mark(tq)
            lw = f"{where}[{lang}]"
            lp = validate(eff, lw)
            if lp:
                out += [(lvl, "truth_quiz.schema", lw, p) for p in lp]
                continue
            if [x["answer"] for x in eff["questions"]] != answers:
                out.append((lvl, "truth_quiz.lang", lw, f"the {lang} layer changes a right answer — answers are the same in every language"))
            miss = [f"questions[{i}].{k}" for i, x in enumerate(eff["questions"])
                    for k, v in [("q", x["q"]), *((f"options[{j}]", o) for j, o in enumerate(x["options"]))] if not _has(v, lang, src)]
            if miss:
                out.append((lvl, "truth_quiz.lang", lw, f"no {lang} text for {', '.join(miss[:4])}{' …' if len(miss) > 4 else ''} — write "
                            f"{{zh, en, ja, ko}} texts or i18n/{lang}/{rel}/plot.json truth_quiz"))
        want = str(tq.get("reward_soul") or "").strip()
        if want:
            cast = cast_of(t, wdir)
            if want not in cast:
                out.append((lvl, "truth_quiz.reward_soul", f"{where}.reward_soul", f"{want!r} is not in the cast — a sid from the template's souls"))
            elif isinstance(cast[want], dict) and cast[want].get("takeable") is False:
                out.append((lvl, "truth_quiz.reward_soul", f"{where}.reward_soul", f"{want!r} is takeable: false — three right would give nothing"))
    applies_c = required(c) or str((c or {}).get("id") or "") in CONTRACTS
    raw = [((d or {}).get("settlement") or {}).get("truth_quiz_points") if isinstance((d or {}).get("settlement"), dict) else None
           for d in (c, getattr(t, "data", None))]
    for where, d in zip(("contract settlement.truth_quiz_points", "settlement.truth_quiz_points"), raw):
        bad = [k for k, v in (d.items() if isinstance(d, dict) else []) if k not in POINTS or not isinstance(v, int) or isinstance(v, bool) or v < 0]
        if d is not None and (not isinstance(d, dict) or bad):
            out.append(("warn", "truth_quiz.points", where, f"must be {{settle, per_right, fallback}} — whole numbers ≥ 0 (bad: {', '.join(bad) or 'not an object'})"))
    if applies_c and not any(isinstance(d, dict) and d for d in raw):
        out.append(("warn", "truth_quiz.points", "settlement.truth_quiz_points",
                    "no points for the three truths: neither the contract nor the template says {settle, per_right, fallback} — the run gives 0"))
    if required(c) and not found:
        out.append((lvl, "contract.truth_quiz", "settlement.truth_quiz",
                    f"the contract requires the three truth questions: a plot's truth_quiz.questions ({N} questions, q + options in "
                    "four languages, answer = the right index; reward_soul = a sid of the cast) — the engine writing them from the "
                    "solution is only a fallback"))
    return out


def cast_of(t: Any, wdir: Path | None) -> dict[str, Any]:
    """sid (and a world soul's instance id) → its soul.json (or None) for every character a template can cast — who a
    ``reward_soul`` may name."""
    from neonrp.template import _world_souls

    cast: dict[str, Any] = {}
    for row in getattr(t, "souls", None) or []:
        for r in ([{"sid": x} if isinstance(x, str) else x for x in row["pool"]] if isinstance(row.get("pool"), list) else [row]):
            if isinstance(r, dict) and r.get("sid"):
                cast.setdefault(str(r["sid"]), None)
    for sid, s in (_world_souls(wdir) if wdir is not None else {}).items():
        cast.setdefault(sid, None)
        if s.get("instance_id"):
            cast.setdefault(str(s["instance_id"]), None)
    for f in t.soul_files():
        sj = _j(f, {}) or {}
        if isinstance(sj, dict) and sj.get("sid"):
            cast[str(sj["sid"])] = sj
    return cast


# ── the questions ────────────────────────────────────────────────────────────

def _truth(root: Path, lang: str) -> str:
    for p in _plots(root):
        rv = p.get("reveal")
        if rv:
            return _pick(rv, lang)
    from neonrp.core.paths import get_data_dir_name

    try:
        return (Path(root) / get_data_dir_name(root) / "lore" / "gm-truth.md").read_text(encoding="utf-8")[:6000]
    except OSError:
        return ""


def _adapter(root: Path) -> Any:
    """The run's provider (its own function so tests inject a stub)."""
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import get_adapter_from_config

    return get_adapter_from_config(resolve_provider(load_config(root), None, None))


def parse(raw: str) -> list[dict[str, Any]] | None:
    """The model's answer → N well-formed questions, or None."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    qs = d.get("questions") if isinstance(d, dict) else None
    if not isinstance(qs, list) or validate({"questions": qs}):
        return None
    return [{"q": str(x["q"]), "options": [str(o) for o in x["options"]], "answer": int(x["answer"])} for x in qs]


def _generate(root: Path, lang: str, adapter: Any = None) -> list[dict[str, Any]] | None:
    from neonrp import prompts

    truth = _truth(root, lang)
    if not truth.strip():
        return None
    T = prompts.strings("truth_quiz", lang)
    ended = _j(_meta(root) / "ending.json", {}) or {}
    user = str(T["user"]).format(truth=truth, ending=str(ended.get("title") or ended.get("id") or "-"), lang_name=T["lang_name"])
    try:
        out = (adapter or _adapter(root)).generate(str(T["system"]), user)
        if getattr(out, "error", None):
            return None
        return parse(str(getattr(out, "raw_output", "") or getattr(out, "proposal_text", "") or ""))
    except Exception:  # noqa: BLE001 — no quiz is the answer to a model that fails, never a crash
        logger.warning("truth quiz generation failed", exc_info=True)
        return None


def questions(root: Path, lang: str, *, adapter: Any = None) -> tuple[list[dict[str, Any]] | None, str]:
    """(questions with answers, by: author | model | none) — the author's, else the cached / freshly written ones."""
    own = spec(root).get("questions")
    if isinstance(own, list) and not validate({"questions": own}):
        return [{"q": _pick(x["q"], lang), "options": [_pick(o, lang) for o in x["options"]], "answer": int(x["answer"])} for x in own], "author"
    cache = _j(_meta(root) / _CACHE, {}) or {}
    if cache.get("lang") == lang and cache.get("questions"):
        return cache["questions"], str(cache.get("by") or "model")
    qs = _generate(root, lang, adapter)
    if qs:
        _w(_meta(root) / _CACHE, {"lang": lang, "by": "model", "questions": qs})
        return qs, "model"
    return None, "none"


# ── who can come home ────────────────────────────────────────────────────────

def _companions(root: Path) -> list[str]:
    from neonrp.core import holdings

    party = holdings.members(root)
    if party is None:
        party = [iid for iid, s in holdings._souls(root).items() if s.get("role") == "companion"]
    return list(party)


def takeable(root: Path) -> list[dict[str, Any]]:
    """The characters the player may take home: their author lets them leave, and the player met them (or they walk
    with the player)."""
    from neonrp.core import people, player_data

    comp = set(_companions(root))
    dirs = people._soul_dirs(root)
    seen = people.seen(root)
    out = []
    for iid, s in player_data.run_souls(root).items():
        if not s["takeable"]:
            continue
        met = bool((people._state(dirs.get(iid)).get("status") or {}).get("met_player")) or (bool(s.get("npc")) and iid in seen)  # a plot NPC: the player came across it
        if met or iid in comp:
            out.append({"iid": iid, "sid": s["sid"], "name": s["name"], "companion": iid in comp})
    return out


def reward_soul(root: Path) -> dict[str, Any] | None:
    """Who comes home with full memory on three right: the author's ``reward_soul``, else the companion."""
    from neonrp.core import player_data

    souls = player_data.run_souls(root)
    want = str(spec(root).get("reward_soul") or "").strip()
    pick = next((i for i, s in souls.items() if want and (s["sid"] == want or i == want)), None)
    if pick is None and not want:
        pick = next((i for i in _companions(root) if i in souls), None)
    if pick is None or not souls[pick]["takeable"]:
        return None
    return {"iid": pick, "sid": souls[pick]["sid"], "name": souls[pick]["name"]}


# ── the screen's two calls ───────────────────────────────────────────────────

def quiz(root: Path, lang: str | None = None, *, adapter: Any = None) -> dict[str, Any]:
    from neonrp.core import settlement
    from neonrp.core.output_lang import prompt_lang

    lang = lang or prompt_lang(root)
    base: dict[str, Any] = {"lang": lang, "questions": [], "reward_soul": None, "points": points(root)}
    if not applies(root):
        return {**base, "state": "unavailable"}
    if settlement.read(root) is None:
        return {**base, "state": "locked"}
    done = _j(_meta(root) / _RESULT)
    qs, by = questions(root, lang, adapter=adapter)
    out = {**base, "by": by, "reward_soul": reward_soul(root),
           "questions": [{"id": i, "q": x["q"], "options": x["options"]} for i, x in enumerate(qs or [])]}
    if isinstance(done, dict):
        return {**out, "state": "answered", "result": done}
    return {**out, "state": "open" if qs else "unavailable"}


def answer(root: Path, answers: list[Any] | None, take: str | None = None, *, lang: str | None = None,
           adapter: Any = None) -> dict[str, Any]:
    """Grade once and hand out what was earned: on three right the reward soul (full memory); points every run, and the
    fallback points when the reward soul did not come home. ``take`` (the old floor's pick) is ignored."""
    from neonrp.core import achievements, player_data, settlement
    from neonrp.core.output_lang import prompt_lang

    del take  # 10-20: the floor is points now — an old client may still send its pick
    lang = lang or prompt_lang(root)
    if not applies(root) or settlement.read(root) is None:
        return {"error": "locked"}
    done = _j(_meta(root) / _RESULT)
    if isinstance(done, dict):
        return done
    qs, _by = questions(root, lang, adapter=adapter)
    given = list(answers or [])
    right = [bool(qs) and i < len(given) and str(given[i]) == str(x["answer"]) for i, x in enumerate(qs or [])]
    score = sum(right)
    all_right = bool(qs) and score == len(qs)
    gained = []
    rs = reward_soul(root) if all_right else None
    if rs and player_data.take(root, rs["iid"], "truth_quiz", memory="full"):  # new, or one home fresh now with full memory
        gained.append({"sid": rs["sid"], "name": rs["name"], "memory": "full", "how": "truth_quiz"})
    pt = points(root)
    world, run = player_data.world_of(root), Path(root).name
    res = {"score": score, "total": len(qs or []), "all_right": all_right, "right": right,
           "answer": [x["answer"] for x in qs or []], "gained": gained, "delivered": bool(gained),
           "fallback": not gained, "no_questions": not qs, "rewards": []}
    for rid, src, amt in ((f"settlement:{world}:{run}", "settlement:quiz", pt["settle"] + pt["per_right"] * score),
                          (f"settlement:{world}:{run}:fallback", "settlement:quiz_fallback", pt["fallback"] if not gained else 0)):
        if amt > 0:
            res["rewards"].append({"id": rid, "kind": "points", "amount": amt, "status": "pending", "source": src})
            player_data.add_reward(rid, "points", world, src, amount=amt)
    res["achievements"] = achievements.after_quiz(root, res)
    res["platform"] = _report(root, res, world, run)
    _w(_meta(root) / _RESULT, res)
    return res


def _report(root: Path, res: dict[str, Any], world: str, run: str) -> str:
    """The run's points told to the platform (core/chronicle.reward → billing, which pays on its own facts, 10-21) — one
    event for the run (``settlement:<world>:<run>``, the sum). → reported · own_key · local · free_zone · guest · none · off"""
    from neonrp.core import chronicle

    try:
        return chronicle.reward(root, ref=f"settlement:{world}:{run}", points=sum(int(r["amount"]) for r in res["rewards"]),
                                source="settlement:quiz", score=res["score"], total=res["total"])
    except Exception:  # noqa: BLE001 — telling the platform never takes the points away here
        logger.warning("truth quiz points not reported", exc_info=True)
        return "error"
