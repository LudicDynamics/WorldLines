"""Achievements (PLATFORM-PLAY-RULES-1015 §6 §9, 10-15): every game has them; the engine brings a set of its own,
a template may add its own, and an unlocked one goes into the player's record (core/player_data ``achievements``) with
its points written as a pending reward (``rewards``, the platform pays out).

    GET /api/v1/play/engine/achievements
    → {lang, achievements: [{id, title, desc, scope: player | world, points, unlocked, at?}]}
    event  achievement.unlocked {turn, id, title, desc, scope, points}      (/engine/beats)

Built in (titles in four languages, ``prompts/achievements.<lang>.json``):

    first_ending · first_character · characters_5 · first_milestone     once per player
    true_ending · all_endings · quiz_perfect · places_5 · places_10     once per world

A template's own (``template.json`` ``achievements``) — no if / else, one condition from a list::

    [{"id": "kind_heart", "title": {"zh": "…", "en": "…"}, "desc": {…}, "when": "ending:E02", "points": 20}]
    when: ending:<id> · ending_kind:<kind> · flag:<key> · stage:<plot>:<n> · var:<key>:<n> · places:<n> ·
          character:<sid> · milestone:<n> · quiz_perfect · run_end

A play contract's own (``<id>.play-contract.json`` ``achievements``, 10-18): the same rows, for every world played
under it — so only the conditions that name no world's things (``CONTRACT_WHEN``: ending_kind · places · milestone ·
quiz_perfect · run_end). ``run_end`` = the run reached its exit (``run.settled``: an ending, or a death that ends it).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BUILTIN: dict[str, dict[str, Any]] = {
    "first_ending": {"scope": "player", "points": 20},
    "true_ending": {"scope": "world", "points": 50},
    "all_endings": {"scope": "world", "points": 80},
    "quiz_perfect": {"scope": "world", "points": 30},
    "first_character": {"scope": "player", "points": 20},
    "characters_5": {"scope": "player", "points": 50},
    "places_5": {"scope": "world", "points": 10},
    "places_10": {"scope": "world", "points": 20},
    "first_milestone": {"scope": "player", "points": 20},
    "run_complete": {"scope": "world", "points": 10},
}
WHEN = ("ending:", "ending_kind:", "flag:", "stage:", "var:", "places:", "character:", "milestone:")
WHEN_BARE = ("quiz_perfect", "run_end")
CONTRACT_WHEN = ("ending_kind:", "places:", "milestone:")
WHEN_HELP = ("ending:<id> · ending_kind:<kind> · flag:<key> · stage:<plot>:<n> · var:<key>:<n> · places:<n> · "
             "character:<sid> · milestone:<n> · quiz_perfect · run_end")
CUSTOM_POINTS = 10


def when_ok(v: Any, heads: tuple[str, ...] = WHEN) -> bool:
    s = str(v or "")
    if s in WHEN_BARE:
        return True
    head = next((h for h in heads if s.startswith(h)), None)
    if head is None or not s[len(head):]:
        return False
    if head in ("places:", "milestone:"):
        return s[len(head):].isdigit()
    if head in ("stage:", "var:"):
        key, _, n = s[len(head):].rpartition(":")
        return bool(key) and n.lstrip("-").isdigit()
    return True


def holds(when: str, ctx: dict[str, Any]) -> bool:
    """One condition against what is true now. ``ctx``: ended (ending id) · ended_kind · flags · places (count) ·
    gained (sids gained from this world) · quiz_perfect · milestones (count) · run_end · vars ({key: value})."""
    head, _, arg = str(when).partition(":")
    if not arg:
        return bool(ctx.get(head))  # quiz_perfect · run_end
    if head in ("stage", "var"):
        key, _, n = arg.rpartition(":")
        key = f"{key}.stage" if head == "stage" else key
        v = (ctx.get("vars") or {}).get(key)
        return isinstance(v, (int, float)) and not isinstance(v, bool) and n.lstrip("-").isdigit() and v >= int(n)
    return bool({"ending": ctx.get("ended") == arg, "ending_kind": bool(ctx.get("ended")) and ctx.get("ended_kind") == arg,
                 "flag": arg in (ctx.get("flags") or ()), "character": arg in (ctx.get("gained") or ()),
                 "places": arg.isdigit() and int(ctx.get("places") or 0) >= int(arg),
                 "milestone": arg.isdigit() and int(ctx.get("milestones") or 0) >= int(arg)}.get(head))


def validate(rows: Any, *, heads: tuple[str, ...] = WHEN, where: str = "achievements") -> list[str]:
    """Problems with a template's ``achievements`` (the template lint's half); ``heads=CONTRACT_WHEN`` for a contract's."""
    if rows is None:
        return []
    if not isinstance(rows, list):
        return [f"{where} must be a list of {{id, title, desc?, when, points?}}"]
    probs, seen = [], set()
    for i, r in enumerate(rows):
        w = f"{where}[{i}]"
        if not isinstance(r, dict) or not str(r.get("id") or "").strip():
            probs.append(f"{w} needs an id")
            continue
        if r["id"] in BUILTIN or r["id"] in seen:
            probs.append(f"{w}.id {r['id']!r} is taken (a built-in or listed twice)")
        seen.add(r["id"])
        if not r.get("title"):
            probs.append(f"{w} needs a title")
        if not when_ok(r.get("when"), heads):
            probs.append(f"{w}.when must be one of " + (WHEN_HELP if heads == WHEN else
                                                       "ending_kind:<kind> · places:<n> · milestone:<n> · quiz_perfect · run_end"))
        if r.get("points") is not None and (not isinstance(r["points"], int) or isinstance(r["points"], bool) or r["points"] < 0):
            probs.append(f"{w}.points must be a whole number ≥ 0")
    return probs


