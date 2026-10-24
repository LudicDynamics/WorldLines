"""「查看」a person / a thing / a place, as the player knows it (10-16: a click showed the name again and nothing else).

    GET  /api/v1/play/engine/inspect?target=<entry id | name>
    → {lang, found, kind: person|item|place, id, name, ...}
       person  sid? · role · intro (one line) · appearance · relation? · trust? · here · met · portrait_slot
       item    desc · source? (how it came to the player / where it lies) · held · desc_by: world|inspect · needs_desc
       place   desc · parent
    POST /api/v1/play/engine/inspect {target}
    → the same, with a thing's description written when the world has none (one model call, once per run)

What a person shows is what the player knows — the same line as core/people: the one-line intro the world wrote for
the player (``soul.json`` ``intro_i18n`` / ``character/profile.json`` summary · an NPC's title), what they look like
(``appearance`` / ``look``), the relation label (``disposition``) and trust. Never ``background/`` (secrets), the
persona, the rules, a relationship's ``truth``, ``game/lore/gm-truth.md``. Someone here but not met has no name.

Someone, or a place, the world wrote nothing about that the player may see gets a few lines written on open the same way:
a person only their outward impression (how they look, carry themselves, sound — from their name or how they appear,
the world's card, where they stand, the prose they came up in; never a persona, a secret or a truth), kept as the entry's
``props.impression``; a place its ``props.summary``.

A thing's description is the world's own (``summary`` / ``desc`` / ``description`` …, already in the run's language: the
i18n layer was laid over the run when it was built). A thing without one gets one written — the thing's name, the
world's card (title · pitch), where it is, the prose it last came up in — on the run's provider (the same adapter a turn
uses, metered the same way) or the configured small judge model, in the run's language. It is written once and kept
in the run's entries overlay (``<data>/meta/entries.json`` ``props.summary`` + ``summary_by: inspect``) — the template is
never touched; every later read (this call, ``entities?cls=item``, the ``[inspect …]`` action) finds it there. A model
error answers with the name only (``desc: ""``) and is not cached, so the next open tries again.

Only what the player has come across answers (core/play_view.visible_entries); anything else is ``found: false``.
Nothing in here knows a world.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DESC_KEYS = ("summary", "desc", "description", "detail", "text", "note")
MAX_DESC = 240


def _T(lang: str) -> dict[str, Any]:
    from neonrp.prompts import strings

    return strings("inspect", lang)


def text_of(v: Any, lang: str = "") -> str:
    """A string, or a ``{lang: text}`` object (a narrowed run keeps one language) → text."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in (lang, "en", "zh", *v):
            x = v.get(k) if k else None
            if isinstance(x, str) and x.strip():
                return x.strip()
    return ""


def own_desc(e: Any, lang: str = "") -> str:
    """The thing's own description (the world's, or the one written for this run), "" when it has none."""
    for k in DESC_KEYS:
        t = text_of(e.props.get(k), lang) or text_of(e.props.get(f"{k}_i18n"), lang)
        if t and t != (e.name or e.id):
            return t
    return ""


