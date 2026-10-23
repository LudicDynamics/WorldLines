"""Template packs — what the engine does not know until a world names its template
(「rpg = template;狼人杀 / 海龟汤要能跑同一套;2–4 个内置,自定的可放 WorldLines」).

A pack seeds the registry's five tables and the mechanics seams:

    Pack(name, classes, actions, variables, triggers, mechanics, prompt, doc)

Two forms:
  * a Python pack — ``neonrp.packs.<name>.pack`` exposing ``PACK`` (the built-ins: rpg, werewolf);
    a custom one is any importable ``module:PACK``;
  * a JSON pack — a folder holding ``pack.json`` (classes / actions / variables / triggers /
    mechanics / prompt in their overlay shapes; handlers named ``builtin:…`` or ``module:function``),
    the form a creator or WorldLines writes.

Which pack a world uses: ``manifest.json["template"]`` > ``playthrough.json["template"]``
(root or ``.neonrp/``) > ``"rpg"``. A name resolves against the built-ins, then
``<world>/template/`` (a JSON pack shipped inside the world), then the folders on
``NEONRP_TEMPLATE_PATH`` (WorldLines' template store); a path or ``module:PACK`` is used as is.
"""
from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from neonrp.core.registry import ActionSpec, ClassSpec, action_from_dict, class_from_dict

BUILTIN = ("rpg", "werewolf", "monopoly", "pct")
DEFAULT = "rpg"


