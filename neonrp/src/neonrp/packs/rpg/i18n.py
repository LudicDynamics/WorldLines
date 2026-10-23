"""rpg sentences in zh / en / ja (templates ship in several languages). ``t(root, key, **fields)`` picks
the world's language (core.adv.world_lang) and falls back to zh. Rule tables carry their own i18n (see data.py)."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from neonrp import prompts as _prompts

S: dict[str, dict[str, str]] = _prompts.inner_lang("rpg_i18n", "S")


def lang_of(root: Path | None) -> str:
    if root is None:
        return "zh"
    try:
        from neonrp.core.output_lang import prompt_lang

        return prompt_lang(root)
    except Exception:  # noqa: BLE001
        return "zh"


def t(root: Path | None, key: str, /, **kw: Any) -> str:
    row = S.get(key) or {}
    lang = lang_of(root)
    tmpl = row.get(lang) or row.get("zh") or key
    try:
        return tmpl.format(**kw)
    except (KeyError, IndexError, ValueError):
        return tmpl
