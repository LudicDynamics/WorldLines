"""What the player is working toward, as the player knows it (10-15, the standard front end §5.18).

    GET /api/v1/play/engine/objective
    → {lang,
       now:   {plot, stage, name, goal} | null,                          the current stage of the main plot
       plots: [{plot, title, stage, steps: [{index, name, goal, state: done|current|hidden}]}],
       jobs:  [{id, name, summary, state, state_label, active}],         taken / offered commissions the player knows of
       exit:  {on, label}}                                                how the run ends (the play contract), in words

A plot's ``stages`` is a list of names, or of ``{name, goal}`` (``goal`` = one line for the player, no spoilers — a
string in the run's language, or ``{zh, en, ja, ko}``; the language layer ``i18n/<lang>/`` translates it like any
field). A stage not reached yet has no name and no goal here (``hidden``). A commission's state word is the world's own
(``taken``, ``accepted``, …) — the word lists in ``prompts/objective.<lang>.json`` fold it into one of ``offered · active · done · failed ·
abandoned`` (``locked`` = not listed at all); ``state_label`` is that in the run's language. An offer is listed once the
player has come across it (core/play_view.visible_entries); one they took, finished or failed always is.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

JOB_STATES = ("offered", "active", "done", "failed", "abandoned")


def _job_words() -> dict[str, set[str]]:
    """state → every word a world may write for it, in all four languages (prompts/objective.<lang>.json ``job_words``;
    ``hidden`` = not on any board yet)."""
    from neonrp.prompts import LANGS, strings

    out: dict[str, set[str]] = {}
    for lg in LANGS:
        for state, words in (strings("objective", lg).get("job_words") or {}).items():
            out.setdefault(state, set()).update(str(w).casefold() for w in words)
    return out


def stage_name(s: Any) -> str:
    """A ``stages`` entry's name: a plain string, or ``{name, goal}``."""
    if isinstance(s, dict):
        n = s.get("name")
        return str(n.get("zh") or next(iter(n.values()), "") if isinstance(n, dict) else n or "")
    return str(s or "")


def stage_goal(s: Any, lang: str) -> str:
    g = s.get("goal") if isinstance(s, dict) else None
    if isinstance(g, dict):
        return str(g.get(lang) or g.get("en") or g.get("zh") or "")
    return str(g or "")


def job_state(raw: Any) -> str | None:
    """The world's word → one of JOB_STATES; None = not open to the player yet (locked); a word nobody listed counts as
    an offer (the board shows it, the screen does not guess that it was taken)."""
    w = str(raw or "").strip().casefold()
    words = _job_words()
    if w in words.get("hidden", set()):
        return None
    for state in JOB_STATES:
        if w in words.get(state, set()):
            return state
    return "offered"


def _T(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("objective", lang)


def objective(root: Path, lang: str | None = None) -> dict[str, Any]:
    from neonrp import template as TP
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.paths import get_data_dir_name
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    T = _T(lang)
    view = TP.run_view(root) or {}
    plots_idx = TP._j(Path(root) / get_data_dir_name(root) / "meta" / "plots.json", {}) or {}
    plots: list[dict[str, Any]] = []
    now = None
    for p in view.get("plots") or []:
        pdef = TP._j(Path(root) / str((plots_idx.get(p["id"]) or {}).get("dir") or "") / "plot.json", {}) or {}
        raw = pdef.get("stages") if isinstance(pdef.get("stages"), list) else []
        if not raw:
            continue
        cur = p.get("stage") if isinstance(p.get("stage"), int) and not isinstance(p.get("stage"), bool) else 0
        steps = []
        for i, s in enumerate(raw):
            state = "done" if i < cur else ("current" if i == cur else "hidden")
            steps.append({"index": i, "name": stage_name(s) if state != "hidden" else "",
                          "goal": stage_goal(s, lang) if state != "hidden" else "", "state": state})
        plots.append({"plot": p["id"], "title": p.get("title"), "stage": cur, "steps": steps})
        if now is None and 0 <= cur < len(raw):
            now = {"plot": p["id"], "stage": cur, "name": stage_name(raw[cur]), "goal": stage_goal(raw[cur], lang)}
    reg = load_registry(root)
    from neonrp.core import play_view

    vis = play_view.visible_entries(root, reg)
    jobs = []
    for e in reg.of_class("job"):
        st = job_state(e.props.get("state") or e.props.get("status"))
        if st is None or (e.id not in vis and st not in ("active", "done", "failed")):  # locked, or an offer not come across
            continue
        jobs.append({"id": e.id, "name": str(e.name or e.id), "summary": str(e.props.get("summary") or ""), "state": st,
                     "state_label": str((T.get("job_states") or {}).get(st) or st), "active": st == "active"})
    jobs.sort(key=lambda j: ("active", "offered", "done", "failed", "abandoned").index(j["state"]))  # the taken ones first
    from neonrp.template import contract as C

    ex = (C.run_contract(root) or {}).get("exit") or {}
    on = str(ex.get("on") or "")
    key = f"{on}:{ex.get('segment') or ex.get('via') or ''}".rstrip(":")
    labels = T.get("exits") or {}
    exit_ = {"on": on, "label": str(labels.get(key) or labels.get(on) or "")} if on else None
    return {"lang": lang, "now": now, "plots": plots, "jobs": jobs, "exit": exit_}
