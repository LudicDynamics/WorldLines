"""The ``sheet`` seam for rpg (and the packs built on it, 10-14): the rule table names the player's numbers.

A row of ``rules.json`` ``attrs`` / ``skills`` (the pack's, layered under the world's ``game/rules/rules.json``)::

    "search": {"zh": "侦查", "en": "Search", "ja": "目星", "ko": "탐색", "base": 25,
               "desc": {"zh": "发现藏起来的东西、不对劲的细节。", "en": "…"}}

matches a sheet entry by its key or by any language's name (the sheet's keys stay as authored: ``skills: {侦查: 60}``)
→ ``label`` in the run's language, ``desc`` the row's line in it (else en, else zh), ``aliases`` every name it goes by.
An entry no row knows keeps its key as the label and an empty description.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neonrp.packs.rpg import data

LANGS = ("zh", "en", "ja", "ko")


def _names(key: str, row: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys([key, *(str(row[k]) for k in LANGS if row.get(k)), *(str(a) for a in row.get("aliases") or [])]))


def row_for(table: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
    n = str(name or "").strip().casefold()
    for key, row in (table or {}).items():
        if isinstance(row, dict) and n in {x.casefold() for x in _names(key, row)}:
            return key, row
    return None


def desc_of(row: dict[str, Any], lang: str) -> str:
    d = row.get("desc")
    if isinstance(d, dict):
        return str(d.get(lang) or d.get("en") or d.get("zh") or "")
    return str(d or "")


def name_rows(rows: list[dict[str, Any]], table: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        hit = row_for(table, str(r.get("key") or r.get("name") or ""))
        if hit is None:
            out.append(r)
            continue
        key, row = hit
        out.append({**r, "label": str(row.get(lang) or row.get("en") or r.get("label") or key), "desc": desc_of(row, lang) or r.get("desc") or "",
                    "id": key, "aliases": _names(key, row)})
    return out


def sheet(root: Path, reg: Any, sh: dict[str, Any], lang: str) -> dict[str, Any]:
    R = data.rules(root)
    return {**sh, "attrs": name_rows(sh.get("attrs") or [], R.get("attrs") or {}, lang),
            "skills": name_rows(sh.get("skills") or [], R.get("skills") or {}, lang)}
