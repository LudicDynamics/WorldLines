"""Display words for a world's enum keys (10-15, the standard front end §5.16): ``status.mood`` (``yearning``),
``relationships.*.disposition`` (``lover``), an NPC's ``role`` (``gate-guard``) are keys the world writes in English —
the screen shows the word in this run's language.

The world names them in ``game/meta/labels.json`` (the language layer ``i18n/<lang>/`` overrides it like any file)::

    {"mood": {"yearning": {"zh": "思念", "en": "yearning", "ja": "憧れ", "ko": "그리움"}},
     "disposition": {"lover": {"zh": "恋人", …}},
     "role": {"gate-guard": {"zh": "城门守卫", …}}}

A value may also be a plain string (already in the run's language). No row: an English run shows the key as words
(``blank_then_violent`` → 「blank then violent」); any other run gets "" (an ASCII key is not a word for a zh / ja / ko
player — the screen shows nothing rather than a code).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

KINDS = ("mood", "disposition", "role", "attitude")


def table(root: Path) -> dict[str, Any]:
    from neonrp.core.paths import get_data_dir_name

    try:
        d = json.loads((Path(root) / get_data_dir_name(root) / "meta" / "labels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def label(root: Path, kind: str, key: Any, lang: str, tbl: dict[str, Any] | None = None) -> str:
    k = str(key or "").strip()
    if not k:
        return ""
    row = ((tbl if tbl is not None else table(root)).get(kind) or {}).get(k)
    if isinstance(row, str) and row.strip():
        return row.strip()
    if isinstance(row, dict):
        v = row.get(lang) or (row.get("en") if lang == "en" else None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if not k.isascii():
        return k  # the world already wrote a word, not a code
    return re.sub(r"[_\-]+", " ", k).strip() if lang == "en" else ""
