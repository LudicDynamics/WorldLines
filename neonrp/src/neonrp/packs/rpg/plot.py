"""Plot packs (剧情包) — a lintable bundle of things that push a story: key items, new places,
if/else (triggers), endings, and the assets the front end shows for them.

    plots/<id>/plot.json
    {
      "id": "P01", "title": "雾里的钥匙",
      "stages": ["起", "承", "转", "合"],                       # a variable P01.stage is declared for you
      "classes":  {"clue": {...ClassSpec...}},                # optional custom classes
      "vars":     {"P01.trust": {"type": "int", "min": 0, "max": 5, "doc": "…"}},   # stored in game/meta/plot_vars.json unless path/key given
      "entries":  {"I900": {"class": "item",  "name": "锈钥匙", "parent": "T001/well",
                            "assets": {"image": "key.png"}},
                   "T001/crypt": {"class": "place", "name": "地窖", "parent": "T001", "links": ["T001/well"],
                            "assets": {"image": "crypt.png", "bgm": "crypt.mp3"}}},
      "triggers": {"P01.key_found": {"when": {"text": "narration"}, "if": [{"text": "钥匙"}], "once": true,     # WHEN / IF / THEN / ELSE
                                     "then": [{"to": "var", "var": "P01.stage", "set": 1},
                                              {"to": "narration", "text": "钥匙冰得咬手。"}]},
                   "P01.end_fog":   {"when": {"var": "P01.stage"}, "if": [{"var": "P01.stage", ">=": 3}],
                                     "then": [{"to": "end", "ending": "E01"}],
                                     "else": [{"to": "narration", "text": "雾还没散。"}]}},
      "endings":  {"E01": {"title": "雾散", "assets": {"image": "e01.png", "video": "e01.mp4"}}}
    }

The engine understands only the closed-schema part (vars / classes / entries / triggers = the
five registry tables). Assets are opaque to it: lint checks that every referenced file exists
and has a kind the front end knows how to show; ``assets(plot)`` hands the front end a flat
list. ``install(root, plot_dir)`` registers the pack into a world through ``registry.register``
(so every world-side check applies) and copies the folder to ``game/plots/<id>/`` so the
bundle travels with the world.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from neonrp.core import scene_cg as _scg
from neonrp.core import triggers as _triggers
from neonrp.core.paths import get_data_dir_name
from neonrp.core.registry import Registry, load_registry, register, write_staged

# what the front end can show, by file extension — the lint's whole knowledge of assets
ASSET_KINDS: dict[str, tuple[str, ...]] = {
    "image": (".png", ".jpg", ".jpeg", ".webp", ".gif"),
    "portrait": (".png", ".jpg", ".jpeg", ".webp"),
    "video": (".mp4", ".webm"),
    "audio": (".mp3", ".ogg", ".wav", ".m4a"),
    "bgm": (".mp3", ".ogg", ".wav", ".m4a"),
    "sfx": (".mp3", ".ogg", ".wav"),
}
ENTRY_CLASSES = ("item", "place", "npc")  # built-ins a plot may add; custom classes come from plot.classes / the world
TOP_KEYS = ("id", "title", "stages", "stage_var", "stage_cg", "classes", "vars", "entries", "triggers", "endings", "notes", "truth_quiz",
            "prompt", "reveal", "collect", "created_by")  # prompt: appended to the narrator · reveal: the truth (mode.reveal) · collect / created_by: template/creation


@dataclass
class Problem:
    level: str  # error | warn
    where: str  # e.g. "entries.I900.assets.image"
    msg: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.where}: {self.msg}"


def load(plot_dir: Path) -> dict[str, Any]:
    p = Path(plot_dir) / "plot.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{p}: plot.json must be an object")
    return data


def stage_var_name(plot: dict[str, Any]) -> str | None:
    """Which variable is this plot's stage: ``stage_var`` when the plot names one (a world variable, one of its own
    ``vars``), else the ``<id>.stage`` that ``stages`` declares; None = the plot has no stages."""
    if isinstance(plot.get("stage_var"), str) and plot["stage_var"].strip():
        return plot["stage_var"].strip()
    stages = plot.get("stages")
    return f"{plot['id']}.stage" if isinstance(stages, list) and stages else None


def stage_var(plot: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The stage variable a plot with `stages` declares implicitly: <id>.stage int 0..n-1 (none when ``stage_var``
    names another variable — that one is declared where it lives)."""
    stages = plot.get("stages")
    if not (isinstance(stages, list) and stages) or stage_var_name(plot) != f"{plot.get('id')}.stage":
        return None
    # readonly (10-06 pct-house: the transition wrote P01.stage 3→1 and the true ending's gate was lost): the stage is the
    # plot's own — its triggers move it (their var emits bypass the model's verify); the model only reads it
    return f"{plot['id']}.stage", {"type": "int", "min": 0, "max": len(stages) - 1, "default": 0, "readonly": True,
                                   "doc": " → ".join(f"{i}={_stage_name(s)}" for i, s in enumerate(stages))}


