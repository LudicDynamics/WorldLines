"""Panels = cards for the screen: a layer's block (<formation>) or a tool's reply ([map]). Never state,
never ops. Each panel is declared once — the pack's ``ui.panels`` (Template v3), a layer's ``panels`` in ``Pack.modes``
as the default, and ``game/meta/prompt.json`` ``panels.<id>`` as a world override — with a ``format``:

    text   the block as written (monospace; TUI, quick prototypes)
    json   the block is a JSON object of the declared ``schema``; the engine only checks the shape (and fills what it
           owns, e.g. hp from foe.* variables); a malformed block falls back to text — the turn is never refused
    image  map only: the world-map level image + hotspots (core/worldmap), no model output involved

The value every consumer gets: ``{"id", "format", "source", "text"?, "data"?, "fallback"?}``."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from neonrp import prompts as _prompts

FORMATS = ("text", "json", "image")

_JSON_DOC = _prompts.by_lang("panels", "_JSON_DOC")


def _pack(root: Path) -> Any | None:
    try:
        from neonrp.packs import resolve as _resolve_pack

        return _resolve_pack(root)
    except Exception:  # noqa: BLE001
        return None


def declared(root: Path) -> dict[str, dict[str, Any]]:
    """id → merged declaration: layer defaults (Pack.modes[*].panels) < Pack.ui.panels < prompt.json panels.<id>."""
    out: dict[str, dict[str, Any]] = {}
    p = _pack(root)
    for layer, spec in ((getattr(p, "modes", None) or {}) if p else {}).items():
        for pid, doc in ((spec or {}).get("panels") or {}).items():
            out[pid] = {"id": pid, "layer": layer, "tag": pid, "format": "text", "prompt_i18n": doc if isinstance(doc, dict) else {"zh": str(doc)}}
    for d in ((getattr(p, "ui", None) or {}).get("panels") or []) if p else []:
        if isinstance(d, dict) and d.get("id"):
            out[d["id"]] = {**out.get(d["id"], {"id": d["id"], "format": "text"}), **{k: v for k, v in d.items() if v is not None}}
    try:
        from neonrp.core.adv import prompt_spec

        for pid, d in ((prompt_spec(root).get("panels") or {}) or {}).items():
            if isinstance(d, dict):
                out[pid] = {**out.get(pid, {"id": pid, "format": "text"}), **d}
    except Exception:  # noqa: BLE001
        pass
    for d in out.values():
        if d.get("format") not in FORMATS:
            d["format"] = "text"
    return out


def doc_for(root: Path, pid: str, lang: str) -> str:
    """The line the layer's format section shows for a panel block, by its declared format."""
    d = declared(root).get(pid) or {"id": pid, "format": "text"}
    if d.get("format") == "json":
        tmpl = _JSON_DOC.get(lang) or _JSON_DOC["zh"]
        return tmpl.format(id=pid, schema=json.dumps(d.get("schema") or {}, ensure_ascii=False))
    i18n = d.get("prompt_i18n") or {}
    if isinstance(d.get("prompt"), dict):  # {lang: text} (10-06)
        i18n = {**i18n, **d["prompt"]}
        d = {**d, "prompt": None}
    text = d["prompt"] if isinstance(d.get("prompt"), str) and d["prompt"].strip() else str(i18n.get(lang) or (i18n.get("en") if lang != "zh" else None) or i18n.get("zh") or "")
    return re.sub(rf"^\s*{re.escape(pid)}\s*[:：]\s*", "", text)  # adv_format writes the "<id>:" head itself


def _shape_ok(schema: Any, value: Any, path: str = "$") -> str | None:
    """Loose structural check: dict keys present with the right kind; lists checked by their first schema item."""
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            return f"{path} 应为对象"
        for k, sub in schema.items():
            if k in value:
                err = _shape_ok(sub, value[k], f"{path}.{k}")
                if err:
                    return err
        return None
    if isinstance(schema, list):
        if not isinstance(value, list):
            return f"{path} 应为数组"
        if schema:
            for i, v in enumerate(value[:50]):
                err = _shape_ok(schema[0], v, f"{path}[{i}]")
                if err:
                    return err
        return None
    kind = str(schema)
    ok = {"int": lambda v: isinstance(v, int) and not isinstance(v, bool), "float": lambda v: isinstance(v, (int, float)),
          "str": lambda v: isinstance(v, str), "bool": lambda v: isinstance(v, bool)}.get(kind)
    if ok is not None and value is not None and not ok(value):
        return f"{path} 应为 {kind}"
    return None


def _var_max(root: Path, v: Any, default: Any = None) -> Any:
    """A variable's ceiling: its fixed max, else the value its ``max_key`` points at in its own file."""
    if getattr(v, "max", None) is not None:
        return v.max
    if getattr(v, "max_key", None) and getattr(v, "path", None):
        try:
            cur: Any = json.loads((Path(root) / v.path).read_text(encoding="utf-8"))
            for k in str(v.max_key).split("."):
                cur = cur.get(k) if isinstance(cur, dict) else None
            return cur if cur is not None else default
        except (OSError, ValueError):
            return default
    return default


def _fill_from_state(root: Path, pid: str, data: dict[str, Any]) -> dict[str, Any]:
    """What the engine owns in a formation: each unit's hp / hp_max from the foe.* variables (and the player's)."""
    if pid != "formation":
        return data
    try:
        from neonrp.core.registry import load_registry

        reg = load_registry(root)
        hp = reg.variables.get("player.hp")
        pl = reg.entries.get("player")
        for side in data.get("sides") or []:
            for u in side.get("units") or [] if isinstance(side, dict) else []:
                if not isinstance(u, dict):
                    continue
                uid = str(u.get("id") or "").removeprefix("foe.")
                fv = reg.variables.get(f"foe.{uid}.hp")
                if fv is not None:
                    u["hp"], u["hp_max"] = fv.value, _var_max(root, fv, u.get("hp_max"))
                elif uid in ("player", "你", "you") and hp is not None:
                    u["hp"], u["hp_max"] = hp.value, (pl.props.get("max_hp") if pl is not None else None)
    except Exception:  # noqa: BLE001 — a filled number is a nicety, never a failure
        pass
    return data


def finish(root: Path, pid: str, raw: str, *, source: str = "layer") -> dict[str, Any]:
    """A panel block as written → the value consumers render (json checked and filled; bad json → text)."""
    d = declared(root).get(pid) or {"format": "text"}
    text = (raw or "").strip("\n")
    if d.get("format") == "json":
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        try:
            data = json.loads(body)
        except ValueError as exc:
            return {"id": pid, "format": "text", "source": source, "text": text, "fallback": f"json: {exc}"[:160]}
        err = _shape_ok(d.get("schema") or {}, data)
        if err:
            return {"id": pid, "format": "text", "source": source, "text": text, "fallback": f"shape: {err}"}
        return {"id": pid, "format": "json", "source": source, "data": _fill_from_state(root, pid, data)}
    return {"id": pid, "format": "text", "source": source, "text": text}


def as_text(panel: Any) -> str:
    """For terminals: a panel value as monospace text."""
    if isinstance(panel, str):
        return panel
    if not isinstance(panel, dict):
        return str(panel)
    if panel.get("text"):
        return str(panel["text"])
    if panel.get("format") == "image":
        return f"[image] {panel.get('data', {}).get('image') or ''}"
    return json.dumps(panel.get("data"), ensure_ascii=False, indent=1)
