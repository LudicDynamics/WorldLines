"""Engine v3 configuration surface (ENGINE-V3-MASTER-PLAN §10).

One dict, its layers, later wins::

    builtin defaults  <  pack.loop  <  play contract["engine"]  <  the orchestration template the world uses
    (core/orch_templates, 10-19 stage A)  <  game/meta/engine.json  <  the orchestration graph's step_params
    (game/meta/orchestration.json, 10-17 S2: the one source an editor writes)  <  .neonrp/playthrough.json["engine"]  <  env

``pack.loop`` is the template pack's agent loop (Pack = 引擎层): the rpg pack runs the full
new engine (v3 · S-judge · ADV); a world / run can still pin v2b in its engine.json.

Every knob can be turned off individually to fall back to today's behaviour.
``explain()`` reports where each effective value came from (for ``/engine``).
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "turn": {
        # "v2b" = today's world-agent tool loop; "v3" = five-phase loop.
        "mode": "v2b",
        "plan": {"backend": "auto", "confidence": 0.7, "react": 0.6, "fallback_depth": "act",
                 "pack_budget": 0},  # 0 = sdk default (7000 chars); ablation E1c sets 2500
        "parallel": {
            # legacy = the pre-v3 soul path (engage loop / one Q&A by depth); the three closed-schema
            # variants are S-judge | S-direct | S-free (soul_step.VARIANTS). E2 decides the v3 default.
            "souls": {"default_variant": "legacy", "per_soul": {}, "max_workers": 8,
                      "timeout_s": 20, "escalate_at": 0.8, "escalate_turns": 3, "heavy_at": 0.4, "decide_conf": 0.5,
                      "adjudicate": 1},  # 0 = no persuasion adjudication (ablation E6-noadj)
            "tools": {"enabled": [], "disabled": []},
            "ctb": {"enabled": False, "budget_per_turn": 2, "wait_day_threshold": 0.7},
        },
        "solve": {"structured": "adv", "max_ops": 24, "stream": False, "history": 4, "sections": "xml", "async_mark": "tilde"},  # adv(文字 + <lines>/<ops>/<options> 块,09-28 定)| json_object | tags | split2 …  # together | json_object(约束解码)| json_schema | split(先叙事再抽取,E1 对照臂)
        "verify": {"l2": "auto", "grounded_min": 0.5, "missed_min": 0.6,
                   "gate": {"need_more": 0.7, "need_fix": 0.7, "max_loops": 1}},
        "apply": {"writers": "on", "re_propose": {"max": 1, "world_conflicts": [
            "same_item", "addressed_but_leaving", "commitment_vs_intention", "tool_flag_clash"]}},
    }
}

# env var -> dotted path (+ coercion). Kept small on purpose: env is for
# experiments; products edit engine.json.
_ENV: dict[str, tuple[str, str]] = {
    "NEONRP_TURN_V3": ("turn.mode", "v3flag"),
    "NEONRP_S1_BACKEND": ("turn.plan.backend", "str"),
    "NEONRP_S1_CONFIDENCE": ("turn.plan.confidence", "float"),
    "NEONRP_S1_REACT": ("turn.plan.react", "float"),
    "NEONRP_S1_FALLBACK_DEPTH": ("turn.plan.fallback_depth", "str"),
    "NEONRP_S1_ENGAGE_TURNS": ("turn.parallel.souls.escalate_turns", "int"),
    "NEONRP_V3_MAX_LOOPS": ("turn.verify.gate.max_loops", "int"),
    "NEONRP_V3_MAX_OPS": ("turn.solve.max_ops", "int"),
    "NEONRP_V3_WRITERS": ("turn.apply.writers", "str"),
    "NEONRP_SOUL_VARIANT": ("turn.parallel.souls.default_variant", "str"),
    "NEONRP_V3_SOLVE": ("turn.solve.structured", "str"),
    "NEONRP_V3_SECTIONS": ("turn.solve.sections", "str"),  # xml | divider | fence — how the output sections are marked
    "NEONRP_V3_ASYNC_MARK": ("turn.solve.async_mark", "str"),  # angle | tilde — how the model is taught to mark an async op (<map> / [~map])
    "NEONRP_SOUL_ADJUDICATE": ("turn.parallel.souls.adjudicate", "int"),
    "NEONRP_V3_L2": ("turn.verify.l2", "str"),
    "NEONRP_PACK_BUDGET": ("turn.plan.pack_budget", "int"),
}


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _set_path(d: dict[str, Any], dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value


def _get_path(d: dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _coerce(kind: str, raw: str) -> Any:
    raw = raw.strip()
    if kind == "v3flag":
        return "v3" if raw.lower() in ("1", "true", "v3", "on") else "v2b"
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    return raw


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _contract_engine(root: Path) -> dict[str, Any]:
    """The play contract's ``engine`` block (how a turn runs — planning beat, narrate-then-transition — belongs
    to the kind of game, i.e. the contract; a world built from a template that declares it plays that way, a world
    without a contract keeps the engine's defaults)."""
    try:
        from neonrp.template.contract import run_contract

        c = run_contract(root) or {}
    except Exception:  # noqa: BLE001
        return {}
    eng = c.get("engine")
    eng = eng if isinstance(eng, dict) else {}
    return _deep_merge(eng, _private_contract_engine(str(c.get("id") or ""))) if c else eng


