"""Template v3 — the Mock 3.0 「组装 · Lint」 model (docs/TEMPLATE-PROTOCOL.md §7).

    ui(t)                    effective slots / views / prompts / budget: pack (+ mixins) < template.json
    slot_rows(t, root)       every slot instance (class × slot, or one shared per class) with have / stale / prompt
    fill_slot(t, id, data)   write an image into a slot — lands in the template (plot dir / soul dir / world-overlay)
    generate_slot(t, id)     the slot's recipe: builtin (map / scene / portrait / sprite) or a named prompt → image
    views_data(root, ui)     the views, bound to the run's current values (the right column of play3)
    lint_v3(t, root, …)      schema · asset · prompt · token (the Mock's four checks)
    contract(t, root)        worldlines.contract/0.1 + gen_ts / gen_gd

Placeholders in named prompts are ``{var.name}`` (a registered variable) or recipe context
(PROMPT_CTX, ``inst.<prop>``). Assets are content-hashed by their resolved inputs: inputs change → stale.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

PROMPT_CTX = ("world.name", "level.name", "nodes", "style", "place.name", "place.summary", "soul.name", "soul.persona",
              "time.day", "time.clock")
BUILTIN_RECIPES = ("map", "scene", "portrait", "sprite")
VIRTUAL_CLASSES = ("level",)  # slot classes that are not registry classes (the map tree's levels)
_PH = re.compile(r"\{([A-Za-z_][\w.*]*)\}")
_EXTS = (".webp", ".png", ".jpg", ".jpeg")
WIDGETS = ("table", "gauge", "bars", "meter", "sparkline", "list", "number")


def _h(o: Any) -> str:
    s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:12]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "__", s) or "_"


def _rj(p: Path, default: Any = None) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _wj(p: Path, d: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ── effective presentation ───────────────────────────────────────────────────

def ui(t: Any, pack: Any | None = None) -> dict[str, Any]:
    """Pack (+ mixins) declarations < the template's own ``ui`` (and top-level ``slots`` / ``views`` / ``panels`` / ``budget``) + ``recipe``."""
    from neonrp import packs
    from neonrp.template import world_dir

    pk = pack if pack is not None else packs.load(t.pack_name, world_dir(t))
    # template.json: "ui": {slots, views, panels, prompts, budget}; slots / views / panels / budget may also sit at the
    # top level. (Top-level "prompts" is the prompt-layer FILE list — named prompts live under ui.prompts.)
    over = dict(t.data.get("ui") or {}) if isinstance(t.data.get("ui"), dict) else {}
    for k in ("slots", "views", "panels", "budget"):
        if k in t.data:
            over[k] = t.data[k]
    out = packs.merge_ui(dict(pk.ui or {}), over)
    out["recipe"] = {"backend": "", "style": "", **(t.data.get("recipe") or {})}
    out.setdefault("budget", 20000)
    return out


# ── placeholders ─────────────────────────────────────────────────────────────

def placeholders(text: str) -> list[str]:
    return _PH.findall(text or "")


def fill(text: str, ctx: dict[str, Any], reg: Any = None) -> str:
    """Replace ``{name}`` with ctx / registered variable values; unknown names are left as they are."""
    def sub(m: re.Match) -> str:
        k = m.group(1)
        if k in ctx and ctx[k] is not None:
            return str(ctx[k])
        if reg is not None and k in reg.variables and reg.variables[k].value is not None:
            return str(reg.variables[k].value)
        return m.group(0)
    return _PH.sub(sub, text or "")


def known_placeholder(name: str, reg: Any) -> bool:
    return name in PROMPT_CTX or name.startswith("inst.") or bool(reg is not None and name in reg.variables)


# ── slot instances ───────────────────────────────────────────────────────────

def _cast(root: Path) -> list[tuple[str, str, Path]]:
    pt = _rj(root / "playthrough.json", {}) or {}
    out = []
    for s in pt.get("souls") or []:
        if isinstance(s, dict) and s.get("sid"):
            d = root / "souls" / f"{s['sid']}-{s.get('instance_id', '')}"
            out.append((str(s["sid"]), str((_rj(d / "soul.json", {}) or {}).get("name_local") or s["sid"]), d))
    return out


def _find(base: Path, stem: str) -> Path | None:
    for ext in _EXTS:
        p = base.with_name(stem + ext) if base.suffix else base / f"{stem}{ext}"
        if p.is_file():
            return p
    return None