def _meta(root: Path) -> Path:
    from neonrp.core.paths import get_data_dir_name

    return Path(root) / get_data_dir_name(root) / "meta"


def _j(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or v.get("zh") or next(iter(v.values()), ""))
    return str(v or "")


def custom(root: Path) -> list[dict[str, Any]]:
    """The template's own, then its play contract's (a template's id wins over the contract's)."""
    rows = (_j(_meta(root) / "template.json", {}) or {}).get("achievements")
    out = [r for r in rows if isinstance(r, dict) and r.get("id") and when_ok(r.get("when"))] if isinstance(rows, list) else []
    from neonrp.template import contract as _contract

    have = {r["id"] for r in out}
    for r in ((_contract.run_contract(root) or {}).get("achievements") or []):
        if isinstance(r, dict) and r.get("id") and r["id"] not in have and r["id"] not in BUILTIN and when_ok(r.get("when"), CONTRACT_WHEN):
            out.append({**r, "contract": True})
    return out


def catalog(root: Path, lang: str) -> list[dict[str, Any]]:
    """Every achievement this run can unlock, in the run's language: the built-ins, then the template's own."""
    from neonrp import prompts

    T = prompts.strings("achievements", lang).get("builtin") or {}
    out = [{"id": k, "title": str((T.get(k) or {}).get("title") or k), "desc": str((T.get(k) or {}).get("desc") or ""),
            "scope": v["scope"], "points": v["points"], "builtin": True} for k, v in BUILTIN.items()]
    for r in custom(root):
        out.append({"id": str(r["id"]), "title": _pick(r.get("title"), lang), "desc": _pick(r.get("desc"), lang), "scope": "world",
                    "points": int(r.get("points") if isinstance(r.get("points"), int) else CUSTOM_POINTS), "when": r["when"],
                    "builtin": False})
    return out


def listing(root: Path, lang: str | None = None) -> dict[str, Any]:
    from neonrp.core import player_data
    from neonrp.core.output_lang import prompt_lang

    lang = lang or prompt_lang(root)
    world = player_data.world_of(root)
    have = player_data.read()["achievements"]
    rows = []
    for a in catalog(root, lang):
        hit = next((h for h in have if h.get("id") == a["id"] and (a["scope"] == "player" or h.get("world") == world)), None)
        rows.append({**{k: v for k, v in a.items() if k != "builtin"}, "unlocked": hit is not None, **({"at": hit.get("at")} if hit else {})})
    return {"lang": lang, "achievements": rows}


def _unlock(root: Path, aid: str, source: str, lang: str) -> dict[str, Any] | None:
    from neonrp.core import player_data

    a = next((x for x in catalog(root, lang) if x["id"] == aid), None)
    if a is None:
        return None
    world = player_data.world_of(root)
    if not player_data.unlock_achievement(aid, world, source, once=a["scope"] == "player"):
        return None
    if a["points"]:
        rid = f"achievement:{aid}" if a["scope"] == "player" else f"achievement:{world}:{aid}"
        player_data.add_reward(rid, "points", world, f"achievement:{aid}", amount=a["points"])
    return {"id": aid, "title": a["title"], "desc": a["desc"], "scope": a["scope"], "points": a["points"]}


def _places_found(root: Path, reg: Any) -> int:
    from neonrp.core import people

    seen = people.seen(root)
    return sum(1 for e in reg.of_class("place") if e.id in seen or e.id == reg.player_location)


def _ending_kind(root: Path, eid: str) -> str:
    from neonrp.core import settlement

    return str(next((e.get("kind") for e in settlement._installed_endings(root) if e["id"] == eid), "") or "")


