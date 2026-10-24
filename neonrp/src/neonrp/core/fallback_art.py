"""Stand-in pictures when a person or an item has no art of its own (10-17: 没图的人显示问号不好看).

The screen never guesses: the engine reads what the world already wrote and names one picture —

    portrait_fallback   "f-child" · "f-young" · "f-adult" · "f-elder" · "m-…" (the same four) · "n-adult" (neutral)
    icon_fallback       "item-key" · "item-letter" · "item-book" · "item-weapon" · "item-potion" · "item-jewelry" ·
                        "item-tool" · "item-food" · "item-coin" · "item-clothing" · "item-container" · "item-generic"
    (ids = the asset repo's worlds/_shared/fallback/PROMPTS.md; a bust is "<id>-portrait")

Person: a ``portrait_fallback`` the world wrote itself wins, then an explicit ``gender`` / ``sex`` / ``pronoun`` field,
else the words (any of the four languages) — first the fields that describe the person (appearance / description /
title / role / tags), then the story ones (summary / intro), which often talk about someone else too; a kinship word
(女儿 · his daughter) counts half. Age = an ``age`` number (or a number in the text: 「21岁」「40歳」「17살」
「a 60-year-old」), else words (少女 · 中年 · old woman …). Nothing to go on for the gender = ``n-adult`` (neutral);
gender but no age = a young adult. Item: its name and category fields (``category`` / ``kind`` / ``type`` / ``tags``);
the head noun wins a tie (rightmost match: 「金色项链」 = jewel). No hit = the generic icon.

The words live in ``neonrp/schema/fallback_art.json`` — no world's words are written here. The pictures themselves are
the standard front end's (worldlines/ui/player/assets/fallback/), shipped with it, never in a world package.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

DATA = Path(__file__).resolve().parent.parent / "schema" / "fallback_art.json"


@lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _words(by_lang: dict[str, list[str]]) -> list[str]:
    return [w for ws in (by_lang or {}).values() for w in ws if isinstance(w, str) and w]


def _alt(w: str) -> str:
    # ASCII words match whole words only (he ≠ the · ring ≠ string · a hyphen joins: spice-witch ≠ witch); CJK / Hangul anywhere
    return r"(?<![A-Za-z-])" + re.escape(w) + r"(?![A-Za-z-])" if w.isascii() else re.escape(w)


@lru_cache(maxsize=8)
def _matcher(kind: str) -> tuple[re.Pattern[str], dict[str, str | None]]:
    """One alternation, longest word first: at each place the longest word wins and what it covered is not read again
    (彼女 ≠ 彼 · 老板娘 ≠ 老板); a strip word matches like any other and counts for nothing."""
    t = table()
    if kind.startswith("portrait."):
        P = t["portrait"]
        groups = P["gender"] if kind == "portrait.gender" else P["age"]
        strip = _words(P.get("strip") or {})
    else:
        groups, strip = t["item"]["words"], []
    group: dict[str, str | None] = {}
    for k, by_lang in groups.items():
        for w in _words(by_lang):
            group.setdefault(w.lower(), k)
    for w in strip:
        group.setdefault(w.lower(), None)
    words = sorted(group, key=lambda w: -len(w))
    return re.compile("|".join(_alt(w) for w in words), re.I), group


def _scan(text: str, kind: str) -> list[tuple[str, int]]:
    """(group, position) for every hit, the strip words taken out."""
    pat, group = _matcher(kind)
    return [(g, m.start()) for m in pat.finditer(text or "") if (g := group.get(m.group(0).lower()))]


def _flat(v: Any, out: list[str], depth: int = 0) -> None:
    if depth > 4 or v is None or isinstance(v, bool):
        return
    if isinstance(v, (str, int, float)):
        out.append(str(v))
    elif isinstance(v, dict):
        for x in v.values():
            _flat(x, out, depth + 1)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _flat(x, out, depth + 1)


def _text(srcs: Iterable[dict[str, Any]], keys: list[str]) -> str:
    out: list[str] = []
    for s in srcs:
        for k in keys:
            if k in s:
                _flat(s[k], out)
    return "\n".join(out)


def _band(n: float) -> str | None:
    for lo, hi, band in table()["portrait"]["age_bands"]:
        if lo <= n <= hi:
            return str(band)
    return None


def _age_number(text: str) -> str | None:
    for pat in table()["portrait"]["age_number_patterns"]:
        m = re.search(pat, text, re.I | re.M)
        if m:
            try:
                return _band(int(m.group(1)))
            except ValueError:
                continue
    return None


def _winner(hits: list[tuple[str, int]], order: list[str] | None = None) -> str | None:
    if not hits:
        return None
    score: dict[str, int] = {}
    for k, _ in hits:
        score[k] = score.get(k, 0) + 1
    top = max(score.values())
    best = [k for k, v in score.items() if v == top]
    if len(best) == 1:
        return best[0]
    if order:  # age: the more telling band wins a tie (a 「少女」 who is also 「孩子」 is a child)
        return next(k for k in order if k in best)
    return None


def _sex(hits: list[tuple[str, int]]) -> str | None:
    """f / m by weighted score (a kinship word — 女儿 · his daughter — counts less: it is usually somebody else)."""
    w = table()["portrait"]["gender_weight"]
    score = {"f": 0, "m": 0}
    for k, _ in hits:
        score[k[:1]] += int(w.get(k, 1))
    return None if score["f"] == score["m"] else ("f" if score["f"] > score["m"] else "m")


def gender(*srcs: dict[str, Any]) -> str | None:
    """"f" / "m" / None (unknown or mixed)."""
    P = table()["portrait"]
    srcs = tuple(s for s in srcs if isinstance(s, dict))
    explicit = _text(srcs, P["explicit_gender_keys"])
    if explicit.strip():
        g = _sex(_scan(explicit, "portrait.gender"))
        if g is None and len(explicit.strip()) <= 2:  # "F" / "M" / "W": a one-letter code is still a code
            g = {"f": "f", "w": "f", "m": "m"}.get(explicit.strip()[:1].lower())
        if g:
            return g
    for keys in P["text_tiers"]:
        g = _sex(_scan(_text(srcs, keys), "portrait.gender"))
        if g:
            return g
    return None


def age(*srcs: dict[str, Any]) -> str | None:
    """"child" / "young" / "adult" / "elder" / None."""
    P = table()["portrait"]
    srcs = tuple(s for s in srcs if isinstance(s, dict))
    for s in srcs:
        for k in P["explicit_age_keys"]:
            v = s.get(k)
            if isinstance(v, bool) or v is None or v == "":
                continue
            if isinstance(v, (int, float)):
                b = _band(v)
            else:
                b = _age_number(str(v)) or _winner(_scan(str(v), "portrait.age"), P["age_priority"])
            if b:
                return b
    texts = [_text(srcs, keys) for keys in P["text_tiers"]]
    for text in texts:
        b = _age_number(text)
        if b:
            return b
    for text in texts:
        b = _winner(_scan(text, "portrait.age"), P["age_priority"])
        if b:
            return b
    return None


def portrait(*srcs: dict[str, Any]) -> str:
    """The stand-in portrait id for a person described by ``srcs`` (soul.json, profile.json, entity props, npc row …)."""
    P = table()["portrait"]
    own = next((str(s[P["override_key"]]) for s in srcs if isinstance(s, dict) and s.get(P["override_key"])), "")
    if own in P["ids"]:  # the world picked one itself
        return own
    g = gender(*srcs)
    if g is None:
        return str(P["neutral"])
    return f"{g}-{age(*srcs) or P['default_age']}"


def icon(*srcs: dict[str, Any], name: str = "") -> str:
    """The stand-in icon id for an item: its category fields first (counted twice), then its name; the head noun
    (the rightmost hit) breaks a tie."""
    T = table()["item"]
    srcs = tuple(s for s in srcs if isinstance(s, dict))
    hits: list[tuple[str, int]] = []
    for k, _ in _scan(_text(srcs, T["category_keys"]), "item"):
        hits += [(k, -1), (k, -1)]
    nm = name or next((str(s.get("name")) for s in srcs if s.get("name")), "")
    hits += _scan(nm, "item")
    if not hits:
        return str(T["generic"])
    score: dict[str, int] = {}
    last: dict[str, int] = {}
    for k, pos in hits:
        score[k] = score.get(k, 0) + 1
        last[k] = max(last.get(k, -1), pos)
    best = max(score, key=lambda k: (score[k], last[k]))
    return str((T.get("alias") or {}).get(best, best))  # a class whose picture is not drawn yet shows as another one


def _rj(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def soul_dir(d: Path | None, *extra: dict[str, Any]) -> str:
    """A soul folder's stand-in: ``soul.json`` + ``character/profile.json`` (+ whatever the caller already has)."""
    if d is None:
        return portrait(*extra)
    return portrait(_rj(Path(d) / "soul.json"), _rj(Path(d) / "character" / "profile.json"), *extra)


def player(root: Path) -> str:
    """The player's stand-in: the world's ``player/profile.json`` + what the character builder wrote back (live values)."""
    from neonrp.core.paths import get_data_dir_name

    g = Path(root) / get_data_dir_name(root) / "player"
    card = _rj(g / "card.json")
    live = card.get("live") if isinstance(card.get("live"), dict) else {}
    vals = card.get("values") if isinstance(card.get("values"), dict) else {}
    return portrait(_rj(g / "profile.json"), vals, live)