def _j(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _first(lang: str, *vals: Any) -> str:
    for v in vals:
        t = text_of(v, lang)
        if t:
            return t
    return ""


def _resolve(reg: Any, target: str) -> str | None:
    t = str(target or "").strip()
    if not t:
        return None
    if t in reg.entries:
        return t
    hit = reg.resolve(t)
    if hit:
        return hit
    # a soul by its sid (the screen keys people by it)
    return next((e.id for e in reg.of_class("soul") if str(e.props.get("sid") or "") == t), None)


# ── people ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _person(root: Path, reg: Any, e: Any, lang: str) -> dict[str, Any] | None:
    from neonrp.core import people as P

    row = next((r for r in P.people(root, lang)["people"] if r["id"] == e.id), None)
    if row is None:  # not here, never met: the player does not know them
        return None
    met = bool(row.get("met")) and bool(row.get("name"))
    intro = appearance = ""
    if e.cls == "soul":
        d = P._soul_dirs(root).get(e.id)
        sj = _j(d / "soul.json") if d else {}
        prof = _j(d / "character" / "profile.json") if d else {}
        intro = _first(lang, sj.get("intro_i18n"), sj.get("intro"), prof.get("summary_i18n"), prof.get("summary"), e.props.get("summary"))
        appearance = _first(lang, prof.get("appearance_i18n"), prof.get("appearance"), sj.get("appearance_i18n"), sj.get("appearance"),
                            e.props.get("appearance"), e.props.get("look"), e.props.get("impression"))
    else:
        rec = P._npc_record(root, e)
        intro = _first(lang, rec.get("intro"), rec.get("summary"), e.props.get("summary"), rec.get("title"))
        appearance = _first(lang, rec.get("look"), rec.get("appearance"), e.props.get("look"), e.props.get("appearance"), e.props.get("impression"))
    out: dict[str, Any] = {"kind": "person", "id": e.id, "cls": e.cls, "name": str(row.get("name") or "") if met else "",
                           "role": str(row.get("role_label") or ""), "met": met, "here": bool(row.get("here")),
                           "companion": bool(row.get("companion")), "where": str(row.get("where") or ""),
                           "intro": intro if met else "", "appearance": appearance,
                           "portrait_slot": str(row.get("portrait_slot") or ""),
                           # nothing written about them that the player may see → an outward impression is written on open
                           "needs_desc": not appearance and not (intro if met else ""),
                           "desc_by": "inspect" if appearance and appearance == text_of(e.props.get("impression"), lang) else ("world" if appearance or intro else "")}
    if row.get("sid"):
        out["sid"] = row["sid"]
    if met and isinstance(row.get("relation"), dict) and row["relation"].get("label"):
        out["relation"] = str(row["relation"]["label"])
    if met and isinstance(row.get("trust"), dict):
        out["trust"] = row["trust"]
    if row.get("mood_label"):
        out["mood"] = str(row["mood_label"])
    return out


# ── things ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _source(root: Path, reg: Any, e: Any, T: dict[str, Any], branch: str = "main") -> str:
    """How the thing came to the player (the beat that gave it: picked here / given by someone / new), or where it lies."""
    from neonrp.core.orchestration_trace import read_turn_traces

    def nm(x: Any) -> str:
        ent = reg.entries.get(str(x or ""))
        return str(ent.name or "") if ent is not None else ""

    if reg.owner_of(e) == "player":
        try:
            trs = read_turn_traces(root, branch)
        except Exception:  # noqa: BLE001
            trs = []
        for tr in reversed(trs):
            ap = tr.get("apply") if isinstance(tr.get("apply"), dict) else {}
            for g in ap.get("gained") or []:
                if isinstance(g, dict) and g.get("id") == e.id and g.get("who") == "player":
                    how, fr = str(g.get("how") or ""), nm(g.get("from"))
                    if how == "given" and fr:
                        return str(T["src_given"]).format(name=fr)
                    if how == "picked" and fr:
                        return str(T["src_picked"]).format(place=fr)
                    return str(T["src_new"])
        return str(T["src_start"])
    owner = reg.owner_of(e)
    if owner and owner != "player" and nm(owner):
        return str(T["src_on"]).format(name=nm(owner))
    return str(T["src_at"]).format(place=nm(e.parent)) if nm(e.parent) else ""


def _thing(root: Path, reg: Any, e: Any, lang: str, branch: str = "main") -> dict[str, Any]:
    from neonrp.core.holdings import PLACE_CLASSES

    T = _T(lang)
    desc = own_desc(e, lang)
    if e.cls in PLACE_CLASSES:
        par = reg.entries.get(e.parent or "")
        return {"kind": "place", "id": e.id, "cls": e.cls, "name": str(e.name or ""), "desc": desc,
                "parent": str(par.name or "") if par is not None else "", "needs_desc": not desc,
                "desc_by": ("inspect" if e.props.get("summary_by") == "inspect" else "world") if desc else ""}
    return {"kind": "item", "id": e.id, "cls": e.cls, "name": str(e.name or ""), "desc": desc, "held": reg.owner_of(e) == "player",
            "desc_by": ("inspect" if e.props.get("summary_by") == "inspect" else "world") if desc else "",
            "needs_desc": not desc, "source": _source(root, reg, e, T, branch), "clue": bool(reg.is_clue(e))}


# ── the read ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def detail(root: Path, target: str, *, lang: str | None = None, reg: Any = None, branch: str = "main") -> dict[str, Any]:
    from neonrp.core import play_view
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    reg = reg if reg is not None else load_registry(root)
    eid = _resolve(reg, target)
    e = reg.entries.get(eid or "")
    if e is None or e.id == "player":
        return {"lang": lang, "found": False, "target": str(target or "")}
    if reg.is_person(e.cls):
        row = _person(root, reg, e, lang)
        return {"lang": lang, "found": True, **row} if row else {"lang": lang, "found": False, "target": str(target or "")}
    if e.id not in play_view.visible_entries(root, reg):
        return {"lang": lang, "found": False, "target": str(target or "")}
    return {"lang": lang, "found": True, **_thing(root, reg, e, lang, branch)}


def text(root: Path, reg: Any, e: Any, lang: str | None = None, *, write: bool = False, adapter: Any = None) -> str:
    """What 「仔细看看」 says about an entry in the prose (the ``[inspect …]`` action): a person's intro + appearance, a
    thing's / a place's description (the world's or the one written for this run); ``write`` = write it now when there is
    none (the action is the player's move, so this is the moment). The name when there is nothing."""
    from neonrp.core.output_lang import prompt_lang

    lang = lang or prompt_lang(root)
    try:
        d = describe(root, e.id, lang=lang, adapter=adapter) if write else detail(root, e.id, lang=lang, reg=reg)
    except Exception:  # noqa: BLE001
        logger.debug("inspect text fell back to the entry", exc_info=True)
        d = {}
    if d.get("found"):
        bits = [d.get("intro"), d.get("appearance")] if d.get("kind") == "person" else [d.get("desc")]
        out = "\n\n".join(str(x) for x in bits if x)
        if out:
            return out
    return own_desc(e, lang) or str(e.name or e.id)


# ── writing a description ─────────────────────────────────────────────────────────────────────────────────────────────

def _adapter(root: Path) -> Any:
    """The small judge model when one is configured, else the run's provider (the same one its turns use) — its own
    function so tests inject a stub."""
    from neonrp.core import system_one as s1

    if s1.LLM_ADAPTER_FACTORY is not None or s1.llm_judge_preset():
        try:
            return s1._llm_adapter()
        except Exception:  # noqa: BLE001
            logger.debug("small model unavailable; the run's provider writes it", exc_info=True)
    from neonrp.core.config import load_config, resolve_provider
    from neonrp.core.llm import get_adapter_from_config

    return get_adapter_from_config(resolve_provider(load_config(root), None, None))


def _world(root: Path, lang: str) -> tuple[str, str]:
    from neonrp.core.paths import get_data_dir_name

    card = (_j(Path(root) / get_data_dir_name(root) / "meta" / "template.json").get("card") or {})
    return text_of(card.get("title"), lang), text_of(card.get("pitch"), lang)


def _seen_in(root: Path, name: str, branch: str = "main") -> str:
    """The last prose the thing came up in (what the player read about it), cut short."""
    from neonrp.core.orchestration_trace import read_turn_traces

    try:
        trs = read_turn_traces(root, branch)
    except Exception:  # noqa: BLE001
        return ""
    for tr in reversed(trs):
        ap = tr.get("apply") if isinstance(tr.get("apply"), dict) else {}
        prose = str(ap.get("narration_plain") or "")
        i = prose.find(name) if name else -1
        if i >= 0:
            return prose[max(0, i - 160): i + 200].strip()
    return ""


def _clean(raw: str, name: str) -> str:
    t = re.sub(r"^```\w*|```$", "", str(raw or "").strip()).strip()
    if t.startswith(("{", "[")):  # a JSON answer (a stub provider's empty proposal, a model that misread the ask) is not prose
        return ""
    t = re.sub(r"^\s*(?:[-*•]|#+)\s*", "", t)
    t = " ".join(x.strip() for x in t.splitlines() if x.strip())
    t = t.strip("「」\"' ")
    if not t or t == name:
        return ""
    return t[:MAX_DESC]


def write_desc(root: Path, eid: str, desc: str, key: str = "summary") -> None:
    """Keep the written description in the run's entries overlay (read last by the registry; the template stays as it is).
    A thing / a place: ``summary``; a person: ``impression`` (what the player sees of them — never their summary)."""
    from neonrp.core.paths import get_data_dir_name

    p = Path(root) / get_data_dir_name(root) / "meta" / "entries.json"
    data = _j(p)
    cur = data.get(eid) if isinstance(data.get(eid), dict) else {}
    props = cur.get("props") if isinstance(cur.get("props"), dict) else {}
    data[eid] = {**cur, "props": {**props, key: desc, f"{key}_by": "inspect"}}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _side(root: Path, rec: dict[str, Any], branch: str = "main") -> None:
    try:
        p = Path(root) / ".neonrp" / "orchestration" / f"{(branch or 'main').replace('/', '-')}.side.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — the side file is for debugging; it never fails the call
        logger.debug("inspect side record skipped", exc_info=True)


def describe(root: Path, target: str, *, lang: str | None = None, adapter: Any = None, branch: str = "main") -> dict[str, Any]:
    """:func:`detail`, and for a person / a thing / a place with nothing written about it: write a few lines (once per
    run) and keep them. A person gets only what the player sees of them — the prompt carries no persona, no secrets."""
    from neonrp.core.output_lang import prompt_lang
    from neonrp.core.registry import load_registry

    lang = lang or prompt_lang(root)
    reg = load_registry(root)
    d = detail(root, target, lang=lang, reg=reg, branch=branch)
    if not d.get("found") or not d.get("needs_desc"):
        return d
    kind = str(d["kind"])
    e = reg.entries[d["id"]]
    T = _T(lang)
    none = str(T["none"])
    title, pitch = _world(root, lang)
    name = d.get("name") or d.get("role") or ""
    near = reg.entries.get(e.parent or "")
    at = str(near.name or "") if near is not None else ""
    names = [str(a) for a in sorted(e.aliases) if isinstance(a, str) and a != e.id and a != e.name][:4] if kind != "person" or d.get("name") else []
    sk, uk = {"item": ("system", "user"), "person": ("system_person", "user_person"), "place": ("system_place", "user_place")}[kind]
    where = (d.get("source") if kind == "item" else d.get("parent") if kind == "place" else at) or at
    user = str(T[uk]).format(name=name or none, aliases=T["sep"].join(names) or none, world=title or none, pitch=pitch or none,
                             where=where or none, role=d.get("role") or none, prose=(_seen_in(root, name, branch) if name else "") or none)
    t0 = time.monotonic()
    rec: dict[str, Any] = {"kind": "inspect", "what": kind, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "id": e.id}
    try:
        ad = adapter or _adapter(root)
        if hasattr(ad, "max_tokens"):
            try:
                ad.max_tokens = min(int(ad.max_tokens or 400), 400)  # a few lines; a cheap call
            except (TypeError, ValueError):
                pass
        out = ad.generate(str(T[sk]), user)
        err = getattr(out, "error", None)
        # the adapter looks for a proposal JSON and flags plain text as an error — plain text is what this asks for
        raw = str(getattr(out, "raw_output", "") or ("" if err else getattr(out, "proposal_text", "")) or "")
        rec["usage"] = dict(getattr(out, "usage", None) or {})
        if err and not raw.strip():
            rec["error"] = str(err)[:300]
    except Exception as exc:  # noqa: BLE001 — a model error answers with the name, never a crash
        raw = ""
        rec["error"] = str(exc)[:300]
    desc = _clean(raw, name)
    rec.update({"desc": desc, "ms": round((time.monotonic() - t0) * 1000, 1)})
    _side(root, rec, branch)
    if not desc:
        return {**d, "needs_desc": True, "error": rec.get("error") or "empty"}
    write_desc(root, e.id, desc, "impression" if kind == "person" else "summary")
    got = {"appearance": desc} if kind == "person" else {}
    return {**d, **got, "desc": desc, "desc_by": "inspect", "needs_desc": False, "generated": True}
