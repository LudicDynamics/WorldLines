"""Mode layers — the v3 equivalent of v2's ``task(sub-agent)``:

A **mode** is a whole other system prompt (the sub-agent's own ``system.md`` from the world's file system), its own
reads (texts the engine packs for it — the sub-agent's READ contract, no read tool), its own op lines (what it may
write, through the same ops), and a state block. Entering a mode changes the whole prompt for the rest of the turn
(``<combat>…</combat>`` is a stop point: the narrator's prefix stays, the layer continues) and for the following turns
until the layer's exit op clears ``run_state.json["mode"]``.

The pack declares its modes (``Pack.modes``); the engine knows only the shape: prompt · reads · ops · strip · state · exit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_data_dir_name
from neonrp import prompts as _prompts

# v2 sections that were the read/task/JSON protocol: the engine does those now, so they leave the prompt
DEFAULT_STRIP = ("读写边界", "输出格式", "掷骰", "读什么文件", "语言匹配", "不出选项菜单", "战斗回合的行动列表", "Read/Write", "Output", "Language", "No menus", "Dice")

BASE_RULES = _prompts.by_lang("modes", "BASE_RULES")
LAYER_HEAD = _prompts.by_lang("modes", "LAYER_HEAD")
READS_TITLE = _prompts.by_lang("modes", "READS_TITLE")


def _rs_path(root: Path) -> Path:
    return root / get_data_dir_name(root) / "meta" / "run_state.json"


def read_mode(root: Path) -> dict[str, Any] | None:
    try:
        m = json.loads(_rs_path(root).read_text(encoding="utf-8")).get("mode")
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) and m.get("name") else None


def write_mode(root: Path, mode: dict[str, Any] | None) -> None:
    p = _rs_path(root)
    try:
        rs = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rs = {}
    if mode is None:
        rs.pop("mode", None)
    else:
        rs["mode"] = mode
    p.write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")


def spec_of(root: Path, name: str) -> dict[str, Any] | None:
    from neonrp.packs import resolve as _resolve_pack

    m = _resolve_pack(root).modes.get(name)
    return dict(m) if isinstance(m, dict) else None


def strip_sections(text: str, titles: tuple[str, ...] = DEFAULT_STRIP) -> str:
    """Drop the ``## `` sections whose title starts with one of ``titles`` (their ``###`` children go with them)."""
    out: list[str] = []
    skipping = False
    for ln in text.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level <= 2:
                skipping = any(title.startswith(t) or t in title for t in titles)
            elif skipping:
                continue
        if not skipping:
            out.append(ln)
    text = "\n".join(out)
    text = re.sub(r"\n(?:---\s*\n\s*)+", "\n---\n", text)  # collapse rulers left behind
    return text.strip()


def _pack_prompt_dirs(root: Path) -> list[Path]:
    """``packs/<name>/prompts/`` of the world's pack (built-in packs ship their layer prompts there), then its base pack's
    (pct → rpg, 10-05): a layer the pack does not rewrite keeps the base's prompt."""
    try:
        from neonrp.packs import resolve as _resolve_pack

        pk = _resolve_pack(root)
        names = [str(pk.name or "").split("+")[0], str(getattr(pk, "base", "") or "")]
    except Exception:  # noqa: BLE001
        return []
    from neonrp.core.paths import private_dir

    priv = private_dir("packs")  # 10-08: the private layer's layer prompts before the pack's public ones
    out = []
    for n in names:
        if not n:
            continue
        for d in ([priv / n / "prompts"] if priv is not None else []) + [Path(__file__).resolve().parents[1] / "packs" / n / "prompts"]:
            if d.is_dir() and d not in out:
                out.append(d)
    return out


def _pack_prompt_dir(root: Path) -> Path | None:
    dirs = _pack_prompt_dirs(root)
    return dirs[0] if dirs else None