def _stage_name(s: Any) -> str:
    """A ``stages`` entry: a name, or ``{name, goal}`` (core/objective, 10-15)."""
    from neonrp.core.objective import stage_name

    return stage_name(s)


# ── lint ─────────────────────────────────────────────────────────────────────

def lint(plot: dict[str, Any], plot_dir: Path | None = None, root: Path | None = None) -> list[Problem]:
    """Every problem a plot pack has, before it touches a world. ``root`` (a world) makes cross
    references (parents / links / souls / variables that live in the world) checkable; without it,
    references outside the plot are warnings."""
    out: list[Problem] = []
    err = lambda w, m: out.append(Problem("error", w, m))  # noqa: E731
    warn = lambda w, m: out.append(Problem("warn", w, m))  # noqa: E731

    pid = str(plot.get("id") or "").strip()
    if not pid:
        err("id", "plot needs an id")
    if not str(plot.get("title") or "").strip():
        err("title", "plot needs a title")
    for k in plot:
        if k not in TOP_KEYS:
            warn(k, f"unknown top-level key (known: {', '.join(TOP_KEYS)})")
    for k in ("classes", "vars", "entries", "triggers", "endings"):
        if k in plot and not isinstance(plot[k], dict):
            err(k, "must be an object keyed by id")
    if "truth_quiz" in plot:  # 10-15: the sandbox mystery's three questions (core/truth_quiz)
        from neonrp.core import truth_quiz as _tq

        for pr in _tq.validate(plot["truth_quiz"]):  # warn here: a template's lint grades it by zone (truth_quiz.lint)
            warn("truth_quiz", pr)
    if not all(isinstance(plot.get(k, {}), dict) for k in ("classes", "vars", "entries", "triggers", "endings")):
        return out

    reg: Registry | None = load_registry(root) if root else None
    classes = dict(plot.get("classes") or {})
    entries = dict(plot.get("entries") or {})
    endings = dict(plot.get("endings") or {})
    trig = dict(plot.get("triggers") or {})
    vars_ = dict(plot.get("vars") or {})
    sv = stage_var(plot)
    if sv:
        vars_.setdefault(sv[0], sv[1])

    def known_entry(eid: str) -> bool:
        return eid in entries or bool(reg and eid in reg.entries)

    def known_var(v: str) -> bool:
        return v in vars_ or bool(reg and v in reg.variables)

    known_classes = set(ENTRY_CLASSES) | set(classes) | (set(reg.classes) if reg else set())

    # entries: key items / new places / npcs / custom-class instances
    for eid, spec in entries.items():
        w = f"entries.{eid}"
        if not isinstance(spec, dict):
            err(w, "must be an object")
            continue
        cls = str(spec.get("class") or "")
        if cls not in known_classes:
            err(f"{w}.class", f"unknown class {cls!r} (built-in: {', '.join(ENTRY_CLASSES)}; declare others under classes)")
        if not str(spec.get("name") or (spec.get("props") or {}).get("name") or "").strip():
            err(f"{w}.name", "needs a name")
        parent = spec.get("parent")
        if cls == "place":
            if not parent:
                err(f"{w}.parent", "a place needs its town as parent")
            elif not known_entry(str(parent)):
                (err if reg else warn)(f"{w}.parent", f"unknown town {parent!r}")
            links = spec.get("links") or []
            if not links:
                warn(f"{w}.links", "a place with no links is unreachable by move_to")
            for lk in links:
                if not known_entry(str(lk)):
                    (err if reg else warn)(f"{w}.links", f"unknown place {lk!r}")
        elif parent and not known_entry(str(parent)):
            (err if reg else warn)(f"{w}.parent", f"unknown parent {parent!r}")
        _lint_assets(spec.get("assets"), plot_dir, w, out)

    for vid, spec in vars_.items():
        if not isinstance(spec, dict) or str(spec.get("type") or "") not in ("int", "float", "bool", "str"):
            err(f"vars.{vid}", "needs a type int|float|bool|str")

    # triggers = the if / else; endings must be declared and reachable
    emitted_endings: set[str] = set()
    for tid, spec in trig.items():
        w = f"triggers.{tid}"
        if not isinstance(spec, dict):
            err(w, "must be an object")
            continue
        for pr in _triggers.validate(None, spec):
            err(w, pr)
        n = _triggers.normalize(spec)
        when = n["when"]
        if "var" in when and not known_var(str(when["var"])):
            (err if reg else warn)(f"{w}.when.var", f"unknown variable {when['var']!r}")
        if "entry" in when and when["entry"] != "*" and not known_entry(str(when["entry"])):
            (err if reg else warn)(f"{w}.when.entry", f"unknown entry {when['entry']!r}")
        for i, c in enumerate(n["if"]):
            for sub in ([c] + list(c.get("any") or [])) if isinstance(c, dict) else []:
                if "var" in sub and not known_var(str(sub["var"])):
                    (err if reg else warn)(f"{w}.if[{i}]", f"unknown variable {sub['var']!r}")
                if "entry" in sub and not known_entry(str(sub["entry"])):
                    (err if reg else warn)(f"{w}.if[{i}]", f"unknown entry {sub['entry']!r}")
                if "at" in sub and str(sub["at"]) != "player" and not known_entry(str(sub["at"])):
                    (err if reg else warn)(f"{w}.if[{i}]", f"unknown place {sub['at']!r}")
        for branch in ("then", "else"):
            for i, e in enumerate(n[branch]):
                if not isinstance(e, dict):
                    continue
                to = str(e.get("to") or "")
                if to == "end":
                    eid = str(e.get("ending") or "")
                    emitted_endings.add(eid)
                    if eid not in endings:
                        err(f"{w}.{branch}[{i}]", f"ending {eid!r} is not declared under endings")
                elif to == "var" and not known_var(str(e.get("var") or "")):
                    (err if reg else warn)(f"{w}.{branch}[{i}]", f"unknown variable {e.get('var')!r}")
                elif to == "soul" and reg:
                    sid = reg.resolve(str(e.get("who") or ""), cls="soul")
                    if not sid:
                        err(f"{w}.{branch}[{i}]", f"unknown soul {e.get('who')!r}")
    if root is not None:  # a rule pack ends the game with its own triggers (狼人杀); a plot ending of the same id only dresses it (E1)
        try:
            from neonrp.packs import resolve as _resolve_pack

            for tspec in (_resolve_pack(Path(root)).triggers or {}).values():
                for branch in ("then", "else"):
                    for e in (tspec.get(branch) or []) if isinstance(tspec, dict) else []:
                        if isinstance(e, dict) and e.get("to") == "end" and e.get("ending"):
                            emitted_endings.add(str(e["ending"]))
        except Exception:  # noqa: BLE001 — no pack: only the plot's own triggers count
            pass
    for eid, spec in endings.items():
        w = f"endings.{eid}"
        if not isinstance(spec, dict) or not str(spec.get("title") or "").strip():
            err(w, "needs a title")
            continue
        if eid not in emitted_endings:
            warn(w, "no trigger emits this ending (unreachable)")
        _lint_assets(spec.get("assets"), plot_dir, w, out)
    if sv and not any(isinstance(s, dict) and any(isinstance(e, dict) and e.get("to") == "var" and e.get("var") == sv[0]
                                                    for e in _triggers.normalize(s)["then"] + _triggers.normalize(s)["else"]) for s in trig.values()):
        warn("stages", f"stages declared but no trigger moves {sv[0]}")
    for i, st in enumerate(plot.get("stages") or [] if isinstance(plot.get("stages"), list) else []):  # a name, or {name, goal} (10-15)
        if isinstance(st, dict):
            if not _stage_name(st).strip():
                err(f"stages[{i}]", "a stage object needs a name")
            g = st.get("goal")
            if g is not None and not isinstance(g, (str, dict)):
                err(f"stages[{i}].goal", "a line for the player: a string or {zh, en, ja, ko}")
            au = st.get("audio")  # 10-15: what plays while this stage is current (core/audio)
            if au is not None:
                from neonrp.core import audio as _audio

                if not isinstance(au, dict):
                    err(f"stages[{i}].audio", "{mood?, bgm?, ambient?}")
                else:
                    if au.get("mood") not in (None, *_audio.MOODS):
                        err(f"stages[{i}].audio.mood", f"one of {', '.join(_audio.MOODS)}")
                    tdir = Path(plot_dir).parents[1] if plot_dir is not None else None  # <template>/plots/<id>: files are the template's
                    tdir = tdir if tdir is not None and (tdir / "template.json").is_file() else None
                    for k, kind in (("bgm", "music"), ("ambient", "ambient")):
                        why = _audio.check_ref(au.get(k), kind, tdir)
                        if why:
                            err(f"stages[{i}].audio.{k}", why)
        elif not isinstance(st, str):
            err(f"stages[{i}]", "a stage is a name or {name, goal}")
    svn = stage_var_name(plot)
    if "stage_var" in plot and (not svn or not known_var(svn)):
        warn("stage_var", f"{plot.get('stage_var')!r} is not a variable of this plot or its world")
    # stage cut-scenes (10-14): {stage index | stage name: {image, video, caption, camera, prompt}}
    from neonrp.core import scene_cg as _scg

    if "stage_cg" in plot and not isinstance(plot["stage_cg"], dict):
        err("stage_cg", "must be an object keyed by stage (index or name)")
    for k, v in (plot.get("stage_cg") or {}).items() if isinstance(plot.get("stage_cg"), dict) else []:
        w = f"stage_cg.{k}"
        n, cg = _scg.stage_index(plot, k), _scg.norm(v)
        nst = len(plot["stages"]) if isinstance(plot.get("stages"), list) else 0
        if n is None or (nst and not 0 <= n < nst):
            warn(w, f"not a stage of this plot (stages: {', '.join(map(_stage_name, plot.get('stages') or [])) or 'none'})")
        if cg is None or not (cg.get("image") or cg.get("video")):
            err(w, "needs an image or a video")
            continue
        files = {kk: cg[kk] for kk in ("image", "video") if cg.get(kk)}
        files.update({f"variants.{sid}": f for sid, f in _scg.variants(cg).items()})  # per companion (10-15)
        _lint_assets({kk: f for kk, f in files.items() if not kk.startswith("variants.")}, None, w, out)
        if "variants" in cg:
            _lint_assets({"variants": cg["variants"]}, None, w, out)  # kind / path only: an optional slot not filled yet is a warning, not a block
        for kk, f in files.items():
            if plot_dir is not None and isinstance(f, str) and not (Path(plot_dir) / f).is_file():
                warn(f"{w}.{kk}", f"optional slot not filled yet: {f}")

    # stray files under assets/ the plot never points at
    if plot_dir:
        referenced = {str(p) for p in _asset_paths(plot)}
        adir = Path(plot_dir) / "assets"
        if adir.is_dir():
            for f in adir.rglob("*"):
                if f.is_file() and str(f.relative_to(plot_dir)) not in referenced:
                    warn(f"assets/{f.relative_to(adir)}", "file is not referenced by any entry or ending")
    return out


