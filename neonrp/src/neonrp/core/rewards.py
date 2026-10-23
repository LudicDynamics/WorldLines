"""World rewards (10-18, niko 「都得做,同步做」): what a world hands the player when a condition holds — declared as data in
the template (``template.json`` ``rewards``; the engine names no world's things), allowed by the play contract, and kept
in the player's record on the launcher's side (core/player_data ``cards``, ``~/.worldlines/player-data``).

    "rewards": [{"id": "lamp", "kind": "card", "title": {"zh": "…", "en": "…", "ja": "…", "ko": "…"}, "desc": {…},
                 "rarity": "common" | "rare" | "epic", "when": "ending:E01" | ["flag:x", "stage:P01:2"],
                 "image": "assets/reward-lamp.webp" | "slot": "<another asset slot, e.g. item.icon:I805 · stage.cg:P01.3>"}]

- ``when``: the achievements' conditions (core/achievements ``WHEN_HELP``); a list = every one of them holds
- ``kind``: ``card`` = the Hub's 收集卡片. Open schema: any other kind is kept as written and shown as a card (lint warns)
- the contract: ``"rewards": {"player": [..., "cards"]}`` lets a world hand cards out; a contract without ``cards``
  hands none out (lint warns); no contract = allowed. A Free-Zone template (``zone: open``) hands none out
  (PLATFORM-PLAY-RULES-1015 §1: 先上后管,不发奖励)
- the picture: the reward's own slot ``reward:<id>`` (filled in the asset workbench like any other) or ``slot`` = a
  picture the template already has. At the moment it is earned the picture is copied beside the player's record, so a
  card is never taken back — not when the author drops it, not when the template is gone
- a new version: each card keeps the template version it was earned under; when the author ships another and the card
  is still there, the Hub offers to pull its new face (:func:`refresh`; a character's persona the same way, its memory
  stays)

    event  reward.granted {turn, id, kind, title, desc, rarity, image?}            (/engine/beats)
    GET  /api/v1/local/player-data          cards: [{…face in the asked language, image (url), upd, gone}]
    POST /api/v1/local/player-data/refresh  {kind: cards | characters, world, id|sid}
    GET  /api/v1/local/player-data/card?world=&id=   the kept picture
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

KINDS = ("card",)
RARITY = ("common", "rare", "epic")
CONTRACT_NAME = "cards"  # the name in a contract's rewards.player that lets a world hand cards out
_STORE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def conds(when: Any) -> list[str]:
    return [str(w) for w in when] if isinstance(when, list) else ([str(when)] if when else [])


def pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("en") or v.get("zh") or next(iter(v.values()), ""))
    return str(v or "")


# ── the template side (lint) ─────────────────────────────────────────────────

def validate(rows: Any, *, endings: set[str] | None = None) -> list[tuple[str, str]]:
    """(level, problem) for a template's ``rewards``: a row the engine cannot record blocks; the rest only warn."""
    from neonrp.core import achievements as A

    if rows is None:
        return []
    if not isinstance(rows, list):
        return [("block", "rewards must be a list of {id, kind?, title, desc?, rarity?, when, image? | slot?}")]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, r in enumerate(rows):
        w = f"rewards[{i}]"
        if not isinstance(r, dict) or not str(r.get("id") or "").strip():
            out.append(("block", f"{w} needs an id"))
            continue
        if r["id"] in seen:
            out.append(("block", f"{w}.id {r['id']!r} is listed twice"))
        seen.add(str(r["id"]))
        if not r.get("title"):
            out.append(("warn", f"{w} has no title (the card shows its id)"))
        kind = str(r.get("kind") or "card")
        if kind not in KINDS:
            out.append(("warn", f"{w}.kind {kind!r} is not one the Hub knows ({', '.join(KINDS)}); it is kept and shown as a card"))
        if r.get("rarity") is not None and r["rarity"] not in RARITY:
            out.append(("warn", f"{w}.rarity must be one of {', '.join(RARITY)} (shown as common)"))
        cs = conds(r.get("when"))
        if not cs or not all(A.when_ok(c) for c in cs):
            out.append(("warn", f"{w}.when must be one of {A.WHEN_HELP} (or a list of them) — never handed out as it is"))
        for c in cs:
            if endings is not None and c.startswith("ending:") and c[7:] not in endings:
                out.append(("warn", f"{w}.when names ending {c[7:]!r}, which no plot has"))
        if r.get("image") and r.get("slot"):
            out.append(("warn", f"{w} has both image and slot; slot wins"))
    return out


