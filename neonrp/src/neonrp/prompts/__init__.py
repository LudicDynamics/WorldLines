"""The engine's prompt texts, one file per unit and language.

Two shapes, both picked by the run's language (``output_lang.prompt_lang``) with the fallback lang → en → zh:

- ``<unit>.<lang>.md`` — a whole prompt (a system prompt, a rule paragraph). ``text(unit, lang)``; ``fill`` replaces the
  ``{name}`` placeholders it is given and nothing else (other braces in the text stay as they are).
- ``<table>.<lang>.json`` — the short strings of one module (headings, one-liners). ``strings(table, lang)`` merges
  key by key, so a language that misses a key still gets the en (then zh) one.

Code keeps only the assembly; the words live here, so a translator touches files, not Python. A unit's zh file is the
original the others are translated from. The guard test (tests/test_prompt_i18n.py) checks every unit has all four.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LANGS: tuple[str, ...] = ("zh", "en", "ja", "ko")
_DIR = Path(__file__).resolve().parent


def _chain(lang: str) -> tuple[str, ...]:
    out = [lang] if lang in LANGS else []
    for x in ("en", "zh"):
        if x not in out:
            out.append(x)
    return tuple(out)


def _private() -> Path | None:
    """The private layer's prompts (``neonrp_private/prompts``, 10-08) — laid over the engine's public ones."""
    from neonrp.core.paths import private_dir

    return private_dir("prompts")


def _read_md(unit: str, lang: str) -> str | None:
    """The engine's text of a unit: the private layer's file when it has one, else the engine's public one."""
    priv = _private()
    if priv is not None:
        t = _read_md_at(priv, unit, lang)
        if t is not None:
            return t
    return _read_md_at(_DIR, unit, lang)


def _read_json(table: str, lang: str) -> dict[str, Any]:
    """A table: the engine's public one with the private layer's keys over it (key by key)."""
    priv = _private()
    return {**_read_json_at(_DIR, table, lang), **(_read_json_at(priv, table, lang) if priv is not None else {})}


@lru_cache(maxsize=None)
def _read_md_at(base: Path, unit: str, lang: str) -> str | None:
    try:
        t = (base / f"{unit}.{lang}.md").read_text(encoding="utf-8")
    except OSError:
        return None
    return t[:-1] if t.endswith("\n") else t  # the file's own last newline is not part of the text


@lru_cache(maxsize=None)
def _read_json_at(base: Path, table: str, lang: str) -> dict[str, Any]:
    try:
        d = json.loads((base / f"{table}.{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _pack_prompts(root: Path | None) -> list[Path]:
    """The world's pack's own prompt folder (``packs/<name>/prompts``) — a pack layer over the engine's units (10-05:
    pct swaps the check grammar of the planning prompt). Only the units a pack ships there are overridden."""
    if root is None:
        return []
    try:
        from neonrp import packs

        head = str(packs.template_of(Path(root)) or "").split("+", 1)[0].strip()
    except Exception:  # noqa: BLE001
        return []
    if not head or "/" in head or ":" in head:
        return []
    from neonrp.core.paths import private_dir

    priv = private_dir("packs")  # 10-08: the private layer's pack prompts first
    cands = ([priv / head / "prompts"] if priv is not None else []) + [Path(packs.__file__).resolve().parent / head / "prompts"]
    return [d for d in cands if d.is_dir()]


def _run_prompts(root: Path | None) -> Path | None:
    """The run's own prompt folder (``game/meta/prompts``): the template's overrides of engine units, copied in at build
    (``<template>/prompts/engine/<unit>.<lang>.md``; R3, 10-06) — the top layer, so the override travels with the game."""
    if root is None:
        return None
    try:
        from neonrp.core.paths import get_data_dir_name

        d = Path(root) / get_data_dir_name(Path(root)) / "meta" / "prompts"
    except Exception:  # noqa: BLE001
        return None
    return d if d.is_dir() else None


def text(unit: str, lang: str, root: Path | None = None) -> str:
    """The whole text of a unit in ``lang`` (→ en → zh). With a run ``root`` the layers are: the run's own
    (``game/meta/prompts``, from the template) → the world's pack's (private layer's, then ``packs/<pack>/prompts``) →
    the engine's (private layer's, then public); the first
    that has the unit (in the language chain) wins. KeyError when the unit does not exist at all."""
    run = _run_prompts(root)
    layers = ([run] if run is not None else []) + _pack_prompts(root)
    for lg in _chain(lang):  # the language first: a template's zh override never beats the engine's own ja
        for d in layers:
            f = d / f"{unit}.{lg}.md"
            if f.is_file():
                t = f.read_text(encoding="utf-8")
                return t[:-1] if t.endswith("\n") else t
        t = _read_md(unit, lg)
        if t is not None:
            return t
    raise KeyError(f"prompt unit {unit!r} not found")


def fill(unit: str, lang: str, **values: Any) -> str:
    """``text`` with ``{name}`` replaced for each given name (only those: literal braces elsewhere are kept)."""
    t = text(unit, lang)
    for k, v in values.items():
        t = t.replace("{" + k + "}", str(v))
    return t


def strings(table: str, lang: str) -> dict[str, Any]:
    """The table's strings in ``lang``, key by key falling back to en then zh."""
    out: dict[str, Any] = {}
    for lg in reversed(_chain(lang)):
        out.update(_read_json(table, lg))
    if not out:
        raise KeyError(f"string table {table!r} not found")
    return out


def by_lang(table: str, key: str) -> dict[str, Any]:
    """{lang: value} of one entry of a table, for every language (each falling back lang → en → zh) — the drop-in for
    a module's old ``{"zh": …, "en": …}`` dict, so ``D[lang]`` never misses a language."""
    return {lg: strings(table, lg)[key] for lg in LANGS}


def inner_lang(table: str, key: str) -> dict[str, dict[str, Any]]:
    """{name: {lang: value}} — the drop-in for an old ``{"name": {"zh": …, "en": …}}`` dict."""
    per = {lg: strings(table, lg)[key] for lg in LANGS}
    return {name: {lg: per[lg][name] for lg in LANGS if name in per[lg]} for name in per["zh"]}


def md_by_lang(unit: str) -> dict[str, str]:
    """{lang: text} of a whole-text unit, for every language."""
    return {lg: text(unit, lg) for lg in LANGS}


def units() -> dict[str, dict[str, set[str]]]:
    """{"md" | "json": {unit: {langs present}}} — what the guard test checks."""
    out: dict[str, dict[str, set[str]]] = {"md": {}, "json": {}}
    for p in _DIR.iterdir():
        parts = p.name.rsplit(".", 2)
        if len(parts) == 3 and parts[2] in ("md", "json") and parts[1] in LANGS:
            out[parts[2]].setdefault(parts[0], set()).add(parts[1])
    return out