def slot_rows(t: Any, root: Path, *, u: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every slot instance, evaluated against a built run ``root`` (template + world + overlay + plots)."""
    from neonrp.core import fallback_art
    from neonrp.core import worldmap as W
    from neonrp.core.registry import load_registry

    u = u or ui(t)
    reg = load_registry(root)
    try:
        tree = W.build_map_tree(root)
    except Exception:  # noqa: BLE001 — a world without a map tree has no level / place slots
        tree = {"nodes": {}}
    style = u["recipe"].get("style") or W.art_style(root)
    rows: list[dict[str, Any]] = []
    plot_entries = _plot_entry_index(t)

    def row(sl: dict[str, Any], inst: str, label: str, *, path: Path | None, prompt: str, input_hash: str | None = None,
            stale: bool = False, grown: bool = False, stand_in: dict[str, str] | None = None) -> None:
        have = bool(path and path.is_file())
        meta = _rj(_meta_path(root, sl, inst), {}) or {}
        if have and not stale and input_hash and meta.get("hash") and meta["hash"] != input_hash:
            stale = True
        rows.append({"slot": f"{sl['cls']}.{sl['slot']}:{inst}", "cls": sl["cls"], "name": sl["slot"], "inst": inst, "label": label,
                     "kind": sl.get("kind", "image"), "required": sl.get("required", "optional"),
                     "need": sl.get("required") == "publish", "have": have, "stale": bool(have and stale),
                     "path": (str(path.relative_to(root)) if path.resolve().is_relative_to(root.resolve()) else str(path)) if have and path else None,
                     "recipe": sl.get("recipe"),
                     "prompt": prompt, "fallback": sl.get("fallback"), "ratio": sl.get("ratio"), "grown": grown,
                     "plot": plot_entries.get(inst), **(stand_in or {})})

    for sl in u["slots"]:
        cls, recipe = str(sl.get("cls")), str(sl.get("recipe") or "")
        named = u["prompts"].get(recipe)
        if cls == "level":
            status = W.map_status(root, tree) if tree["nodes"] else {}
            for lv in W.map_levels(tree) if tree["nodes"] else []:
                n = tree["nodes"][lv]
                prompt = fill(named, {"level.name": n["name"], "style": style, "nodes": ", ".join(tree["nodes"][c]["name"] for c in n["children"]),
                                      "world.name": tree["nodes"].get("world", {}).get("name", "")}, reg) if named else W.map_prompt(root, tree, lv)
                row(sl, lv, n["name"], path=W.map_image_path(root, lv), prompt=prompt, stale=bool((status.get(lv) or {}).get("stale")))
        elif cls == "soul":
            for sid, name, d in _cast(root):
                stem = str(sl.get("slot"))
                alias = W.asset_alias(d, stem)   # soul.json assets: {"sprite": "portrait"} (10-24)
                p = _find(d / "assets", stem) or (_find(d / "assets", alias) if alias else None)
                if named:
                    prompt = fill(named, {"soul.name": name, "soul.persona": (d / "soul.md").read_text(encoding="utf-8")[:300] if (d / "soul.md").is_file() else "",
                                          "style": style}, reg)
                else:
                    try:
                        prompt = W.portrait_prompt(root, sid) if recipe in ("portrait", "sprite") else f"{name}, {style}"
                    except Exception:  # noqa: BLE001
                        prompt = name
                row(sl, sid, name, path=p, prompt=prompt, stand_in={"portrait_fallback": fallback_art.soul_dir(d)})
        elif cls == "player":  # the player's own picture: game/player/assets/<slot> — where the play screen reads the avatar
            for e in reg.of_class("player"):
                name = str(e.props.get("name") or e.id)
                prompt = fill(named, {"style": style}, reg) if named else f"{name}, {style}"
                row(sl, e.id, name, path=_find(root / get_data(root) / "player" / "assets", str(sl.get("slot"))), prompt=prompt,
                    stand_in={"portrait_fallback": fallback_art.player(root)})
        elif cls == "place" and recipe == "scene":
            for lv in W.map_levels(tree) if tree["nodes"] else []:
                if W.level_kind(tree, lv) != "town":
                    continue
                for c in tree["nodes"][lv]["children"]:
                    n = tree["nodes"][c]
                    prompt = fill(named, {"place.name": n["name"], "place.summary": n.get("summary") or "", "style": style}, reg) if named else W.scene_prompt(root, tree, c)
                    row(sl, c, n["name"], path=W.scene_image_path(root, c), prompt=prompt, grown=bool(n.get("plot")))
        else:
            if cls not in reg.classes:
                continue  # reported by lint (schema)
            if sl.get("scope") == "class":
                prompt = fill(named or f"{cls}, {style}", {"style": style}, reg)
                p = _find(root / "assets" / cls / str(sl["slot"]), "_class")
                row(sl, "*", f"类级共享({cls})", path=p, prompt=prompt, input_hash=_h(prompt))
                continue
            insts = reg.of_class(cls)
            if not insts:
                rows.append({"slot": f"{cls}.{sl['slot']}:∅", "cls": cls, "name": sl["slot"], "inst": "∅", "label": "(还没有实例)", "kind": sl.get("kind", "image"),
                             "required": sl.get("required", "optional"), "need": False, "have": False, "stale": False, "path": None,
                             "recipe": recipe or None, "prompt": "", "fallback": sl.get("fallback"), "ratio": sl.get("ratio"), "grown": False,
                             "empty": True, "plot": None})
                continue
            for e in insts:
                ctx = {"style": style, **{f"inst.{k}": v for k, v in (e.props or {}).items() if isinstance(v, (str, int, float))}, "inst.name": e.props.get("name") or e.id}
                own = e.props.get("image_prompt")  # an instance's own art direction beats the class recipe
                prompt = f"{own}, {style}" if isinstance(own, str) and own.strip() else fill(named or "{inst.name}, {style}", ctx, reg)
                pe = plot_entries.get(e.id)
                if pe and pe.get("image"):  # the run's installed copy of the plot folder carries the image
                    p = root / get_data(root) / "plots" / pe["pid"] / pe["image"]
                else:
                    p = _find(root / "assets" / cls / str(sl["slot"]), _slug(e.id))
                grown = bool((e.provenance or {}).get("turn"))
                # no picture yet: the stand-in the screens draw instead (core/fallback_art, 10-17) — a silhouette for a person, an icon for a thing
                fb = ({"portrait_fallback": fallback_art.portrait(e.props or {})} if reg.is_person(cls)
                      else {"icon_fallback": fallback_art.icon(e.props or {}, name=e.name)} if sl.get("slot") == "icon" else None)
                row(sl, e.id, str(e.props.get("name") or e.id), path=p if p and p.is_file() else None, prompt=prompt, input_hash=_h(prompt), grown=grown,
                    stand_in=fb)
    return rows


def get_data(root: Path) -> str:
    from neonrp.core.paths import get_data_dir_name

    return get_data_dir_name(root)


def _meta_path(root: Path, sl: dict[str, Any], inst: str) -> Path:
    return root / "assets" / str(sl["cls"]) / str(sl["slot"]) / f"{_slug(inst if inst != '*' else '_class')}.json"


def _plot_entry_index(t: Any) -> dict[str, dict[str, Any]]:
    """Entries that plots define (their image lives with the plot, recorded in plot.json)."""
    out = {}
    for rel in t.plots:
        pj = _rj(t.dir / rel / "plot.json", {}) or {}
        for eid, es in (pj.get("entries") or {}).items():
            if isinstance(es, dict):
                out[eid] = {"rel": rel, "pid": pj.get("id") or Path(rel).name, "image": (es.get("assets") or {}).get("image")}
    return out


def source_file(t: Any, slot: str) -> Path | None:
    """Where a filled slot's file really lives: plot dir · world-overlay · a brought-in soul · the bound world."""
    from neonrp.template import overlay_dir, world_dir

    row = next((r for r in cached_rows(t) if r["slot"] == slot), None)
    if not row or not row.get("have") or not row.get("path"):
        return None
    rel = Path(row["path"])
    cands: list[Path] = []
    pe = row.get("plot")
    if pe and pe.get("image"):
        cands.append(t.dir / pe["rel"] / pe["image"])
    ov = overlay_dir(t)
    if ov is not None:
        cands.append(ov / rel)
    if row["cls"] == "soul":
        from neonrp.template import linked_src

        src = next((s for s in t.souls if s.get("sid") == row["inst"] and (s.get("path") or s.get("lib"))), None)
        lsrc = linked_src(t, src) if src else None
        if lsrc is not None:
            cands.append(_find(lsrc / "assets", row["name"]) or t.dir / "_")
    wd = world_dir(t)
    if wd is not None:
        cands.append(wd / rel)
    bases = [t.dir.resolve()] + ([wd.resolve()] if wd is not None else [])
    if lsrc_ok := [linked_src(t, s) for s in t.souls if s.get("lib")]:   # a linked library soul's own portrait
        bases += [p for p in lsrc_ok if p is not None]
    for c in cands:
        if c and c.is_file() and any(c.resolve().is_relative_to(b) for b in bases):
            return c
    return None


# ── filling a slot (upload / generation) ─────────────────────────────────────

def _target(t: Any, root: Path, row: dict[str, Any], ext: str) -> tuple[Path, Any]:
    """Where a slot instance's file lives IN THE TEMPLATE + a function recording it."""
    from neonrp.core import worldmap as W
    from neonrp.template import overlay_dir

    ov = overlay_dir(t) or (t.dir / "world-overlay")
    cls, inst, name = row["cls"], row["inst"], row["name"]
    if cls == "level":
        rel = W.map_image_path(root, inst).relative_to(root)
        return ov / rel.with_suffix(ext), (lambda: None)
    if cls == "place" and row.get("recipe") == "scene":
        return ov / "assets" / "places" / f"{W._slug(inst)}{ext}", (lambda: None)
    if cls == "soul":
        src = next((s for s in t.souls if s.get("sid") == inst and s.get("path")), None)
        if src:
            return t.dir / str(src["path"]) / "assets" / f"{name}{ext}", (lambda: None)
        d = next((d for sid, _n, d in _cast(root) if sid == inst), None)
        if d is None:
            from neonrp.template import TemplateError

            raise TemplateError(f"soul {inst!r} is not cast")
        return ov / "souls" / d.name / "assets" / f"{name}{ext}", (lambda: None)
    if cls == "player":
        return ov / get_data(root) / "player" / "assets" / f"{name}{ext}", (lambda: None)
    pe = row.get("plot")
    if pe:
        fname = f"entry-{_slug(inst)}{ext}"

        def record() -> None:
            pj = _rj(t.dir / pe["rel"] / "plot.json", {}) or {}
            pj["entries"][inst].setdefault("assets", {})["image"] = f"assets/{fname}"
            _wj(t.dir / pe["rel"] / "plot.json", pj)
        return t.dir / pe["rel"] / "assets" / fname, record
    stem = "_class" if inst == "*" else _slug(inst)
    return ov / "assets" / cls / name / f"{stem}{ext}", (lambda: None)


def _check_image(data: bytes) -> None:
    from neonrp.template import MAX_UPLOAD, TemplateError

    if not data or len(data) > MAX_UPLOAD:
        raise TemplateError("image is empty or larger than 8 MB")
    if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise TemplateError("not a PNG / JPEG / WebP image")


def fill_slot(t: Any, slot: str, data: bytes, *, ext: str = ".png", root: Path | None = None) -> dict[str, Any]:
    """Write an image into a slot instance of the template. For a level map, the current layout's transform is
    frozen next to it (hotspots follow the data); for a hashed slot, the input hash is recorded (not stale)."""
    from neonrp.core import worldmap as W
    from neonrp.template import TemplateError

    _check_image(data)
    ext = ext.lower() if ext.lower() in _EXTS else ".png"
    with _scratch(t, root) as rt:
        u = ui(t)
        row = next((r for r in slot_rows(t, rt, u=u) if r["slot"] == slot), None)
        if row is None or row.get("empty"):
            raise TemplateError(f"unknown slot {slot!r}")
        dest, record = _target(t, rt, row, ext)
        if not dest.resolve().is_relative_to(t.dir.resolve()):
            raise TemplateError("slot escapes the template")
        for old in dest.parent.glob(dest.stem + ".*"):
            if old.suffix in _EXTS and old != dest:
                old.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        record()
        if row["cls"] == "level":
            tree = W.build_map_tree(rt)
            _wj(dest.with_suffix(".json"), {"level": row["inst"], "layout_hash": W.layout_hash(tree, row["inst"]),
                                            "fit": W.layout_fit(tree, row["inst"]), "backend": "upload"})
        elif row["cls"] not in ("soul", "player") and not (row["cls"] == "place" and row.get("recipe") == "scene") and not row.get("plot"):
            _wj(dest.with_suffix(".json"), {"hash": _h(row["prompt"]), "backend": "upload"})
    forget(t)
    with _scratch(t, None) as rt2:
        return next((r for r in slot_rows(t, rt2) if r["slot"] == slot), {"slot": slot, "have": True})


def generate_slot(t: Any, slot: str, *, prompt: str | None = None) -> dict[str, Any]:
    """Run the slot's recipe with the configured image backend and fill the slot with the result."""
    from neonrp.core import worldmap as W
    from neonrp.core.imagegen import generate_image
    from neonrp.template import TemplateError

    with _scratch(t, None) as rt:
        row = next((r for r in slot_rows(t, rt) if r["slot"] == slot), None)
        if row is None or row.get("empty"):
            raise TemplateError(f"unknown slot {slot!r}")
        if row["cls"] == "level" and not prompt:
            out = W.generate_map(rt, row["inst"])  # guide → image → frozen transform, all in the scratch run
            img = W.map_image_path(rt, row["inst"])
            dest, _ = _target(t, rt, row, img.suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dest)
            for extra in (W.map_meta_path(rt, row["inst"]), W.map_guide_path(rt, row["inst"])):
                if extra.is_file():
                    shutil.copy2(extra, dest.parent / extra.name)
            del out
        else:
            wide = row.get("ratio") in ("16:9", "3:2")
            tall = row.get("ratio") == "3:4"
            with tempfile.TemporaryDirectory() as tmp:
                png = generate_image(prompt or row["prompt"], Path(tmp), width=1344 if wide else 896 if tall else 1024,
                                     height=768 if wide else 1152 if tall else 1024)
                return fill_slot(t, slot, png.read_bytes(), ext=png.suffix or ".png")
    with _scratch(t, None) as rt2:
        return next((r for r in slot_rows(t, rt2) if r["slot"] == slot), {"slot": slot, "have": True})


# A thumbnail / slot list must not rebuild the whole world every time (one build ≈ 1 s; the Lint panel asks for ~15 files):
# slot rows are cached per template folder and reused until any file in it changes (mtime / size signature).
_ROWS: dict[str, tuple[str, list[dict[str, Any]]]] = {}
# 10-15 (chat-fe / ios2: the first portrait after start took ~30 s): the signature walks every file of the template, so
# it is itself remembered for SIG_TTL seconds (an edit shows up within that), and a cold build happens once per template
# even when a screen asks for twenty pictures at the same moment (one lock per template folder).
SIG_TTL = 2.0
_SIGS: dict[str, tuple[float, str]] = {}
_BUILD_LOCKS: dict[str, threading.Lock] = {}
_BUILD_LOCKS_LOCK = threading.Lock()


def _signature(t: Any) -> str:
    import time

    key = str(Path(t.dir).resolve())
    hit = _SIGS.get(key)
    if hit is not None and time.monotonic() - hit[0] < SIG_TTL:
        return hit[1]
    sig = _walk_signature(t)
    _SIGS[key] = (time.monotonic(), sig)
    return sig


def forget(t: Any) -> None:
    """A write through the engine (an upload, a creation save): the next look rebuilds the signature at once instead of
    trusting the one remembered for SIG_TTL — otherwise a picture just put in reads as missing for up to two seconds."""
    _SIGS.pop(str(Path(t.dir).resolve()), None)


def _walk_signature(t: Any) -> str:
    h = hashlib.sha1()
    for p in sorted(Path(t.dir).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            st = p.stat()
            h.update(f"{p.relative_to(t.dir)}|{st.st_mtime_ns}|{st.st_size}\n".encode())
    return h.hexdigest()


def cached_rows(t: Any) -> list[dict[str, Any]]:
    """``slot_rows`` against a scratch build, cached until the template folder changes."""
    key, sig = str(Path(t.dir).resolve()), _signature(t)
    hit = _ROWS.get(key)
    if hit is None or hit[0] != sig:
        with _BUILD_LOCKS_LOCK:
            lock = _BUILD_LOCKS.setdefault(key, threading.Lock())
        with lock:
            hit = _ROWS.get(key)
            if hit is None or hit[0] != sig:  # the request that held the lock may have built it already
                with _scratch(t, None) as root:
                    hit = (sig, slot_rows(t, root))
                _ROWS[key] = hit
    return [dict(r) for r in hit[1]]


def soul_file_fast(t: Any, name: str, sid: str) -> Path | None:
    """A soul's picture (``soul.<name>:<sid>``) found without building the world, in the order :func:`source_file`
    looks: the overlay's copy of the world's soul folder · the brought-in soul (library / template path) · the world's
    own soul folder. None = not there — the caller falls back to the full slot rows."""
    from neonrp.template import _world_souls, draw_souls, linked_src, overlay_dir, world_dir

    wd = world_dir(t)
    native = _world_souls(wd).get(sid) if wd is not None else None
    row = next((s for s in draw_souls(t, seed="", everyone=True) if s.get("sid") == sid), None)
    cands: list[Path] = []
    ov = overlay_dir(t)
    if ov is not None and native:
        cands.append(ov / "souls" / Path(native["dir"]).name / "assets")
    src = linked_src(t, row) if row else None
    if src is not None:
        cands.append(src / "assets")
    if native:
        cands.append(Path(native["dir"]) / "assets")
    hit = next((p for c in cands if (p := _find(c, name)) is not None), None)
    if hit is not None:
        return hit
    from neonrp.core.worldmap import asset_alias

    alias = next((a for d in (Path(native["dir"]) if native else None, src) if d is not None and (a := asset_alias(d, name))), None)
    return next((p for c in cands if (p := _find(c, alias)) is not None), None) if alias else None   # soul.json assets: {"sprite": "portrait"}


_SWEPT = [0.0]


def _sweep_stale_scratch(max_age: float = 3600.0) -> None:
    """Throwaway builds a killed process never cleaned (10-08: 110 left in the temp dir · 872 MB). At most once a minute,
    remove ``wl-tpl-v3-*`` older than an hour — a live build never takes that long."""
    import time

    now = time.time()
    if now - _SWEPT[0] < 60:
        return
    _SWEPT[0] = now
    for d in Path(tempfile.gettempdir()).glob("wl-tpl-v3-*"):
        try:
            if d.is_dir() and now - d.stat().st_mtime > max_age:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


class _scratch:
    """A throwaway build of the template (plots installed) to evaluate slots against."""

    def __init__(self, t: Any, root: Path | None):
        self.t, self.given, self.tmp = t, root, None

    def __enter__(self) -> Path:
        if self.given is not None:
            return self.given
        from neonrp.template import build

        _sweep_stale_scratch()
        self.tmp = Path(tempfile.mkdtemp(prefix="wl-tpl-v3-"))
        build(self.t, self.tmp / "run", cast_all=True)
        return self.tmp / "run"

    def __exit__(self, *exc: Any) -> None:
        if self.tmp is not None:
            shutil.rmtree(self.tmp, ignore_errors=True)


# ── views ────────────────────────────────────────────────────────────────────

def expand_bind(pattern: str, reg: Any, *, town: str = "*") -> list[str]:
    p = pattern.replace("{town}", town or "*")
    if "*" not in p:
        return [p] if p in reg.variables else []
    rx = re.compile("^" + re.escape(p).replace(r"\*", r"[^.]+") + "$")
    return [k for k in reg.variables if rx.match(k)]


def views_data(root: Path, u: dict[str, Any] | None = None, t: Any = None) -> list[dict[str, Any]]:
    """The declared views bound to the run's current state (``{town}`` = the player's town)."""
    from neonrp import packs
    from neonrp.core.registry import load_registry

    reg = load_registry(root)
    if u is None:
        pk = packs.resolve(root)
        u = packs.merge_ui(dict(pk.ui or {}), (_rj(root / get_data(root) / "meta" / "template.json", {}) or {}).get("ui") or {})
    town = str(reg.player_location or "").split("/")[0] or "*"
    out = []
    for v in u.get("views") or []:
        data: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        for b in v.get("bind") or []:
            if b.startswith("class:"):
                cls = b[6:]
                if cls in reg.classes:
                    rows += [{"id": e.id, "name": e.props.get("name") or e.id, **{k: x for k, x in e.props.items() if isinstance(x, (str, int, float, bool))}}
                             for e in reg.of_class(cls)][-30:]
                continue
            for k in expand_bind(b, reg, town=town):
                spec = reg.variables[k]
                data[k] = {"value": spec.value, "min": spec.min, "max": spec.max}
        out.append({"id": v.get("id"), "title": v.get("title"), "widget": v.get("widget"), "layout": v.get("layout") or {},
                    "actions": [a for a in v.get("actions") or [] if a in reg.actions], "vars": data, "rows": rows})
    return sorted(out, key=lambda x: ((x["layout"] or {}).get("area", "right"), (x["layout"] or {}).get("order", 99)))


# ── lint: the Mock's four checks ─────────────────────────────────────────────

def lint_v3(t: Any, root: Path, *, u: dict[str, Any] | None = None, publish: bool = True) -> list[dict[str, Any]]:
    """schema · asset · prompt · token. ``publish`` = release-level (missing / stale required assets block)."""
    from neonrp.core.registry import load_registry

    u = u or ui(t)
    reg = load_registry(root)
    out: list[dict[str, Any]] = []
    add = lambda lvl, code, where, msg: out.append({"level": lvl, "code": code, "where": where, "msg": msg})  # noqa: E731
    # 1 schema closure: views bind registered vars, view actions have handlers, slot classes exist
    for v in u["views"]:
        vid = f"views.{v.get('id')}"
        if v.get("widget") and v["widget"] not in WIDGETS:
            add("warn", "schema.view", vid, f"unknown widget {v['widget']!r} (known: {', '.join(WIDGETS)})")
        for b in v.get("bind") or []:
            if b.startswith("class:"):
                if b[6:] not in reg.classes:
                    add("block", "schema.view", vid, f"binds {b} — no such class")
            elif not expand_bind(b, reg):
                add("block", "schema.view", vid, f"binds {b} — no registered variable matches")
        for a in v.get("actions") or []:
            spec = reg.actions.get(a)
            if spec is None or not spec.enabled:
                add("block", "schema.view", vid, f"action {a} has no handler (install the mixin that provides it, or drop it)")
    for sl in u["slots"]:
        if sl.get("cls") not in reg.classes and sl.get("cls") not in VIRTUAL_CLASSES:
            add("warn", "schema.slot", f"slots.{sl.get('cls')}.{sl.get('slot')}", "slot on a class this world does not have (no instances)")
        r = sl.get("recipe")
        if r and r not in BUILTIN_RECIPES and r not in u["prompts"]:
            add("block", "schema.slot", f"slots.{sl.get('cls')}.{sl.get('slot')}", f"recipe {r!r} is neither builtin nor a named prompt")
    # 2 assets
    rows = slot_rows(t, root, u=u)
    missing_opt = 0
    for r in rows:
        if r.get("empty"):
            continue
        w = f"slots.{r['slot']}"
        if r["stale"]:
            add("block" if publish and r["need"] else "warn", "asset.stale", w, f"{r['label']}:输入已变(过期),要重跑配方")
        elif not r["have"] and r["need"]:
            add("block" if publish else "warn", "asset.missing", w, f"{r['label']}:发布必需,还没填")
        elif not r["have"]:
            missing_opt += 1
    if missing_opt:
        add("warn", "asset.optional", "slots", f"{missing_opt} 个可选槽位没填(有兜底的用兜底)")
    # 3 prompts: every placeholder resolves
    for pid, text in u["prompts"].items():
        bad = [p for p in placeholders(text) if not known_placeholder(p, reg)]
        if bad:
            add("block", "prompt.placeholder", f"prompts.{pid}", "引用 " + " ".join(f"{{{b}}}" for b in bad) + " —— 既不是注册变量也不是配方上下文")
    from neonrp.core.adv import prompt_spec

    for e in prompt_spec(root).get("entries") or []:
        txt = e.get("text") if isinstance(e.get("text"), str) else " ".join(map(str, (e.get("text") or {}).values()))
        bad = [p for p in placeholders(txt or "") if not known_placeholder(p, reg) and "." in p]
        if bad:
            add("warn", "prompt.placeholder", f"prompt.entries.{e.get('id')}", "引用 " + " ".join(f"{{{b}}}" for b in bad) + " —— 未注册,会原样输出")
    # 4 token budget: measured from real runs of this template
    per, n = measured_tokens(t)
    budget = int(u.get("budget") or 0)
    if not n:
        add("warn", "token.unmeasured", "budget", "还没有回合——用这个模板玩一回合才量得出每回合 token")
    elif budget and per > budget:
        add("block" if publish else "warn", "token.over", "budget", f"每回合均值 {per:,} token,超过预算 {budget:,}")
    elif budget and per > budget * 0.8:
        add("warn", "token.near", "budget", f"每回合均值 {per:,} token / 预算 {budget:,}({round(per / budget * 100)}%)")
    return out


def measured_tokens(t: Any, *, last: int = 30) -> tuple[int, int]:
    """Average world-side tokens per turn over this template's recent local runs (traces' timing.v3.usage)."""
    from neonrp.core.orchestration_trace import read_turn_traces
    from neonrp.worlds import PLAYS_HOME

    tot, n = 0, 0
    runs = sorted(PLAYS_HOME.glob(f"tpl-{t.id}-*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5] if PLAYS_HOME.is_dir() else []
    for r in runs:
        branch = str((_rj(r / ".neonrp" / "manifest.json", {}) or {}).get("current_branch") or "main")
        for tr in read_turn_traces(r, branch)[-last:]:
            us = ((tr.get("timing") or {}).get("v3") or {}).get("usage") or {}
            s = int(us.get("total_tokens") or (int(us.get("prompt_tokens") or 0) + int(us.get("completion_tokens") or 0)))
            if s:
                tot, n = tot + s, n + 1
    return (round(tot / n) if n else 0), n


# ── contract + codegen ───────────────────────────────────────────────────────

_GRAPH_RUNS: dict[str, tuple[str, Path]] = {}


def _graph_run(t: Any) -> Path:
    """One built run per template for the orchestration editor's reads (graph · lint), kept until the template folder
    changes (10-17 审计 1.6: every graph / lint request used to build a throwaway run — seconds each, and the editor asks
    for one per template; a busy engine then dropped the page's /api/v1/meta → 「连不上引擎」). Only read, never played."""
    import atexit

    from neonrp.template import build

    key, sig = str(Path(t.dir).resolve()), _signature(t)
    hit = _GRAPH_RUNS.get(key)
    if hit is not None and hit[0] == sig and hit[1].is_dir():
        return hit[1]
    with _BUILD_LOCKS_LOCK:
        lock = _BUILD_LOCKS.setdefault("graph:" + key, threading.Lock())
    with lock:
        hit = _GRAPH_RUNS.get(key)
        if hit is not None and hit[0] == sig and hit[1].is_dir():
            return hit[1]
        tmp = Path(tempfile.mkdtemp(prefix="wl-tpl-graph-"))
        build(t, tmp / "run", cast_all=True)
        old = _GRAPH_RUNS.get(key)
        _GRAPH_RUNS[key] = (sig, tmp / "run")
        if old is not None:
            shutil.rmtree(old[1].parent, ignore_errors=True)
        if len(_GRAPH_RUNS) == 1:
            atexit.register(lambda: [shutil.rmtree(r.parent, ignore_errors=True) for _, r in list(_GRAPH_RUNS.values())])
        return tmp / "run"


def _template(ref: str) -> Any:
    from neonrp import template as TP

    p = Path(ref).expanduser()
    if not (p / "template.json").is_file():
        hit = TP.discover().get(ref)
        if hit is None:
            raise KeyError(f"no template {ref!r}")
        p = hit
    return TP.load(p)


def graph_of(ref: str) -> dict[str, Any]:
    """A template's orchestration graph without a play session (10-06: the orchestration editor switches between
    templates): read off a run built the way a new game builds it (kept per template, :func:`_graph_run`).
    ``ref`` = a template id or folder."""
    from neonrp.core import orchestration

    t = _template(ref)
    rt = _graph_run(t)
    return {"template": t.id, "pack": t.pack_name, "graph": orchestration.graph(rt), "default": orchestration.default_graph(rt)}


def lint_graph_of(ref: str, g: dict[str, Any]) -> list[dict[str, str]]:
    """``orchestration.lint_runnable`` for a draft graph against a template (10-07: the editor's unsaved edits get the same
    warnings a saved graph gets). Against the same kept run as :func:`graph_of`; nothing is written."""
    from neonrp.core import orchestration

    rt = _graph_run(_template(ref))
    return orchestration.lint_runnable(rt, g) + orchestration.lint_step_params(rt, g)


def contract(t: Any, root: Path, *, u: dict[str, Any] | None = None) -> dict[str, Any]:
    from neonrp.core.registry import load_registry

    u = u or ui(t)
    reg = load_registry(root)
    ops = [{"op": a.op, "kind": a.kind, "fields": {f: "any" for f in a.fields}, "owner": (a.handler.split(":")[0].rsplit(".", 1)[-1] if ":" in a.handler else "core")}
           for a in reg.actions.values() if a.enabled and a.scope != "souls"]
    c = {
        "$schema": "worldlines.contract/0.1", "world": t.id, "template": {"base": t.pack_name.split("+")[0], "mixins": t.pack_name.split("+")[1:]},
        "vars": [{"name": v.name, "type": v.type, **({"min": v.min} if v.min is not None else {}), **({"max": v.max} if v.max is not None else {}),
                  "at": v.path, **({"readonly": True} if v.readonly else {})} for v in reg.variables.values()],
        "classes": [{"name": k, "policy": getattr(c, "policy", "auto"), "required": list(c.required),
                     "slots": [s["slot"] for s in u["slots"] if s.get("cls") == k]} for k, c in reg.classes.items()],
        "ops": ops,
        "events": ["var.changed", "entity.created", "entry.entered", "flag.set", "trigger.fired", "ending.reached", "pending", "commit"],
        # contract 1.0 beat events (R6, core/beat_events.py) — on the turn stream (SSE) next to chunk / done
        "beat_events": list(_beat_events()),
        "triggers": [{"id": tr.id, "when": tr.when} for tr in reg.triggers.values()],
        "slots": [{"id": f"{s['cls']}.{s['slot']}", "kind": s.get("kind", "image"), "required": s.get("required", "optional"),
                   **({"ratio": s["ratio"]} if s.get("ratio") else {}), **({"hotspots": True} if s.get("hotspots") else {}),
                   "dir": f"assets/{s['cls']}/{s['slot']}/"} for s in u["slots"]],
        "views": [{k: v.get(k) for k in ("id", "title", "widget", "bind", "actions", "layout")} for v in u["views"]],
        "panels": [{k: p.get(k) for k in ("id", "tag", "tool", "format", "schema", "layout") if k in p} for p in u.get("panels") or []],
        "transport": {"rpc": "POST /api/v1/play/engine/{cmd,tick,rollback}  GET /api/v1/play/schema[/history|/events]",
                      "stream": "GET /api/v1/play/schema/stream?pattern=…  (SSE)"},
    }
    try:  # the pack's stop tags / layer switches / exits / panels / engine-initiated points (engine side, core/interaction)
        from neonrp.core.interaction import interaction_points

        c["interaction"] = interaction_points(root, reg)
    except Exception:  # noqa: BLE001 — older engines without the module still export the rest
        c["interaction"] = {}
    c["version"] = f"{t.version or '0'}"
    c["hash"] = _h({k: v for k, v in c.items() if k != "version"})
    return c


def _beat_events() -> tuple[str, ...]:
    from neonrp.core.beat_events import EVENTS

    return EVENTS


_TS = {"int": "number", "float": "number", "str": "string", "bool": "boolean", "any": "unknown"}
_GD = {"int": "int", "float": "float", "str": "String", "bool": "bool", "any": "Variant"}


def _ident(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "x"


def _pascal(s: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", s) if w) or "World"


def gen_ts(c: dict[str, Any]) -> str:
    cls = _pascal(c["world"])
    L = [f"// generated from worldlines.contract/0.1 · {c['world']} {c['version']} · hash {c['hash']} — do not edit",
         f"export const CONTRACT_HASH = '{c['hash']}';", "", f"export interface {cls}Vars {{"]
    L += [f"  '{v['name']}': {_TS.get(v['type'], 'unknown')};" + (f" // {v.get('min', '')}…{v.get('max', '')}" if "min" in v or "max" in v else "") for v in c["vars"]]
    L += ["}", "", f"export interface {cls}Ops {{"]
    L += [f"  {o['op']}: {{ {'; '.join(f'{f}: unknown' for f in o['fields'])} }}; // {o['owner']}" for o in c["ops"]]
    L += ["}", "", f"export type {cls}Class = " + (" | ".join(f"'{k['name']}'" for k in c["classes"]) or "never") + ";",
          "export type ProposeResult = { applied: unknown[]; refused: { op: unknown; why: string }[]; ended?: unknown };",
          "export type BeatEvent = " + (" | ".join(f"'{e}'" for e in c.get("beat_events") or []) or "never") + ";", "",
          f"export class {cls}World {{",
          "  constructor(private base = '') {}",
          "  private post(path: string, body: unknown) { return fetch(`${this.base}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()); }",
          "  schema() { return fetch(`${this.base}/api/v1/play/schema`).then(r => r.json()); }",
          "  say(text: string) { return this.post('/cmd', { text }); }",
          "  tick(turns = 1) { return this.post('/api/v1/play/engine/tick', { turns }); }",
          "  on(pattern: string, fn: (e: unknown) => void) { const es = new EventSource(`${this.base}/api/v1/play/schema/stream?pattern=${encodeURIComponent(pattern)}`); es.onmessage = m => fn(JSON.parse(m.data)); return () => es.close(); }",
          "}"]
    return "\n".join(L) + "\n"


def gen_gd(c: dict[str, Any]) -> str:
    cls = _pascal(c["world"])
    L = [f"# generated from worldlines.contract/0.1 · {c['world']} {c['version']} · hash {c['hash']} — do not edit",
         f"class_name {cls}World", "extends Node", "", f'const CONTRACT_HASH := "{c["hash"]}"', "",
         "signal changed(var_name: String, from, to)", "signal ended(ending: Dictionary)",
         "signal beat(event: String, data: Dictionary)  # " + " · ".join(c.get("beat_events") or []), "", "# ── closed schema ──"]
    L += [f"var {_ident(v['name'])}: {_GD.get(v['type'], 'Variant')}" + (f"  # {v.get('min', '')}…{v.get('max', '')}" if "min" in v or "max" in v else "") for v in c["vars"]]
    L += ["", "const VAR_NAMES := {"] + [f'\t"{v["name"]}": "{_ident(v["name"])}",' for v in c["vars"]] + ["}", "",
          "const OPS := [" + ", ".join(f'"{o["op"]}"' for o in c["ops"]) + "]", "",
          "var base_url := \"http://127.0.0.1:8787\"", "",
          "func apply_change(var_name: String, value) -> void:",
          "\tif VAR_NAMES.has(var_name):",
          "\t\tvar old = get(VAR_NAMES[var_name])",
          "\t\tset(VAR_NAMES[var_name], value)",
          "\t\tchanged.emit(var_name, old, value)"]
    return "\n".join(L) + "\n"
