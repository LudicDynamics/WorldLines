"""The 「真相三问」 on the creation desk (PLATFORM-PLAY-RULES-1015 §11, 10-18): a creator writes and edits the plot's
``truth_quiz`` — three questions, their options, the right answer, the ``reward_soul`` picked from the world's cast — and
can have the engine write a first draft from the truth (「点生成」) to edit after. The questions are the run's
(core/truth_quiz.py plays them at the settlement); this module is only the desk's half.

    form(t)["truth_quiz"] = {required, n, options, langs, lang, souls: [{sid, name, takeable}], reward_default,
                              points: {settle, per_right, fallback}}
    addition["truth_quiz"] = {questions: [{q, options, answer}], reward_soul?}     # q / an option: a text or {zh, en, ja, ko}
    POST …/<template>/creation/truth-quiz/generate {reveal?, story?, lang?} → {ok, questions, problems}

Open when the template opens a creation layer and either lists ``truth_quiz`` in ``creation.add`` or plays under a
contract that settles with the three questions (``mystery-trpg``). Required only when the contract requires them and
none of the template's own plots carries them — over a template that has its own, the creator's are their plot's.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from neonrp.core import truth_quiz as Q

logger = logging.getLogger(__name__)

KEY = "truth_quiz"
OPTIONS = 3   # how many options the desk shows per question (validate wants ≥ 2)


def _contract(t: Any) -> dict[str, Any]:
    from neonrp.template import contract as C

    if not getattr(t, "play_contract", ""):
        return {}
    try:
        return C.load(t.play_contract) or {}
    except Exception:  # noqa: BLE001 — an unknown contract is the lint's to report
        return {}


def _own_plots(t: Any) -> list[dict[str, Any]]:
    out = []
    for rel in getattr(t, "plots", None) or []:
        try:
            p = json.loads((Path(t.dir) / rel / "plot.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(p, dict):
            out.append(p)
    return out


def opened(t: Any) -> bool:
    raw = (getattr(t, "data", None) or {}).get("creation")
    if not isinstance(raw, dict) or not raw:
        return False
    c = _contract(t)
    return KEY in (raw.get("add") or []) or Q.required(c) or str(c.get("id") or "").split("@")[0] in Q.CONTRACTS


def souls(t: Any) -> list[dict[str, Any]]:
    """Who a ``reward_soul`` may be: the template's cast (sid · name · takeable), the ones that may leave first."""
    from neonrp.template import _world_souls, world_dir

    wdir = world_dir(t)
    iids = {str(s.get("instance_id")) for s in (_world_souls(wdir) if wdir is not None else {}).values() if s.get("instance_id")}
    names: dict[str, str] = {}
    for row in getattr(t, "souls", None) or []:
        for r in ([{"sid": x} if isinstance(x, str) else x for x in row["pool"]] if isinstance(row.get("pool"), list) else [row]):
            if isinstance(r, dict) and r.get("sid") and r.get("name"):
                names[str(r["sid"])] = str(r["name"])
    out = []
    for sid, sj in Q.cast_of(t, wdir).items():
        if sid in iids and sj is None:
            continue  # a world soul's instance id: the same character as its sid
        sj = sj if isinstance(sj, dict) else {}
        out.append({"sid": sid, "name": str(sj.get("name_local") or sj.get("name") or names.get(sid) or sid),
                    "takeable": sj.get("takeable") is not False})
    return sorted(out, key=lambda s: not s["takeable"])


def form_part(t: Any) -> dict[str, Any]:
    """The desk's 「真相三问」 part of creation.form (absent when the template does not open it)."""
    from neonrp.template import i18n as I

    if not opened(t):
        return {}
    have = any(isinstance(p.get(KEY), dict) and p[KEY].get("questions") for p in _own_plots(t))
    cast = souls(t)
    return {KEY: {"required": Q.required(_contract(t)) and not have, "n": Q.N, "options": OPTIONS, "langs": list(I.LANGS),
                  "lang": I.source_lang(t), "souls": cast,
                  "reward_default": next((s["sid"] for s in cast if s["takeable"]), None),
                  "points": Q._amounts(_contract(t), getattr(t, "data", None) or {})}}   # what the player is promised (preview)


def _text(v: Any) -> bool:
    if isinstance(v, dict):
        return any(str(x or "").strip() for x in v.values())
    return bool(str(v or "").strip())


def check(t: Any, tq: Any) -> list[str]:
    """Problems with the creator's three questions (empty = ok); ``tq`` None = they wrote none."""
    part = form_part(t).get(KEY)
    if part is None:
        return [] if tq in (None, {}) else ["the template does not ask for the three truth questions"]
    if tq in (None, {}) or (isinstance(tq, dict) and not tq.get("questions") and not tq.get("reward_soul")):
        return [f"{KEY}: required"] if part["required"] else []
    probs = Q.validate(tq, KEY)
    if probs:
        return probs
    if not tq.get("questions"):
        probs.append(f"{KEY}.questions: required" if part["required"] else f"{KEY}.questions: write the {Q.N} questions")
    for i, x in enumerate(tq.get("questions") or []):
        if not _text(x["q"]):
            probs.append(f"{KEY}.questions[{i}].q: required")
        probs += [f"{KEY}.questions[{i}].options[{j}]: required" for j, o in enumerate(x["options"]) if not _text(o)]
    want = str(tq.get("reward_soul") or "").strip()
    if want:
        one = next((s for s in part["souls"] if s["sid"] == want), None)
        if one is None:
            probs.append(f"{KEY}.reward_soul: {want!r} is not in the cast")
        elif not one["takeable"]:
            probs.append(f"{KEY}.reward_soul: {want!r} cannot leave the world (takeable: false)")
    return probs