def lint(t: Any) -> list[tuple[str, str]]:
    """The template lint's half: the rows, their pictures, and whether the contract / zone lets them out."""
    rows = t.data.get("rewards")
    if rows is None:
        return []
    endings: set[str] = set()
    for rel in t.plots:
        try:
            pj = json.loads((t.dir / rel / "plot.json").read_text(encoding="utf-8"))
            endings |= {str(k) for k in (pj.get("endings") or {})}
        except (OSError, ValueError, AttributeError):
            pass
    out = validate(rows, endings=endings)
    if not isinstance(rows, list):
        return out
    for i, r in enumerate(rows):
        if isinstance(r, dict) and r.get("image") and not r.get("slot") and not (t.dir / str(r["image"])).is_file():
            out.append(("warn", f"rewards[{i}].image {r['image']!r} is not in the template (the card shows a plain face)"))
    if rows and t.zone == "open":
        out.append(("warn", "a Free-Zone template hands no rewards out (PLATFORM-PLAY-RULES §1)"))
    if rows and t.play_contract:
        from neonrp.template import contract as C

        try:
            c = C.load(t.play_contract)
        except C.ContractError:
            return out  # contract.unknown blocks elsewhere
        if not allows(c):
            out.append(("warn", f"the play contract {t.play_contract} does not hand out {CONTRACT_NAME!r} — these rewards stay unearned"))
    return out


def allows(c: dict[str, Any] | None) -> bool:
    """Whether a contract lets a world hand cards out (no contract = yes)."""
    if c is None:
        return True
    return CONTRACT_NAME in [str(x) for x in (((c.get("rewards") or {}).get("player")) or [])]


# ── the run side ─────────────────────────────────────────────────────────────

def _meta(root: Path) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    try:
        d = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def store_template(world: str) -> Any:
    """The template ``world`` names in the template store now (None when it is gone)."""
    try:
        from neonrp import template as TP

        d = TP.discover().get(world)
        return TP.load(d) if d else None
    except Exception:  # noqa: BLE001 — a template that does not load is as good as gone
        return None


def _store_rows(world: str) -> list[dict[str, Any]]:
    """The template's rewards as it is in the store now (cached on its template.json's mtime)."""
    t = store_template(world)
    if t is None:
        return []
    f = t.dir / "template.json"
    mt = f.stat().st_mtime if f.is_file() else 0.0
    hit = _STORE.get(world)
    if hit is None or hit[0] != mt:
        rows = t.data.get("rewards")
        hit = (mt, [r for r in rows if isinstance(r, dict) and r.get("id")] if isinstance(rows, list) else [])
        _STORE[world] = hit
    return hit[1]


def declared(root: Path) -> list[dict[str, Any]]:
    """The rewards this run can hand out: read off its template in the store (not copied into the run — a run holds
    one language, a card keeps all four for the Hub)."""
    from neonrp.core import player_data

    return _store_rows(player_data.world_of(root))


def allowed(root: Path) -> bool:
    from neonrp.template import contract as C

    return _meta(root).get("zone") != "open" and allows(C.run_contract(root))


def _picture(world: str, r: dict[str, Any], dest_dir: Path) -> str:
    """Copy the reward's picture beside the player's record; the kept file's name ("" when there is none)."""
    t = store_template(world)
    if t is None:
        return ""
    from neonrp import template as TP

    try:
        src = TP.slot_file(t, str(r.get("slot") or f"reward:{r['id']}"))
    except Exception:  # noqa: BLE001 — a slot that does not resolve = no picture
        src = None
    if src is None or not Path(src).is_file():
        return ""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(r["id"]))
    name = f"{safe}{Path(src).suffix.lower()}"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest_dir / name)
    except OSError:
        return ""
    return name


def card_dir(world: str) -> Path:
    from neonrp.core import player_data
    from neonrp.core.soul_chat import _safe

    return player_data.player_dir() / "cards" / _safe(world)


def _stamp() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _record(root: Path | None, world: str, r: dict[str, Any], version: str, source: str) -> dict[str, Any]:
    image = _picture(world, r, card_dir(world))
    return {"id": str(r["id"]), "world": world, "kind": str(r.get("kind") or "card"), "title": r.get("title") or str(r["id"]),
            "desc": r.get("desc") or "", "rarity": r.get("rarity") if r.get("rarity") in RARITY else "common",
            "image": image, **({"image_slot": str(r.get("slot") or f"reward:{r['id']}")} if image else {}), "version": version,
            **({"run": Path(root).name} if root is not None else {}), "source": source}


def face(rec: dict[str, Any], lang: str) -> dict[str, Any]:
    """A kept card in one language, for a screen."""
    from urllib.parse import quote

    return {"id": rec.get("id"), "world": rec.get("world"), "kind": rec.get("kind") or "card", "title": pick(rec.get("title"), lang),
            "desc": pick(rec.get("desc"), lang), "rarity": rec.get("rarity") or "common",
            "image": (f"/api/v1/local/player-data/card?world={quote(str(rec.get('world') or ''))}&id={quote(str(rec.get('id') or ''))}"
                      if rec.get("image") else None), "version": rec.get("version") or "", "at": rec.get("at")}