def context(root: Path, reg: Any, *, ended: str | None = None, quiz_perfect: bool = False, milestones: int | None = None,
            run_end: bool = False) -> dict[str, Any]:
    """What :func:`holds` checks a condition against, read off the run now (core/rewards uses the same)."""
    from neonrp.core import player_data

    pd = player_data.read()
    world = player_data.world_of(root)
    return {"ended": ended or None, "ended_kind": _ending_kind(root, ended) if ended else "", "quiz_perfect": quiz_perfect,
            "milestones": milestones or 0, "run_end": run_end,
            "places": _places_found(root, reg) if reg is not None else 0,
            "flags": {k[5:] for k, v in (reg.variables.items() if reg is not None else []) if k.startswith("flag.") and v.value},
            "vars": {k: v.value for k, v in (reg.variables.items() if reg is not None else [])},
            "gained": {c.get("sid") for c in pd["characters"] if c.get("world") == world}}


def _check(root: Path, reg: Any, *, ended: str | None = None, quiz_perfect: bool = False, milestones: int | None = None,
           run_end: bool = False) -> list[str]:
    """The ids whose condition holds now (unlocked or not — :func:`_unlock` keeps each once)."""
    from neonrp.core import player_data, settlement

    pd = player_data.read()
    world = player_data.world_of(root)
    ctx = context(root, reg, ended=ended, quiz_perfect=quiz_perfect, milestones=milestones, run_end=run_end)
    ids: list[str] = []
    if run_end:
        ids.append("run_complete")
    if ended:
        ids.append("first_ending")
        if ctx["ended_kind"] == "true":
            ids.append("true_ending")
        mine = {e.get("id") for e in pd["endings"] if e.get("world") == world}
        every = {e["id"] for e in settlement._installed_endings(root)}
        if every and every <= mine:
            ids.append("all_endings")
    if quiz_perfect:
        ids.append("quiz_perfect")
    if pd["characters"]:
        ids.append("first_character")
    if len(pd["characters"]) >= 5:
        ids.append("characters_5")
    n = ctx["places"]
    ids += [k for k, m in (("places_5", 5), ("places_10", 10)) if n >= m]
    if milestones:
        ids.append("first_milestone")
    ids += [str(r["id"]) for r in custom(root) if holds(str(r["when"]), ctx)]
    return ids


def after_apply(root: Path, reg: Any, res: Any) -> list[dict[str, Any]]:
    """After a beat landed: what it unlocked (the ending that fired, flags, places, stages, characters gained)."""
    from neonrp.core.output_lang import prompt_lang

    ended = str((res.ended or {}).get("id") or "") if isinstance(getattr(res, "ended", None), dict) else ""
    lang = prompt_lang(root)
    total = None
    if getattr(res, "milestones", None):
        from neonrp.core import milestones as _ms

        total = len(_ms.listing(root)["milestones"])
    out = [u for aid in _check(root, reg, ended=ended or None, milestones=total, run_end=bool(getattr(res, "settled", None)))
           if (u := _unlock(root, aid, f"turn:{getattr(res, 'turn', 0)}", lang))]
    return [{"turn": getattr(res, "turn", None), **u} for u in out]


def after_quiz(root: Path, result: dict[str, Any]) -> list[dict[str, Any]]:
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = prompt_lang(root)
    reg = load_registry(root)
    return [u for aid in _check(root, reg, quiz_perfect=bool(result.get("all_right"))) if (u := _unlock(root, aid, "settlement:quiz", lang))]


def describe(aid: str, world: str = "", lang: str = "zh") -> dict[str, Any] | None:
    """One achievement's face without a run — for the player's record (the Hub's 「我的」 page): a built-in by its id, a
    template's own by the template id it was earned in (``world``). {title, desc, points, scope}, or None."""
    from neonrp import prompts

    if aid in BUILTIN:
        row = (prompts.strings("achievements", lang).get("builtin") or {}).get(aid) or {}
        return {"title": str(row.get("title") or aid), "desc": str(row.get("desc") or ""), **BUILTIN[aid]}
    if not world:
        return None
    try:
        from neonrp import template

        tdir = template.discover().get(world)
        tj = json.loads((Path(tdir) / "template.json").read_text(encoding="utf-8")) if tdir else {}
        rows = list(tj.get("achievements") or [])
        if tj.get("play_contract"):  # the contract's own come after (10-18)
            from neonrp.template import contract as _contract

            try:
                rows += list(_contract.load(str(tj["play_contract"])).get("achievements") or [])
            except _contract.ContractError:
                pass
    except Exception:  # noqa: BLE001 — a template that does not load names nothing
        return None
    r = next((x for x in rows or [] if isinstance(x, dict) and x.get("id") == aid), None)
    if r is None:
        return None
    return {"title": _pick(r.get("title"), lang), "desc": _pick(r.get("desc"), lang),
            "points": int(r["points"]) if isinstance(r.get("points"), int) else CUSTOM_POINTS, "scope": "world"}
