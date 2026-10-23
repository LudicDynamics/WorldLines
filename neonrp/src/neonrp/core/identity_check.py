"""Ledger invariants about identity — cheap, no model: run after a beat lands,
in tests and in benchmarks, so a ledger quietly written wrong shows up at once.

* someone's things: no two of the same class with the same name on one owner; every owner is a live entry
* every person (player, characters, people of the world) is found by its id and by each of its own spellings
"""
from __future__ import annotations

from neonrp.core.registry import Registry, _norm


def problems(reg: Registry) -> list[str]:
    out: list[str] = []
    seen: dict[tuple[str, str, str], str] = {}
    for e in reg.entries.values():
        if e.id.startswith("~pending:") or reg.is_person(e.cls):
            continue
        spec = reg.classes.get(e.cls)
        if spec is None or not (spec.effect or spec.list_store):
            continue
        owner = reg.owner_of(e)
        if owner is None or owner not in reg.entries:
            out.append(f"orphan: {e.cls} {e.id} ({e.name}) belongs to {owner!r}, which is not an entry")
            continue
        key = (owner, e.cls, _norm(e.name))
        if key in seen:
            out.append(f"duplicate: {e.cls} {e.name!r} twice on {owner} ({seen[key]}, {e.id})")
        seen[key] = e.id
    for e in reg.entries.values():
        if not reg.is_person(e.cls):
            continue
        if reg.lookup(e.id).ids != [e.id]:
            out.append(f"id: {e.id} does not find itself alone ({reg.lookup(e.id).ids})")
        for a in {e.name, *e.aliases}:
            if a and e.id not in reg.lookup(str(a)).ids:
                out.append(f"spelling: {a!r} does not find {e.id}")
    return out