_MISSING = "file not found: "


def _lint_assets(assets: Any, plot_dir: Path | None, where: str, out: list[Problem]) -> None:
    if assets is None:
        return
    if not isinstance(assets, dict):
        out.append(Problem("error", f"{where}.assets", "must be an object {kind: relative path}"))
        return
    for kind, rel in assets.items():
        w = f"{where}.assets.{kind}"
        if kind == "variants":  # {sid: image} — the picture per companion the player picked (10-15)
            if not isinstance(rel, dict) or not rel:
                out.append(Problem("error", w, "must be an object {companion sid: image path}"))
            else:
                for sid, f in rel.items():
                    _lint_one(f"{w}.{sid}", "image", f, plot_dir, out)
            continue
        if kind not in ASSET_KINDS:
            out.append(Problem("error", w, f"unknown asset kind (known: {', '.join(ASSET_KINDS)}, variants)"))
            continue
        _lint_one(w, kind, rel, plot_dir, out)


def _lint_one(w: str, kind: str, rel: Any, plot_dir: Path | None, out: list[Problem]) -> None:
    if not isinstance(rel, str) or not rel.strip():
        out.append(Problem("error", w, "must be a relative path"))
        return
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        out.append(Problem("error", w, "path must stay inside the plot folder"))
        return
    if Path(rel).suffix.lower() not in ASSET_KINDS[kind]:
        out.append(Problem("error", w, f"{rel!r} is not a {kind} file ({', '.join(ASSET_KINDS[kind])})"))
    if plot_dir is not None and not (Path(plot_dir) / rel).is_file():
        # 10-16 (niko): an entry / ending image not made yet is an optional slot (warn, like stage_cg) — the screen shows
        # its fallback; a malformed path / kind above still blocks
        out.append(Problem("warn", w, f"{_MISSING}{rel}"))