def _template_override(root: Path, name: str, lang: str) -> str | None:
    """A template / world may replace a layer's prompt by id — ``prompts["modes.<name>"]`` in the pack's ui layer (Template v3)
    or ``game/meta/prompt.json`` ``modes.<name>`` — as a string or {lang: text}."""
    cands: list[Any] = []
    try:
        from neonrp.packs import resolve as _resolve_pack

        ui = getattr(_resolve_pack(root), "ui", None) or {}
        cands.append((ui.get("prompts") or {}).get(f"modes.{name}"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from neonrp.core.adv import prompt_spec

        ps = prompt_spec(root)
        cands.append((ps.get("modes") or {}).get(name) if isinstance(ps.get("modes"), dict) else None)
    except Exception:  # noqa: BLE001
        pass
    from neonrp.core.output_lang import pick_lang

    for c in cands:
        if isinstance(c, dict):
            c = pick_lang(c, lang)
        if isinstance(c, str) and c.strip():
            return c
    return None


def _lang_chain(lang: str) -> list[str]:
    """``<name>.<lang>.md`` to try before the zh original ``<name>.md``: the run's language, then en (10-05: a ko run
    reads the en layer before falling back to the zh one)."""
    return [lg for lg in dict.fromkeys((lang, "en")) if lg != "zh"] if lang != "zh" else []


def prompt_source(root: Path, name: str, spec: dict[str, Any], lang: str) -> tuple[str, str]:
    """(text, where) for a layer's prompt, first hit wins (a world needs no agents/ folder):
    template / world override → the world's own ``agents/<id>/system.md`` (old worlds) → the pack's built-in prompt."""
    over = _template_override(root, name, lang)
    if over:
        return over, "template"
    rel = str(spec.get("prompt") or "")
    if rel:
        for c in [root / rel.replace(".md", f".{lg}.md") for lg in _lang_chain(lang)] + [root / rel]:
            try:
                return c.read_text(encoding="utf-8"), f"world:{rel}"
            except OSError:
                continue
    for d in _pack_prompt_dirs(root):
        for c in [d / f"{name}.{lg}.md" for lg in _lang_chain(lang)] + [d / f"{name}.md"]:
            try:
                return c.read_text(encoding="utf-8"), f"pack:{c.name}"
            except OSError:
                continue
    return "", "none"


def prompt_text(root: Path, spec: dict[str, Any], lang: str, name: str | None = None) -> str:
    """The layer's prompt (see prompt_source), with v2's read / task / JSON protocol sections stripped."""
    layer = name or next((k for k, v in _all_modes(root).items() if v is spec or v == spec), "")
    text, _where = prompt_source(root, layer, spec, lang)
    return strip_sections(text, tuple(spec.get("strip") or DEFAULT_STRIP)) if text else ""


def _all_modes(root: Path) -> dict[str, Any]:
    try:
        from neonrp.packs import resolve as _resolve_pack

        return dict(_resolve_pack(root).modes or {})
    except Exception:  # noqa: BLE001
        return {}


def layer_ops(reg: Any, spec: dict[str, Any]) -> Any:
    """A registry view whose world-side actions are the layer's own (its exit op always included)."""
    import copy

    allowed = set(spec.get("ops") or [])
    if spec.get("exit"):
        allowed.add(str(spec["exit"]))
    view = copy.copy(reg)
    view.actions = {k: copy.copy(a) for k, a in reg.actions.items()}
    for k, a in view.actions.items():
        if a.scope == "world" and allowed and k not in allowed and a.kind != "update":
            a.enabled = False
        if a.kind == "mode" and not spec.get("here_class"):  # no nested switching from inside a stateful layer (a place layer may still open combat)
            a.enabled = False
    return view


def layer_system(root: Path, reg: Any, name: str, lang: str, *, structured: str = "adv") -> str:
    """The whole system prompt of a mode: base rules + the sub-agent's own prompt + the ADV format with the layer's ops."""
    from neonrp.core.adv import adv_format, ops_lines

    spec = spec_of(root, name) or {}
    body = prompt_text(root, spec, lang, name)
    from neonrp.core.output_lang import pick_lang as _pl

    title = str(_pl(spec.get("title"), lang) or name)  # a string, or {lang: text} (10-06)
    from neonrp.core.adv import lang_rule

    base = (BASE_RULES.get(lang) or BASE_RULES["zh"]).replace("{LANG}", lang_rule(root, lang))
    if spec.get("output") == "json":  # a one-shot ruling layer keeps its own (v2) JSON contract
        return base + "\n\n" + body
    blocks = tuple(spec.get("blocks") or ("lines", "ops", "options"))
    from neonrp.core.output_lang import pick_lang

    tail = pick_lang(spec.get("tail"), lang)  # a string, or {lang: text} (a pack whose files carry the words, 10-05)
    from neonrp.core import panels as _panels

    pdocs = {pid: _panels.doc_for(root, pid, lang) for pid in (spec.get("panels") or {})}
    fmt = adv_format(lang, ops_lines(layer_ops(reg, spec), lang), blocks=blocks, panels=pdocs or None)
    head = ((LAYER_HEAD.get(lang) or LAYER_HEAD["zh"]).format(title=title, exit=spec.get("exit")) + "\n") if spec.get("exit") else f"# {title}\n"
    return base + "\n\n" + head + body + "\n\n" + fmt + ("\n" + tail if tail else "")


def reads_block(root: Path, reg: Any, spec: dict[str, Any]) -> str:
    """The texts the layer's contract lets it read, packed by the engine (v2's READ globs, no read tool)."""
    from neonrp.core.output_lang import pick_lang as _pl, prompt_lang as _plang

    lang = _plang(root)
    rt = str(_pl(spec.get("reads_title"), lang) or READS_TITLE.get(lang) or READS_TITLE["zh"])
    sep = ":" if lang in ("zh", "ja") else ": "
    parts = []
    texts = getattr(reg, "texts", {}) or {}
    for key in spec.get("reads") or []:
        t = texts.get(str(key))
        if t:
            parts.append(f"# {rt}{sep}{key}\n{str(t)[:3500]}")
    return "\n\n".join(parts)


def state_block(root: Path, reg: Any, spec: dict[str, Any]) -> str:
    fn = spec.get("state")
    if not fn:
        return ""
    from neonrp.core.handlers import resolve

    try:
        return str(resolve(str(fn))(root, reg) or "")
    except Exception as exc:  # noqa: BLE001
        return f"# 状态块出错:{exc}"[:200]


def here_layer(root: Path, reg: Any) -> str | None:
    """A layer keyed by where the player stands (``here_class``): used for the turn, never written to run_state.
    Read off the orchestration graph's here-class edges (O3, 10-05) — the default graph has one per pack layer."""
    if reg is None:
        return None
    from neonrp.core import orchestration

    name = orchestration.here_layer(root, reg)
    return name if name and spec_of(root, name) is not None else None


def enter(root: Path, reg: Any, name: str, *, turn: int, note: str = "", via: dict[str, Any] | None = None,
          **kw: Any) -> dict[str, Any] | None:
    """Switch the world into ``name``: run_state.mode + the layer's own spawn (state) if it has one (``kw`` reach it).
    ``via`` = what triggered it (``{"op": …}`` · ``{"gate": True}`` · ``{"tick": …}``): the orchestration graph must have
    an edge for it (O3, 10-05), else None and nothing changes. Without ``via`` (tests, tools) it just enters."""
    if via is not None:
        from neonrp.core import orchestration

        if not orchestration.allows(root, orchestration.current(root, reg), via, to=name, reg=reg):
            return None
    spec = spec_of(root, name) or {}
    mode = {"name": name, "since_turn": int(turn), "note": note[:400], "state": {}}
    prev = read_mode(root)
    if prev and prev.get("name") != name:  # O4 (10-06): entering a layer from another remembers it; leaving returns there
        mode["return"] = prev
    fn = spec.get("enter")
    if fn:
        from neonrp.core.handlers import resolve

        st = resolve(str(fn))(root, reg, note=note, turn=turn, **kw)
        if isinstance(st, dict):
            mode["state"] = st
    write_mode(root, mode)
    return mode


def leave(root: Path) -> dict[str, Any] | None:
    """Leave the current layer: back to the one it was entered from (O4 return stack), else to no layer."""
    m = read_mode(root)
    back = m.get("return") if isinstance(m, dict) and isinstance(m.get("return"), dict) else None
    write_mode(root, back)
    return m
