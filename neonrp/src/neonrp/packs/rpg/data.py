"""rpg rule tables as data: pack defaults in ``packs/rpg/data/*.json``, a world overrides key by key in
``game/rules/<table>.json`` (and, for older worlds, ``world_map.json`` ``travel.hazards`` / ``foes``). Werewolf / 海龟汤
reuse the same gate + layer machinery with their own tables; nothing in the engine knows these keys."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

_DIR = Path(__file__).resolve().parent / "data"


def _read(p: Path) -> dict[str, Any]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (over or {}).items():
        if k.startswith("_"):
            continue
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _pack_dir(root: Path) -> Path | None:
    """A pack built on rpg (pct …) ships its own tables in ``packs/<name>/data/`` — layered over rpg's (10-05)."""
    try:
        from neonrp.packs import template_of

        head = str(template_of(root) or "").split("+", 1)[0].strip()
    except Exception:  # noqa: BLE001
        return None
    if not head or head == "rpg" or "/" in head or ":" in head:
        return None
    d = _DIR.parent.parent / head / "data"
    return d if d.is_dir() else None


def table(root: Path | None, name: str) -> dict[str, Any]:
    """The pack's table ``name`` with the world's overrides applied: rpg's defaults < the world's pack (if it is built on
    rpg and ships its own ``data/<name>.json``) < the world's ``game/rules/<name>.json``."""
    t = {k: v for k, v in _read(_DIR / f"{name}.json").items() if not k.startswith("_")}
    if root is None:
        return t
    pd = _pack_dir(root)
    if pd is not None:
        t = _merge(t, _read(pd / f"{name}.json"))
    g = root / get_data_dir_name(root)
    wm = _read(g / "world" / "world_map.json")
    legacy = {"hazards": (wm.get("travel") or {}).get("hazards"), "foes": wm.get("foes"),
              "rules": ({"travel_per_day": (wm.get("travel") or {}).get("per_day")} if (wm.get("travel") or {}).get("per_day") else None)}.get(name)
    if isinstance(legacy, dict):
        t = _merge(t, _normalize_legacy(name, legacy))
    return _merge(t, _read(g / "rules" / f"{name}.json"))


def _normalize_legacy(name: str, d: dict[str, Any]) -> dict[str, Any]:
    """world_map.json shapes from before the tables: hazards as [p, text(, dc)] lists."""
    if name != "hazards":
        return d
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            out[k] = {"p": float(v[0]), "text": {"zh": str(v[1]), "en": str(v[1]), "ja": str(v[1])}, **({"dc": int(v[2])} if len(v) > 2 else {})}
        elif isinstance(v, dict):
            out[k] = v
    return out


def pick(v: Any, lang: str) -> str:
    """A {lang: text} value (or a plain string) in the world's language."""
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("zh") or v.get("en") or "")
    return "" if v is None else str(v)


def rules(root: Path | None) -> dict[str, Any]:
    return table(root, "rules")


def foe_key(root: Path | None, name: str) -> str | None:
    """A foe's stable id from any of its names / aliases in any language (case-insensitive)."""
    n = str(name or "").strip().lower()
    if not n:
        return None
    for fid, f in table(root, "foes").items():
        names = [fid, *((f.get("names") or {}).values()), *(f.get("aliases") or [])]
        if any(n == str(x).lower() for x in names):
            return fid
    for fid, f in table(root, "foes").items():  # a longer name that contains a known one: 「山贼头目」
        names = [*((f.get("names") or {}).values()), *(f.get("aliases") or [])]
        if any(len(str(x)) >= 2 and str(x).lower() in n for x in names):
            return fid
    return None