@dataclass
class Pack:
    name: str
    classes: dict[str, ClassSpec] = field(default_factory=dict)
    actions: list[ActionSpec] = field(default_factory=list)
    variables: dict[str, dict[str, Any]] = field(default_factory=dict)  # overlay shape: {name: {type, path, key, …}}
    triggers: dict[str, dict[str, Any]] = field(default_factory=dict)  # when / if / then / else rows
    mechanics: dict[str, str] = field(default_factory=dict)  # seam → handler name (core/mechanics.py)
    prompt: str = ""  # the template's own world-side contract text, if its contract handler wants it
    doc: str = ""
    source: str = ""
    flags: dict[str, str] = field(default_factory=lambda: {"path": "game/meta/flags.json", "key": "flags"})  # where flag.* live
    blocks: tuple[str, ...] = ("lines", "ops", "options")  # the ADV blocks this template asks the model for (cot optional)
    prompt_spec: dict[str, Any] = field(default_factory=dict)  # pack.json "prompt": rules / voice / entries / ops_docs at the template level
    # mode layers (v2's sub-agents = a whole other system prompt): name → {prompt: FS file, reads: [texts], ops: [op names],
    # strip: [v2 section titles to drop], state: "module:function" (state block), exit: op name, one_shot: bool, title: str}
    modes: dict[str, dict[str, Any]] = field(default_factory=dict)
    # the agent loop this template runs (Pack = 引擎层 / agent loop 的自定义层): an engine_config
    # fragment ({"turn": {"mode": "v3", "parallel": {"souls": {"default_variant": "S-judge"}}, …}}), layered
    # builtin < pack.loop < game/meta/engine.json < playthrough < env (core/engine_config.py)
    loop: dict[str, Any] = field(default_factory=dict)
    # world ticks: "module:function" run inside every apply after the turn's ops — fn(root, reg, *, turn, res) -> [op]
    # (deterministic world simulation: prices, factions, rumors …); mixins add theirs
    ticks: list[str] = field(default_factory=list)
    mixins: tuple[str, ...] = ()  # mixins composed into this pack (packs/mixins), in order
    base: str = ""  # the built-in pack this one is built on (pct → rpg): its layer prompts are the fallback (10-05)
    # the pack's own part of the orchestration graph (core/orchestration.py, worldlines.orchestration/1): extra
    # {"nodes": {…}, "edges": [...]} on top of the graph the engine generates from today's behaviour (phases, encounters)
    orchestration: dict[str, Any] = field(default_factory=dict)
    # declared presentation (Template v3 / Mock 3.0): {"slots": [...], "views": [...], "prompts": {id: text}, "budget": int}
    ui: dict[str, Any] = field(default_factory=dict)
    # the class whose instances are the cast when it is not souls (a rule pack's seats, 10-08 E2); a contract's
    # entry.cast: fixed counts them as a fixed cast
    cast_class: str = ""

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any], source: str = "") -> "Pack":
        base = load(str(d["extends"])) if d.get("extends") else None
        classes = dict(base.classes) if base else {}
        for cname, spec in (d.get("classes") or {}).items():
            if spec is None:
                classes.pop(cname, None)
            elif isinstance(spec, dict):
                classes[cname] = class_from_dict(cname, spec, classes.get(cname))
        actions = {a.op: a for a in base.actions} if base else {}
        for op, spec in (d.get("actions") or {}).items():
            if spec is None:
                actions.pop(op, None)
            elif isinstance(spec, dict):
                actions[op] = action_from_dict(op, spec, actions.get(op))
        out = cls(name, classes, list(actions.values()),
                  {**(base.variables if base else {}), **(d.get("variables") or {})},
                  {**(base.triggers if base else {}), **(d.get("triggers") or {})},
                  {**(base.mechanics if base else {}), **{k: str(v) for k, v in (d.get("mechanics") or {}).items()}},
                  str(d.get("prompt") or (base.prompt if base else "")), str(d.get("doc") or ""), source)
        if base:
            out.flags = dict(base.flags)
        if isinstance(d.get("flags"), dict):
            out.flags.update({k: str(v) for k, v in d["flags"].items()})
        if base:
            out.blocks = tuple(base.blocks)
        if isinstance(d.get("blocks"), list) and d["blocks"]:
            out.blocks = tuple(str(b) for b in d["blocks"])
        if base:
            out.prompt_spec = dict(base.prompt_spec)
        if isinstance(d.get("prompt"), dict):
            from neonrp.core.adv import merge_prompt_spec

            out.prompt_spec = merge_prompt_spec(out.prompt_spec, d["prompt"])
        if base:
            out.modes = {k: dict(v) for k, v in base.modes.items()}
        for mname, mspec in (d.get("modes") or {}).items():
            if mspec is None:
                out.modes.pop(mname, None)
            elif isinstance(mspec, dict):
                out.modes[mname] = {**out.modes.get(mname, {}), **mspec}
        out.loop = _deep_merge(dict(base.loop) if base else {}, d.get("loop") if isinstance(d.get("loop"), dict) else {})
        out.ticks = list(base.ticks if base else []) + [str(t) for t in d.get("ticks") or [] if t]
        out.mixins = tuple(base.mixins) if base else ()
        out.ui = merge_ui(dict(base.ui) if base else {}, d.get("ui") if isinstance(d.get("ui"), dict) else {})
        out.orchestration = _merge_orch(dict(base.orchestration) if base else {},
                                        d.get("orchestration") if isinstance(d.get("orchestration"), dict) else {})
        out.cast_class = str(d.get("cast_class") or (base.cast_class if base else ""))
        if d.get("mixins"):
            out = compose(out, [str(m) for m in d["mixins"]])
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "classes": sorted(self.classes), "actions": [a.op for a in self.actions],
                "variables": sorted(self.variables), "triggers": sorted(self.triggers), "mechanics": dict(self.mechanics),
                "source": self.source, "loop": self.loop, "ticks": list(self.ticks), "mixins": list(self.mixins)}


class PackError(ValueError):
    pass


def _search_dirs(root: Path | None) -> list[Path]:
    out: list[Path] = []
    if root is not None:
        out.append(Path(root) / "template")
    for d in (os.environ.get("NEONRP_TEMPLATE_PATH") or "").split(os.pathsep):
        if d.strip():
            out.append(Path(d.strip()).expanduser())
    return out


