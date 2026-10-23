"""Multilingual card helpers for world / character (soul) cards.

A card field can be either a plain string (backward-compatible — treated
as ``{source_lang: <that string>}``) or a locale map::

    {"en": "Elena", "zh": "艾琳娜", "ja": "エレナ", "ko": "엘레나"}

Callers resolve through :func:`card_field` which falls back to
``source_lang`` (and then to the first available locale) so no locale
ever renders empty.

This module is a pure-data leaf — no I/O, no LLM calls. Agentic fill
lives elsewhere (cast_agent / skill-authoring) and calls into the build
helpers here.
"""

from __future__ import annotations

# Canonical locale list for card i18n — matches the TUI locale set.
CARD_LOCALES: tuple[str, ...] = ("en", "zh", "ja", "ko")

# Locale → script preference for displaying proper names in a non-source
# locale. E.g. a zh-source card shown in ja should prefer the latin name
# over a Chinese name_local — the latin script is culturally neutral
# where the Chinese glyphs are jarring.
_SCRIPT_FALLBACK: dict[str, str] = {
    "ja": "en",   # Japanese UI → show latin, not Chinese
    "ko": "en",   # Korean UI → show latin, not Chinese
    "zh": "zh",   # Chinese UI → native OK
    "en": "en",
}


def card_field(
    field: str | dict[str, str] | None,
    locale: str,
    *,
    source_lang: str = "en",
) -> str:
    """Resolve a card field to the best available locale string.

    Order: exact ``locale`` → ``source_lang`` → first non-empty value →
    ``""``. Never returns ``None``.
    """
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if not isinstance(field, dict):
        return ""
    # 1. Exact locale match
    v = field.get(locale, "").strip()
    if v:
        return v
    # 2. Source-language fallback
    v = field.get(source_lang, "").strip()
    if v:
        return v
    # 3. Any available locale
    for k in CARD_LOCALES:
        v = field.get(k, "").strip()
        if v:
            return v
    return ""


def card_name_for_locale(
    name: str,
    name_local: str,
    locale: str,
    *,
    source_lang: str = "en",
    name_i18n: dict[str, str] | None = None,
) -> str:
    """Best-effort character/world name for a given UI locale.

    * If ``name_i18n`` has a locale entry → use it (transliteration).
    * If ``locale`` ≠ ``source_lang`` and the script-is-jarring heuristic
      triggers → prefer the latin ``name`` over ``name_local``.
    * Otherwise → ``name (name_local)`` as today.
    """
    if name_i18n:
        v = card_field(name_i18n, locale, source_lang=source_lang)
        if v:
            return v
    # Heuristic: non-source-locale, latin-default → show latin name only
    pref = _SCRIPT_FALLBACK.get(locale, source_lang)
    if pref == "en" and locale != source_lang:
        return name
    # Default: show name + name_local like today
    if name_local:
        return f"{name} ({name_local})"
    return name


def field_as_i18n(value: str | dict[str, str] | None) -> dict[str, str]:
    """Normalise a card field to the i18n dict form for storage.

    A plain string is left as-is on disk (back-compat); this returns the
    dict representation for in-memory use.
    """
    if value is None:
        return {}
    if isinstance(value, str):
        return {}  # caller falls back to bare string
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if isinstance(v, str) and v.strip()}
    return {}


def build_i18n_block(
    *,
    en: str = "",
    zh: str = "",
    ja: str = "",
    ko: str = "",
    source_lang: str = "en",
) -> dict[str, str]:
    """Build a compact i18n block, omitting empty values.

    If only the source_lang entry is non-empty, returns just a plain
    string (back-compat on-disk form).
    """
    block: dict[str, str] = {}
    if en.strip():
        block["en"] = en.strip()
    if zh.strip():
        block["zh"] = zh.strip()
    if ja.strip():
        block["ja"] = ja.strip()
    if ko.strip():
        block["ko"] = ko.strip()
    if not block:
        return {}
    # If only source_lang is present, return bare string for back-compat
    if len(block) == 1 and source_lang in block:
        return {source_lang: block[source_lang]}
    return block


def locale_to_source_lang(locale: str) -> str:
    """Map a UI locale to the conventional source language.

    zh → zh, ja → ja, ko → ko, everything else → en.
    This is used when a new card is authored in a given locale.
    """
    if locale in ("zh", "zh-cn", "zh-tw"):
        return "zh"
    if locale in ("ja", "ja-jp"):
        return "ja"
    if locale in ("ko", "ko-kr"):
        return "ko"
    return "en"