def _private_contract_engine(cid: str) -> dict[str, Any]:
    """Our own turn settings for a contract (10-08 open engine · private orchestration): the private layer's
    ``contracts/<id>.engine.json`` — only the ``engine`` block, laid over the public contract's at run time (never
    copied into the save, so a shared save or replay carries the public contract only)."""
    if not cid or "/" in cid or ".." in cid:
        return {}
    from neonrp.core.paths import private_dir

    d = private_dir("contracts")
    return _read_json(d / f"{cid}.engine.json") if d is not None else {}


def _orchestration_layer(root: Path) -> dict[str, Any]:
    """The settings of the orchestration template the run's world uses (its template record's ``uses``; a run built
    before templates: what its play contract stood for) — looked up at run time, never copied into the save."""
    from neonrp.core import orch_templates
    from neonrp.template.contract import run_contract

    meta = root / get_data_dir_name(root) / "meta"
    key = (_mtime(meta / "template.json"), _mtime(meta / "play_contract.json"), orch_templates.stamp())
    hit = _ORCH_LAYER.get(str(meta))
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        layer = orch_templates.layer(_read_json(meta / "template.json").get("uses"), contract=run_contract(root) is not None)
    except Exception:  # noqa: BLE001 — a broken template never stops a turn
        logger.warning("orchestration template layer failed", exc_info=True)
        layer = {}
    if len(_ORCH_LAYER) > 64:
        _ORCH_LAYER.clear()
    _ORCH_LAYER[str(meta)] = (key, layer)
    return layer


_ORCH_LAYER: dict[str, tuple[Any, dict[str, Any]]] = {}


def _mtime(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def _layers(root: Path) -> list[tuple[str, dict[str, Any]]]:
    game = root / get_data_dir_name(root)
    layers: list[tuple[str, dict[str, Any]]] = [("builtin", DEFAULTS)]
    try:
        from neonrp.packs import resolve as _resolve_pack

        loop = _resolve_pack(root).loop
    except Exception:  # noqa: BLE001 — a world whose pack does not load still has a config
        loop = {}
    layers.append(("pack", loop if isinstance(loop, dict) else {}))
    layers.append(("contract", _contract_engine(root)))
    layers.append(("orchestration", _orchestration_layer(root)))
    layers.append(("world", _read_json(game / "meta" / "engine.json")))
    layers.append(("graph", _graph_layer(root)))  # 10-17 S2: the orchestration graph's step settings — the one source
    pt = _read_json(root / ".neonrp" / "playthrough.json")
    eng = pt.get("engine") if isinstance(pt.get("engine"), dict) else {}
    layers.append(("playthrough", eng))
    layers.append(("env", env_layer()))
    return layers


_GRAPH_LAYER: dict[str, tuple[float, dict[str, Any]]] = {}


def _graph_layer(root: Path) -> dict[str, Any]:
    """The run's orchestration override's ``step_params`` (core/turn_steps.graph_layer), cached on the file's mtime —
    the default graph carries none, so only the override matters; read on every turn, so kept cheap."""
    p = root / get_data_dir_name(root) / "meta" / "orchestration.json"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    key = str(p)
    hit = _GRAPH_LAYER.get(key)
    if hit is not None and hit[0] == mt:
        return hit[1]
    d = _read_json(p)
    if not any(isinstance(n, dict) and n.get("step_params") for n in (d.get("nodes") or {}).values()):
        layer: dict[str, Any] = {}
    else:
        from neonrp.core import turn_steps

        layer = turn_steps.graph_layer(d)
    _GRAPH_LAYER[key] = (mt, layer)
    return layer


def env_layer() -> dict[str, Any]:
    """The env layer alone (experiments: ``NEONRP_TURN_V3`` · ``NEONRP_SOUL_VARIANT`` …)."""
    env: dict[str, Any] = {}
    for var, (dotted, kind) in _ENV.items():
        raw = os.environ.get(var)
        if raw is None or raw == "":
            continue
        try:
            _set_path(env, dotted, _coerce(kind, raw))
        except ValueError:
            logger.warning("engine config: ignoring %s=%r", var, raw)
    return env


def engine_config(root: Path) -> dict[str, Any]:
    """Effective configuration for ``root`` (all four layers merged)."""
    cfg: dict[str, Any] = {}
    for _name, layer in _layers(root):
        cfg = _deep_merge(cfg, layer)
    return cfg


def get(root: Path, dotted: str, default: Any = None) -> Any:
    return _get_path(engine_config(root), dotted, default)


def explain(root: Path) -> list[tuple[str, Any, str]]:
    """``[(dotted_key, value, source_layer)]`` for every leaf, for ``/engine``."""
    rows: dict[str, tuple[Any, str]] = {}

    def walk(prefix: str, d: dict[str, Any], src: str) -> None:
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and v and not (prefix.endswith("per_soul")):
                walk(key, v, src)
            else:
                rows[key] = (v, src)

    for name, layer in _layers(root):
        walk("", layer, name)
    return sorted((k, v, s) for k, (v, s) in rows.items())


def v3_enabled(root: Path) -> bool:
    return str(get(root, "turn.mode", "v2b")).lower() == "v3"