def _clean(v: Any) -> Any:
    if isinstance(v, dict):
        d = {k: str(x).strip() for k, x in v.items() if str(x or "").strip()}
        return d if len(d) > 1 else next(iter(d.values()), "")
    return str(v or "").strip()


def to_plot(tq: dict[str, Any]) -> dict[str, Any]:
    """The checked questions as a plot's ``truth_quiz`` (empty language slots dropped; one language left = a plain text)."""
    out: dict[str, Any] = {}
    if tq.get("questions"):
        out["questions"] = [{"q": _clean(x["q"]), "options": [_clean(o) for o in x["options"]], "answer": int(x["answer"])}
                            for x in tq["questions"]]
    if str(tq.get("reward_soul") or "").strip():
        out["reward_soul"] = str(tq["reward_soul"]).strip()
    return out


# ── 「点生成」 ─────────────────────────────────────────────────────────────

def _truth(t: Any, reveal: Any, lang: str) -> str:
    """What the questions ask about: the reveal the creator wrote, else the template's plots' reveal, else its world's
    GM truth (the run's own fallback, core/truth_quiz._truth)."""
    from neonrp.template import world_dir

    if _text(reveal):
        return Q._pick(reveal, lang).strip() or next(str(x) for x in reveal.values() if str(x or "").strip())
    for p in _own_plots(t):
        if p.get("reveal"):
            return Q._pick(p["reveal"], lang)
    wdir = world_dir(t)
    try:
        return (wdir / "game" / "lore" / "gm-truth.md").read_text(encoding="utf-8")[:6000] if wdir else ""
    except OSError:
        return ""


def parse(raw: str, langs: list[str] | tuple[str, ...], lang: str) -> list[dict[str, Any]] | None:
    """The model's answer → N questions whose texts are {lang: text} for ``langs`` (a plain text = the desk language)."""
    import re

    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else None
    except ValueError:
        return None
    qs = d.get("questions") if isinstance(d, dict) else None
    if not isinstance(qs, list) or Q.validate({"questions": qs}):
        return None

    def tx(v: Any) -> dict[str, str] | None:
        got = {k: str(v.get(k) or "").strip() for k in langs} if isinstance(v, dict) else {lang: str(v or "").strip()}
        got = {k: x for k, x in got.items() if x}
        return got if got.get(lang) else None

    out = []
    for x in qs:
        q, opts = tx(x["q"]), [tx(o) for o in x["options"]]
        if q is None or None in opts:
            return None
        out.append({"q": q, "options": opts, "answer": int(x["answer"])})
    return out


def _adapter() -> Any:
    """The creator's model (the creation provider — the browser engine's own ``web`` one too); its own function so
    tests inject a stub."""
    from neonrp.core.hub_publish import adapter_for_preset

    return adapter_for_preset()


def generate(t: Any, *, reveal: Any = None, story: str = "", lang: str = "", adapter: Any = None) -> dict[str, Any]:
    """Three questions from the truth, in the four languages, as a draft the creator edits → {ok, questions, problems}
    (problems = what check() still says, e.g. none in the cast may leave) · {ok: false, error: closed | no_truth | model}."""
    from neonrp import prompts
    from neonrp.template import i18n as I

    if not opened(t):
        return {"ok": False, "error": "closed"}
    lang = I.norm_lang(lang) or I.source_lang(t)
    truth = _truth(t, reveal, lang)
    if not truth.strip():
        return {"ok": False, "error": "no_truth"}
    S = prompts.strings("truth_quiz_author", lang)
    user = str(S["user"]).format(truth=truth, story=(story or "").strip()[:3000] or "-", n=Q.N, k=OPTIONS,
                                 langs=", ".join(I.LANGS), lang=lang)
    try:
        out = (adapter or _adapter()).generate(str(S["system"]), user)
        if getattr(out, "error", None):
            return {"ok": False, "error": "model"}
        qs = parse(str(getattr(out, "raw_output", "") or getattr(out, "proposal_text", "") or ""), I.LANGS, lang)
    except Exception:  # noqa: BLE001 — a failing model leaves the creator their own pen, never a crash
        logger.warning("truth quiz draft failed", exc_info=True)
        return {"ok": False, "error": "model"}
    if not qs:
        return {"ok": False, "error": "model"}
    part = form_part(t).get(KEY) or {}
    tq = {"questions": qs, **({"reward_soul": part["reward_default"]} if part.get("reward_default") else {})}
    return {"ok": True, **tq, "problems": check(t, tq)}
