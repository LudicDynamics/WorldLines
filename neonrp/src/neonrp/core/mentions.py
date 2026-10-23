"""The entities a beat's prose names, with where they sit in the text (10-14, the standard front end §5.5): a front end
marks exactly these as clickable instead of matching names itself (and hitting a same-named word).

    find(reg, text) -> [{id, cls, name, span: [start, end]}, …]     spans index ``text`` (Python str offsets = code points)

People (souls, NPCs), things and places by their names and aliases; the longest name wins where two overlap; a name the
registry gives to several entries picks the one here (where the player stands, or the player's own), and lists the
others as ``alt``. The player and the world itself are left out; so are names too short to be safe (one CJK character,
fewer than three Latin letters) and the bare ids the engine uses inside.
"""
from __future__ import annotations

import re
from typing import Any

SKIP_CLASSES = ("world", "level", "player")
MAX = 80


def _ok(name: str) -> bool:
    n = name.strip()
    if not n or n.startswith(("{{", "~")):
        return False
    latin = all(ord(c) < 0x2E80 for c in n)
    return len(n) >= (3 if latin else 2)


def _names(reg: Any) -> dict[str, list[str]]:
    """name → [entry ids] (a name several entries share keeps them all)."""
    out: dict[str, list[str]] = {}
    for e in reg.entries.values():
        if e.id == "player" or str(e.id).startswith("~") or e.cls in SKIP_CLASSES:
            continue
        cands = {str(e.name or "")} | {str(a) for a in e.aliases if isinstance(a, str)}
        for n in cands:
            n = n.strip()
            if n == e.id and ("/" in n or any(ch.isdigit() for ch in n)):  # T001/hall · I701 · si-xiacheng01: engine ids, not prose
                continue
            if _ok(n):
                ids = out.setdefault(n, [])
                if e.id not in ids:
                    ids.append(e.id)
    return out


def _pick(reg: Any, ids: list[str]) -> str:
    here = reg.player_location
    for eid in ids:
        e = reg.entries.get(eid)
        if e is not None and here and (e.parent == here or eid == here):
            return eid
    for eid in ids:
        e = reg.entries.get(eid)
        if e is not None and reg.owner_of(e) == "player":
            return eid
    return ids[0]


def find(reg: Any, text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    names = _names(reg)
    if not names:
        return []
    order = sorted(names, key=len, reverse=True)
    rx = re.compile("|".join(
        (rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])" if all(ord(c) < 0x2E80 for c in n) else re.escape(n)) for n in order),
        re.IGNORECASE)
    folded = {n.casefold(): n for n in order}
    out: list[dict[str, Any]] = []
    for m in rx.finditer(text):
        key = folded.get(m.group(0).casefold())
        if key is None:
            continue
        ids = names[key]
        eid = _pick(reg, ids)
        e = reg.entries.get(eid)
        rec = {"id": eid, "cls": e.cls if e is not None else None, "name": m.group(0), "span": [m.start(), m.end()]}
        if len(ids) > 1:
            rec["alt"] = [x for x in ids if x != eid]
        out.append(rec)
        if len(out) >= MAX:
            break
    return out
