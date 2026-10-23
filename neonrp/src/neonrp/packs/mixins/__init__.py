"""Mixins — pack fragments a template adds on top of its base pack (``rpg+economy+factions``).

A mixin is the pack layer's plug-in: classes / actions / variables / triggers / prompt entries plus
``ticks`` (deterministic world rules run inside every apply, core/sdk.py ``_run_ticks``). Its rules live
here; its DATA lives in the world (``game/world/<mixin>.json``) — goods, markets, factions are world data,
so the same mixin runs on any world that ships the data (World = 数据, Pack = 引擎层).

Built-ins: ``economy`` (markets, prices, caravans, trade) · ``factions`` (power / wealth / relations,
rumors, quests, strikes). Ported from the WorldLines 3.0 mock (ext.js), where they were front-end JS.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

BUILTIN = ("economy", "factions")


def rng(*key: Any) -> random.Random:
    """A seeded RNG per (turn, what) — a replayed turn rolls the same dice."""
    return random.Random(int(hashlib.sha256(":".join(map(str, key)).encode()).hexdigest()[:12], 16))


def read(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def write(p: Path, data: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def dget(d: dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def dset(d: dict[str, Any], dotted: str, value: Any) -> None:
    *head, last = dotted.split(".")
    cur = d
    for k in head:
        cur = cur.setdefault(k, {})
    cur[last] = value


def world_data(root: Path, name: str) -> dict[str, Any]:
    return read(root / get_data_dir_name(root) / "world" / f"{name}.json")


def register_vars(root: Path, specs: dict[str, dict[str, Any]]) -> list[str]:
    """Bulk-write variable overlays (``game/meta/variables.json``) and seed each value where it lives,
    only when missing — installing twice changes nothing. Returns the names added."""
    meta = root / get_data_dir_name(root) / "meta" / "variables.json"
    cur = read(meta)
    added: list[str] = []
    files: dict[Path, dict[str, Any]] = {}
    for name, spec in specs.items():
        seed = spec.pop("seed", None)
        if name not in cur:
            cur[name] = spec
            added.append(name)
        p = root / spec["path"]
        data = files.setdefault(p, read(p))
        if dget(data, spec["key"]) is None and seed is not None:
            dset(data, spec["key"], seed)
    for p, data in files.items():
        write(p, data)
    if added:
        write(meta, cur)
    return added


def set_var(root: Path, reg: Any, name: str, value: Any) -> Any:
    """Write a registered variable (file + in-memory registry), clamped to its min / max. Returns the old value."""
    spec = reg.variables[name]
    if spec.type == "int":
        value = int(round(value))
        if spec.min is not None:
            value = max(int(spec.min), value)
        if spec.max is not None:
            value = min(int(spec.max), value)
    p = root / spec.path
    data = read(p)
    old = dget(data, spec.key)
    dset(data, spec.key, value)
    write(p, data)
    spec.value = value
    return old


def vint(reg: Any, name: str, default: int = 0) -> int:
    v = reg.variables.get(name)
    try:
        return int(v.value) if v is not None and v.value is not None else default
    except (TypeError, ValueError):
        return default


def new_entry(root: Path, reg: Any, cls: str, eid: str, props: dict[str, Any], *, parent: str | None = None, turn: int = 0, by: str = "") -> str:
    """An open-schema instance of a mixin class, written where the class keeps them and added to the registry."""
    from neonrp.core.registry import Envelope

    spec = reg.classes[cls]
    f = root / spec.folder / f"{eid}.json"
    data = {"id": eid, "class": cls, "parent": parent, "links": [], "props": props, "provenance": {"turn": turn, "by": by}}
    write(f, data)
    reg.add(Envelope(eid, cls, parent, [], dict(props), dict(data["provenance"]), set(), str(f.relative_to(root))))
    return eid


def patch_entry(root: Path, reg: Any, eid: str, **props: Any) -> None:
    e = reg.entries[eid]
    e.props.update(props)
    f = root / e.source
    data = read(f)
    data.setdefault("props", {}).update(props)
    write(f, data)


def next_id(reg: Any, prefix: str) -> str:
    n = sum(1 for e in reg.entries if e.startswith(prefix)) + 1
    while f"{prefix}{n:03d}" in reg.entries:
        n += 1
    return f"{prefix}{n:03d}"


def town_of(reg: Any, where: str | None) -> str:
    return str(where or "").split("/")[0]
