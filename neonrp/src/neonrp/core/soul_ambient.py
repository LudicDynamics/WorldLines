"""A character's simple world view — the background its free action (tick) happens in, outside any run (10-16:
「背景用一个简单的世界观,复刻它原来的世界背景或自动生成」). Not a world: no world agent, no registry — one small file
the character's tick reads, ``ambient/world.json``:

    {"schema": "worldlines.soul-ambient/1", "source": "replicated" | "generated" | "authored", "lang": "zh",
     "setting": "<a paragraph>",
     "places":  [{"id", "name", "summary"}]                       ≤ 6, the first one is home
     "routine": [{"at": "morning" | "afternoon" | "evening" | "night", "place": <id>, "doing": "<a line>"}]
     "people":  [{"name", "line"}]                                ≤ 4, whom it knows
     "clock":   "real"}                                           the player's wall clock (the only one for now)

Where it comes from (later wins, like the character's graph): its own folder · the template's override
``prompts/souls/<sid>/ambient/world.json`` (this world only). A world's character with neither gets one replicated from
its world on the fly (:func:`replicate`: the card's pitch, its town, the places around where it stands, the people its
persona says it knows — never the GM's truth, notes or secrets); a library character with none gets ``None`` until one
is generated (:func:`generate`, one model call) or written.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "worldlines.soul-ambient/1"
FILE = "ambient/world.json"
SLOTS = ("morning", "afternoon", "evening", "night")
MAX_PLACES, MAX_PEOPLE = 6, 4


def _read(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _s(v: Any, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def normal(d: Any, source: str = "authored") -> dict[str, Any]:
    """The file's shape, whatever came in (a model's answer, the bench's form): clipped, ids kept, unknown keys dropped."""
    d = d if isinstance(d, dict) else {}
    places = []
    for p in d.get("places") or []:
        if isinstance(p, dict) and (p.get("name") or p.get("id")):
            pid = re.sub(r"[^\w-]", "_", str(p.get("id") or p.get("name")))[:40]
            places.append({"id": pid, "name": _s(p.get("name") or pid, 40), "summary": _s(p.get("summary"), 200)})
    places = places[:MAX_PLACES]
    ids = {p["id"] for p in places}
    routine = [{"at": str(r.get("at")), "place": str(r.get("place") or ""), "doing": _s(r.get("doing"), 120)}
               for r in d.get("routine") or [] if isinstance(r, dict) and str(r.get("at")) in SLOTS]
    routine = [r for r in routine if not r["place"] or r["place"] in ids][:len(SLOTS) * 2]
    people = [{"name": _s(x.get("name"), 40), "line": _s(x.get("line"), 120)} for x in d.get("people") or [] if isinstance(x, dict) and x.get("name")][:MAX_PEOPLE]
    return {"schema": SCHEMA, "source": str(d.get("source") or source), "lang": str(d.get("lang") or "zh")[:5],
            "setting": _s(d.get("setting"), 600), "places": places, "routine": routine, "people": people, "clock": "real"}


def sources(c: dict[str, Any]) -> list[tuple[str, Path]]:
    t = c.get("t")
    out = [("soul", Path(c["dir"]) / FILE)]
    if t is not None:
        out.append(("template", Path(t.dir) / "prompts" / "souls" / c["sid"] / FILE))
    return out


def read(c: dict[str, Any], lang: str = "zh") -> dict[str, Any] | None:
    """The character's world view (``c`` = core/soul_chat.resolve): the template's, else its folder's, else replicated
    from its world (a world's character), else None (a library character nobody wrote one for)."""
    for _, p in reversed(sources(c)):
        d = _read(p)
        if isinstance(d, dict):
            return normal(d)
    return replicate(c, lang) if c.get("t") is not None else None


def _pick(v: Any, lang: str) -> str:
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("zh") or next(iter(v.values()), "") or "")
    return str(v or "")