def _asset_paths(plot: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for table in ("entries", "endings"):
        for spec in (plot.get(table) or {}).values():
            if isinstance(spec, dict) and isinstance(spec.get("assets"), dict):
                out += [str(v) for v in spec["assets"].values() if isinstance(v, str)]
                out += list(_scg.variants(spec["assets"]).values())
    for v in (plot.get("stage_cg") or {}).values() if isinstance(plot.get("stage_cg"), dict) else []:
        out += [str(v[k]) for k in ("image", "video") if isinstance(v, dict) and isinstance(v.get(k), str)] if isinstance(v, dict) else [str(v)]
        out += list(_scg.variants(v).values())
    return out


# ── the front end's face ─────────────────────────────────────────────────────

def assets(plot: dict[str, Any], base: str = "") -> list[dict[str, str]]:
    """Flat list for the front end: [{owner, owner_kind, kind, path}] — kind is one of ASSET_KINDS,
    path is relative to the plot folder (or prefixed with ``base``). Nothing else is promised."""
    out: list[dict[str, str]] = []
    for table, ok in (("entries", "entry"), ("endings", "ending")):
        for oid, spec in (plot.get(table) or {}).items():
            if isinstance(spec, dict) and isinstance(spec.get("assets"), dict):
                for kind, rel in spec["assets"].items():
                    if isinstance(rel, str):
                        out.append({"owner": str(oid), "owner_kind": ok, "kind": str(kind), "path": (base.rstrip("/") + "/" + rel) if base else rel})
                for sid, rel in _scg.variants(spec["assets"]).items():  # the picture per companion (10-15)
                    out.append({"owner": str(oid), "owner_kind": ok, "kind": "image", "variant": sid,
                                "path": (base.rstrip("/") + "/" + rel) if base else rel})
    return out


# ── install into a world ─────────────────────────────────────────────────────

def install(root: Path, plot_dir: Path, *, copy_assets: bool = True) -> dict[str, Any]:
    """Register a linted plot into a world: classes → vars → entries → triggers, through
    ``registry.register`` (so the world's own checks apply); copy the folder under
    ``game/plots/<id>/`` and index it in ``game/meta/plots.json``. Raises on lint errors."""
    plot = load(plot_dir)
    probs = lint(plot, plot_dir, root)
    # 10-08: an ending / entry image not generated yet does not stop the run — write the prompt first, make the image
    # later; the screen shows its fallback meanwhile (10-16: it is a warn in the template lint too, see _lint_one)
    errors = [p for p in probs if p.level == "error"]
    if errors:
        raise ValueError("plot has lint errors:\n" + "\n".join(str(p) for p in errors))
    pid = str(plot["id"])
    done: dict[str, list[str]] = {"classes": [], "vars": [], "entries": [], "triggers": []}
    for cid, spec in (plot.get("classes") or {}).items():
        register(root, "classes", cid, spec)
        done["classes"].append(cid)
    vars_ = dict(plot.get("vars") or {})
    sv = stage_var(plot)
    if sv:
        vars_.setdefault(sv[0], sv[1])
    store = f"{get_data_dir_name(root)}/meta/plot_vars.json"  # where a plot's own numbers live unless the spec says otherwise
    store_p = root / store
    try:
        stored = json.loads(store_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    for vid, spec in vars_.items():
        spec = {"path": store, "key": vid, **spec}
        if spec["path"] == store:  # dotted key = nested path inside the store (the registry's convention)
            node = stored
            *head, last = spec["key"].split(".")
            for part in head:
                node = node.setdefault(part, {}) if isinstance(node.get(part), dict) or part not in node else node[part]
            node.setdefault(last, spec.get("default", {"int": 0, "float": 0.0, "bool": False, "str": ""}[spec["type"]]))
        register(root, "variables", vid, spec)
        done["vars"].append(vid)
    store_p.parent.mkdir(parents=True, exist_ok=True)
    store_p.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    for eid, spec in (plot.get("entries") or {}).items():
        s = {k: v for k, v in spec.items() if k != "assets"}
        props = dict(s.pop("props", None) or {})
        if s.get("name"):
            props.setdefault("name", s.pop("name"))
        if "clue" in s:  # a clue (10-15): kept with the entry's props, so the registry knows it
            props.setdefault("clue", bool(s.pop("clue")))
        register(root, "entries", eid, {**s, "props": props})
        if s.get("class") == "place":
            _add_map_node(root, eid, props, s)  # the RPG map is this pack's; a new place must be walkable
        done["entries"].append(eid)
    treg = load_registry(root) if plot.get("triggers") else None  # once: a trigger changes nothing the next one is checked against
    staged: dict[str, dict[str, Any]] = {}  # and triggers.json is written once, not once per trigger
    try:
        for tid, spec in (plot.get("triggers") or {}).items():
            register(root, "triggers", tid, spec, reg=treg, staged=staged)
            done["triggers"].append(tid)
    finally:
        write_staged(staged)  # what registered before a refusal lands, as when each one wrote the file
    dest = root / get_data_dir_name(root) / "plots" / pid
    if copy_assets:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(plot_dir, dest)
    idx_p = root / get_data_dir_name(root) / "meta" / "plots.json"
    try:
        idx = json.loads(idx_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        idx = {}
    idx[pid] = {"title": plot.get("title"), "dir": str(dest.relative_to(root)), "endings": sorted(plot.get("endings") or {}),
                "stage_var": stage_var_name(plot), **done}
    idx_p.parent.mkdir(parents=True, exist_ok=True)
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    return idx[pid]


def _add_map_node(root: Path, eid: str, props: dict[str, Any], spec: dict[str, Any]) -> None:
    """Put a plot place into its town's ``town_map.json`` (node + symmetric links), so the
    reference map judge / mover accept it. Idempotent."""
    from neonrp.core import place_tree

    town, _, node = eid.rpartition("/")
    town = town or str(spec.get("parent") or "")
    data = place_tree.level_doc(root, town) if town else None  # town_map.json, or the town's place folders
    if not isinstance(data, dict):
        return
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    links = [str(lk).rpartition("/")[2] for lk in spec.get("links") or []]
    existing = next((n for n in nodes if isinstance(n, dict) and n.get("id") == node), None)
    if existing is None:
        nodes.append({"id": node, "name": props.get("name", node), "type": str(spec.get("type") or "facility"),
                      "description": str(props.get("summary") or props.get("description") or ""), "links": links, "plot": True})
    else:
        existing["links"] = sorted(set(existing.get("links") or []) | set(links))
    for n in nodes:
        if isinstance(n, dict) and n.get("id") in links and node not in (n.get("links") or []):
            n["links"] = list(n.get("links") or []) + [node]
    data["nodes"] = nodes
    place_tree.save_level_doc(root, town, data)


def problems_json(probs: list[Problem]) -> list[dict[str, str]]:
    return [asdict(p) for p in probs]