def _from_json_dir(d: Path, name: str) -> Pack:
    try:
        data = json.loads((d / "pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PackError(f"cannot read {d / 'pack.json'}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackError(f"{d / 'pack.json'} must be an object")
    return Pack.from_dict(str(data.get("name") or name), data, str(d))


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def merge_ui(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Layer presentation declarations: slots by (cls, slot), views / panels by id, prompts by key; ``remove`` / ``null``
    drops one; budget replaces. Panels = what a layer or tool draws (formation, map): the pack gives the default, a template
    overrides the prompt and the format (``text`` | ``json`` with ``schema`` | ``image``) — TEMPLATE-V3-ENGINE-REQUESTS §2."""
    out: dict[str, Any] = {"slots": list(base.get("slots") or []), "views": list(base.get("views") or []),
                           "panels": list(base.get("panels") or []),
                           "prompts": dict(base.get("prompts") or {}), **({"budget": base["budget"]} if "budget" in base else {})}
    if not over:
        return out
    for key, idf in (("slots", lambda x: (x.get("cls"), x.get("slot"))), ("views", lambda x: x.get("id")), ("panels", lambda x: x.get("id"))):
        rows = {idf(x): x for x in out[key] if isinstance(x, dict)}
        for x in over.get(key) or []:
            if not isinstance(x, dict):
                continue
            if x.get("remove"):
                rows.pop(idf(x), None)
            else:
                rows[idf(x)] = {**rows.get(idf(x), {}), **x}
        out[key] = list(rows.values())
    for k, v in (over.get("prompts") or {}).items():
        if v is None:
            out["prompts"].pop(k, None)
        else:
            out["prompts"][k] = str(v)
    if "budget" in over:
        out["budget"] = int(over["budget"])
    beats = {**(base.get("beats") or {}), **(over.get("beats") or {})} if (base.get("beats") or over.get("beats")) else None
    if beats is not None:  # how the beats are shown (R2/R3): kinds merged by node, start replaced
        beats["kinds"] = {**((base.get("beats") or {}).get("kinds") or {}), **((over.get("beats") or {}).get("kinds") or {})}
        out["beats"] = beats
    return out


def mixin_spec(name: str) -> dict[str, Any]:
    """A mixin's pack-shaped fragment: ``neonrp.packs.mixins.<name>.MIXIN`` or a folder / file holding ``mixin.json``."""
    p = Path(name).expanduser()
    for cand in (p / "mixin.json", p) if p.suffix in ("", ".json") else ():
        if cand.is_file():
            try:
                d = json.loads(cand.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise PackError(f"{cand}: not JSON ({exc})") from exc
            return d if isinstance(d, dict) else {}
    try:
        return dict(importlib.import_module(f"neonrp.packs.mixins.{name}").MIXIN)
    except (ImportError, AttributeError) as exc:
        raise PackError(f"unknown mixin {name!r}: {exc}") from exc


def _merge_orch(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """The pack's orchestration part: nodes by key, edges appended (an edge id seen again replaces the earlier one)."""
    nodes = {**(a.get("nodes") or {}), **(b.get("nodes") or {})}
    edges = {str(e.get("id") or i): e for i, e in enumerate([*(a.get("edges") or []), *(b.get("edges") or [])]) if isinstance(e, dict)}
    out: dict[str, Any] = {}
    if nodes:
        out["nodes"] = nodes
    if edges:
        out["edges"] = list(edges.values())
    return out


def compose(base: Pack, mixins: list[str]) -> Pack:
    """``base`` + mixins (packs/mixins): classes / actions / variables / triggers / prompt entries add up
    (a later one wins on the same key), mechanics fill only seams the base left empty, loops deep-merge,
    ticks append. The result is named ``base+m1+m2`` so ``load`` can rebuild it from the name alone."""
    out = Pack(base.name, dict(base.classes), list(base.actions), dict(base.variables), dict(base.triggers),
               dict(base.mechanics), base.prompt, base.doc, base.source)
    out.flags, out.blocks, out.prompt_spec = dict(base.flags), tuple(base.blocks), dict(base.prompt_spec)
    out.modes, out.loop, out.ticks, out.mixins = {k: dict(v) for k, v in base.modes.items()}, dict(base.loop), list(base.ticks), tuple(base.mixins)
    out.ui = merge_ui({}, base.ui)
    out.orchestration = _merge_orch({}, base.orchestration)
    out.cast_class = base.cast_class
    for m in mixins:
        if m in out.mixins:
            continue
        d = mixin_spec(m)
        for cname, spec in (d.get("classes") or {}).items():
            if isinstance(spec, dict):
                out.classes[cname] = class_from_dict(cname, spec, out.classes.get(cname))
        acts = {a.op: a for a in out.actions}
        for op, spec in (d.get("actions") or {}).items():
            if isinstance(spec, dict):
                acts[op] = action_from_dict(op, spec, acts.get(op))
        out.actions = list(acts.values())
        out.variables.update(d.get("variables") or {})
        out.triggers.update(d.get("triggers") or {})
        for seam, h in (d.get("mechanics") or {}).items():
            out.mechanics.setdefault(seam, str(h))
        if isinstance(d.get("prompt"), dict):
            from neonrp.core.adv import merge_prompt_spec

            out.prompt_spec = merge_prompt_spec(out.prompt_spec, d["prompt"])
        out.loop = _deep_merge(out.loop, d.get("loop") if isinstance(d.get("loop"), dict) else {})
        out.ticks += [str(t) for t in d.get("ticks") or [] if t and str(t) not in out.ticks]
        out.ui = merge_ui(out.ui, d.get("ui") if isinstance(d.get("ui"), dict) else {})
        out.orchestration = _merge_orch(out.orchestration, d.get("orchestration") if isinstance(d.get("orchestration"), dict) else {})
        out.mixins = (*out.mixins, m)
    if out.mixins != base.mixins:
        out.name = "+".join([base.name.split("+")[0], *out.mixins])
    return out


def load(name: str, root: Path | None = None) -> Pack:
    """Resolve a template name / path / ``module:PACK`` to a Pack (cached per name).
    ``rpg+economy+factions`` = the base pack composed with mixins (``compose``)."""
    name = str(name or DEFAULT).strip() or DEFAULT
    if "+" in name and not Path(name).exists():
        head, *mix = [x.strip() for x in name.split("+") if x.strip()]
        return compose(load(head, root), mix)
    if ":" in name and not Path(name).exists():  # module:PACK
        mod, _, attr = name.partition(":")
        try:
            pk = getattr(importlib.import_module(mod), attr)
        except (ImportError, AttributeError) as exc:
            raise PackError(f"cannot import template {name!r}: {exc}") from exc
        return pk if isinstance(pk, Pack) else Pack.from_dict(name, dict(pk), name)
    p = Path(name).expanduser()
    if p.is_dir() and (p / "pack.json").exists():
        return _from_json_dir(p, p.name)
    if name in BUILTIN:
        return _builtin(name)
    for d in _search_dirs(root):
        cand = d / name if (d / name / "pack.json").exists() else (d if d.name == name and (d / "pack.json").exists() else None)
        if cand is not None:
            return _from_json_dir(cand, name)
    if root is not None and (Path(root) / "template" / "pack.json").exists():
        return _from_json_dir(Path(root) / "template", name)
    raise PackError(f"unknown template {name!r}: not built in {BUILTIN}, no pack.json folder, not on NEONRP_TEMPLATE_PATH")


@lru_cache(maxsize=None)
def _builtin(name: str) -> Pack:
    return importlib.import_module(f"neonrp.packs.{name}.pack").PACK


def template_of(root: Path) -> str:
    """The template name a world declares (manifest.json > playthrough.json > rpg)."""
    from neonrp.core.paths import get_data_dir_name

    for cand in (Path(root) / "manifest.json", Path(root) / get_data_dir_name(Path(root)) / "playthrough.json", Path(root) / "playthrough.json"):
        try:
            d = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("template"):
            return str(d["template"])
    return DEFAULT


def resolve(root: Path) -> Pack:
    """The pack a world runs on."""
    return load(template_of(root), root)