def replicate(c: dict[str, Any], lang: str = "zh") -> dict[str, Any]:
    """Its world, made small: the card's pitch + its town's summary · home = where it stands in the world, then the
    places that connect to it, then the rest of that town · the people its persona knows (``known`` is not false).
    Only what a player may see: never ``game/lore/gm-truth.md`` / ``notes.md`` / ``game/secrets`` / its own secrets."""
    from neonrp.template import i18n, world_dir

    t = c["t"]
    wd = world_dir(t) or Path(t.dir) / "world"
    try:
        card = i18n.card(t, lang)
    except Exception:  # noqa: BLE001
        card = t.card
    rs = _read(Path(c.get("folder") or c["dir"]) / "run_state.json") or {}  # a taken character: its own (the snapshot, 10-20)
    loc = rs.get("location")
    loc = str(loc.get("id") if isinstance(loc, dict) else loc or "")
    town_id, _, here = loc.partition("/")
    town_dir = wd / "game" / "locations" / town_id if town_id else None
    town = _read(town_dir / "location.json") if town_dir else None
    rows: dict[str, dict[str, Any]] = {}
    if town_dir and town_dir.is_dir():
        for f in sorted(town_dir.glob("*/location.json")):
            d = _read(f)
            if isinstance(d, dict):
                rows[str(d.get("id") or f.parent.name)] = d
    order = [here] if here in rows else []
    order += [x for x in (rows.get(here) or {}).get("connections") or [] if x in rows and x not in order]
    order += [x for x in rows if x not in order]
    places = [{"id": pid, "name": _pick(rows[pid].get("name_i18n") or rows[pid].get("name"), lang) or pid,
               "summary": _pick(rows[pid].get("summary_i18n") or rows[pid].get("summary"), lang)} for pid in order[:MAX_PLACES]]
    routine = [{"at": s, "place": places[i % len(places)]["id"] if places else "", "doing": ""} for i, s in enumerate(SLOTS)]
    rel = _read(Path(c.get("folder") or c["dir"]) / "persona" / "relationships.json") or {}
    rel = rel.get("relationships", rel) if isinstance(rel, dict) else {}
    people = [{"name": str((v or {}).get("name") or k), "line": str((v or {}).get("disposition") or "")}
              for k, v in (rel.items() if isinstance(rel, dict) else []) if k not in ("sid",) and isinstance(v, dict) and v.get("known") is not False]
    setting = " ".join(x for x in (_pick(card.get("pitch"), lang), _pick((town or {}).get("summary_i18n") or (town or {}).get("summary"), lang)) if x)
    return normal({"source": "replicated", "lang": lang, "setting": setting, "places": places, "routine": routine, "people": people})


GEN_PROMPT = """You set up a small, everyday world for one character to live in between conversations with the player.
Read the character's own documents below and answer with ONE JSON object, nothing else:
{"setting": "<one paragraph: where and when this character lives>",
 "places": [{"id": "<short_snake_id>", "name": "<name>", "summary": "<one line>"}],   // 3-6 places, the first is home
 "routine": [{"at": "morning|afternoon|evening|night", "place": "<a place id>", "doing": "<one line>"}],   // one per slot
 "people": [{"name": "<name>", "line": "<who they are to the character>"}]}   // 0-4 people it knows
Write every text in the language "{lang}". Keep to what the documents say or plainly imply; no new secrets, no plot.
The character's documents are in the next message."""


def generate(c: dict[str, Any], lang: str = "zh", adapter: Any = None) -> dict[str, Any]:
    """One model call over the character's own documents (core/soul_chat's set) → a world view (``source: generated``).
    ValueError(why) when the model gives nothing usable."""
    from neonrp.core import soul_chat as C
    from neonrp.core.llm import Message

    docs = C._docs(Path(c["folder"]))
    try:
        out = (adapter or C._adapter()).chat([Message(role="system", content=GEN_PROMPT.replace("{lang}", lang)), Message(role="user", content=docs)])
    except Exception as exc:  # noqa: BLE001 — no model / transport: an answer, never a crash
        raise ValueError(str(exc)[:300]) from exc
    err = getattr(out, "error", None)
    if err:
        raise ValueError(str(err)[:300])
    raw = str(getattr(getattr(out, "message", None), "content", None) or "")
    from neonrp.core.json_repair import loads_repaired

    try:
        d = loads_repaired(raw[raw.find("{"): raw.rfind("}") + 1] if "{" in raw else raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"no JSON in the answer: {exc}") from exc
    w = normal({**(d if isinstance(d, dict) else {}), "source": "generated", "lang": lang})
    if not w["places"] and not w["setting"]:
        raise ValueError("the answer had no setting and no places")
    return w


def save(c: dict[str, Any], world: Any) -> dict[str, Any]:
    """A library character → its folder; a world's character → the template's override (author op
    ``set_soul_ambient``; a built-in template is read-only → PermissionError)."""
    w = normal(world, source=str((world or {}).get("source") or "authored") if isinstance(world, dict) else "authored")
    if c.get("t") is None:
        p = Path(c["dir"]) / FILE
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(w, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"ok": True, "to": "library", "path": str(p), "world": w}
    from neonrp.template import author

    if not author.writable(c["t"]):
        raise PermissionError(f"template {c['t'].id} is built in (read-only): copy it into your own templates first")
    out = author.apply_ops(c["t"], [{"op": "set_soul_ambient", "sid": c["sid"], "world": w}])
    if not out.get("ok"):
        raise ValueError("; ".join(str(x.get("why")) for x in out.get("refused") or []) or "refused")
    return {"ok": True, "to": "template", "id": c["t"].id, "world": w}