def after_apply(root: Path, reg: Any, res: Any) -> list[dict[str, Any]]:
    """After a beat landed: the rewards whose every condition holds now go into the player's record (once each)."""
    rows = declared(root)
    if not rows or not allowed(root):
        return []
    from neonrp.core import achievements as A
    from neonrp.core import player_data
    from neonrp.core.output_lang import prompt_lang

    ended = str((res.ended or {}).get("id") or "") if isinstance(getattr(res, "ended", None), dict) else ""
    total = None
    if any(c.startswith("milestone:") for r in rows for c in conds(r.get("when"))):
        from neonrp.core import milestones as _ms

        total = len(_ms.listing(root)["milestones"])
    ctx = A.context(root, reg, ended=ended or None, milestones=total, run_end=bool(getattr(res, "settled", None)))
    world, version, lang = player_data.world_of(root), player_data.version_of(root), prompt_lang(root)
    have = {c.get("id") for c in player_data.read()["cards"] if c.get("world") == world}
    out = []
    for r in rows:
        cs = conds(r.get("when"))
        if str(r["id"]) in have or not cs or not all(A.when_ok(c) and A.holds(c, ctx) for c in cs):
            continue
        rec = _record(root, world, r, version, f"turn:{getattr(res, 'turn', 0)}")
        if player_data.add_card(rec):
            out.append({"turn": getattr(res, "turn", None), **{k: v for k, v in face(rec, lang).items() if k != "at"}})
    if getattr(res, "settled", None):
        _note_settlement(root, res)
    return out


def _note_settlement(root: Path, res: Any) -> None:
    """The run settled this beat: its settlement lists the cards this run earned (``rewards.player.cards``)."""
    from neonrp.core import player_data
    from neonrp.core import settlement as S

    world = player_data.world_of(root)
    ids = [c.get("id") for c in player_data.read()["cards"] if c.get("world") == world and c.get("run") == Path(root).name]
    p = S._meta(root) / "settlement.json"
    d = S._read(p, None)
    if not isinstance(d, dict):
        return
    d.setdefault("rewards", {}).setdefault("player", {})[CONTRACT_NAME] = ids
    S._write(p, d)
    if isinstance(res.settled, dict):
        res.settled.setdefault("rewards", {}).setdefault("player", {})[CONTRACT_NAME] = ids


# ── the player's side (the Hub) ──────────────────────────────────────────────

def listing(lang: str) -> dict[str, list[dict[str, Any]]]:
    """Every kept card in ``lang`` with ``upd`` (the author shipped a new version that still has it) and ``gone`` (the
    template no longer lists it — still kept); every gained character's ``upd`` the same way."""
    from neonrp.core import player_data

    pd = player_data.read()
    vers: dict[str, str | None] = {}

    def now(world: str) -> str | None:
        if world not in vers:
            t = store_template(world)
            vers[world] = t.version if t is not None else None
        return vers[world]

    cards = []
    for c in pd["cards"]:
        w, v = str(c.get("world") or ""), now(str(c.get("world") or ""))
        there = any(str(r.get("id")) == str(c.get("id")) for r in _store_rows(w)) if v is not None else False
        cards.append({**face(c, lang), "upd": bool(there and v and v != (c.get("version") or "")), "gone": not there})
    chars = []
    from neonrp.core import soul_update

    for c in pd["characters"]:  # a character with its own snapshot: the author changed something since the last decision
        try:
            upd = soul_update.has_update(str(c.get("world") or ""), str(c.get("sid") or ""))
        except Exception:  # noqa: BLE001
            upd = False
        chars.append({**c, "upd": bool(upd)})
    return {"cards": cards, "characters": chars}


def refresh(kind: str, world: str, cid: str) -> dict[str, Any]:
    """Pull the author's new version of a kept card (its face and picture) or a gained character (its persona; the
    memory from the run it came from stays). Nothing is taken away: a card the author dropped stays as it was."""
    from neonrp.core import player_data

    t = store_template(world)
    if t is None:
        return {"ok": False, "error": "no_template"}
    if kind == "cards":
        r = next((x for x in _store_rows(world) if str(x.get("id")) == cid), None)
        if r is None:
            return {"ok": False, "error": "gone"}
        rec = _record(None, world, r, t.version, "")
        ok = player_data.update("cards", {"id": cid, "world": world},
                                {k: rec[k] for k in ("kind", "title", "desc", "rarity", "version")} | ({"image": rec["image"]} if rec["image"] else {})
                                | ({"image_slot": rec["image_slot"]} if rec.get("image_slot") else {}) | {"updated": _stamp()})
        return {"ok": ok, **({} if ok else {"error": "not_collected"})}
    if kind == "characters":  # 10-20: the player chooses item by item (core/soul_update); this = 「all as suggested」
        from neonrp.core import soul_update

        try:
            r = soul_update.apply(world, cid, all_="defaults")
        except soul_update.UpdateError as e:
            if e.code != "not_collected" or not any(c.get("sid") == cid and c.get("world") == world for c in player_data.read()["characters"]):
                return {"ok": False, "error": e.code}
            # gained without a folder of its own (a collect rule, as written): it reads its author's version anyway
            ok = player_data.update("characters", {"sid": cid, "world": world}, {"version": t.version, "updated": _stamp()})
            return {"ok": ok}
        return {"ok": True, **{k: r[k] for k in ("update", "took", "kept", "version")}}
    return {"ok": False, "error": "bad_kind"}


