"""Authoring a template (Template v3 · the 3.0 studio's 组装 · Lint): fork one, apply creator ops to it, mirror assets.

A template is edited only where it is writable: under ``NEONRP_TEMPLATE_WRITE_DIR`` (WorldLines' own template store).
Built-in / example templates are read-only — fork first. Every edit goes through ``apply_ops``: all ops are verified
before anything is written (one refused → nothing lands), then the template is re-linted.

Ops (the mock's creator ops, now against the template on disk):

    edit_card     {title?, pitch?, tags?, lang?}
    set_mode      {ending?, freedom?}
    set_mixins    {mixins: [...]}                    pack mixins (economy / factions …)
    add_slot      {cls, slot, kind?, required?, recipe?, ratio?, scope?, fallback?}
    remove_slot   {cls, slot}
    edit_prompt   {id, text}                         named prompt (ui.prompts); text null removes it
    edit_recipe   {key: backend|style, value}
    set_view      {view: {id, title, bind, widget, actions?, layout?}}
    remove_view   {id}
    set_budget    {value}
    register_class{name, policy?}                    a template-level class (world-overlay game/meta/classes.json)
    set_policy    {cls, policy}                      growth policy of a class (same overlay)
    set_world_data{name: economy|factions, data}     mixin world data (world-overlay game/world/<name>.json)
    set_orchestration{graph}                         the template's graph, stored as a patch on the pack default (orchestration.json);
                                                     nodes.resolve.state = pseudo | jev: how the Resolve beat writes state
    set_play_contract{contract}                      "<id>@<version>" of a play contract; "" drops it
    set_soul_orchestration{sid, graph}               one character's own graph in this world (core/soul_orchestration), stored as a
                                                     patch on what it gets without one: prompts/souls/<sid>/orchestration.json
    set_engine_setting{key, value}                   one whitelisted engine setting in the template's pack.engine (merged into the
                                                     run's game/meta/engine.json at build): turn.parallel.souls.per_soul.<sid>
                                                     (a character of this template; null = follow default_variant) ·
                                                     turn.parallel.souls.default_variant — values: legacy · S-judge · S-direct · S-free
    set_soul_ambient{sid, world}                     one character's simple world view in this world (core/soul_ambient):
                                                     prompts/souls/<sid>/ambient/world.json
    set_cast      {souls: [...]}                     who plays: {sid} world-native · {lib} a link into the character
                                                     library (copied in only when a run is built) · {path} · {pool, pick};
                                                     role npc / companion / player

The asset workshop: when ``WORLDLINES_ASSETS_DIR`` is set, every image that lands in a slot is also copied to
``$WORLDLINES_ASSETS_DIR/worlds/<template id>/<cls>/<slot>/<inst>.<ext>`` (the production workshop; generated
prompts are appended to ``prompts.md`` there) — the template keeps the final, the workshop keeps the history.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from neonrp.template import (
    ENDING_MODES,
    FREEDOM_MODES,
    SCHEMA,
    Template,
    TemplateError,
    discover,
    load,
)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")
NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
WORLD_DATA = ("economy", "factions")
RECIPE_KEYS = ("backend", "style")
SLOT_KINDS = ("image", "icon", "audio")
REQUIRED = ("publish", "optional")
POLICIES = ("auto", "approve", "creator", "forbid")
COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc")


# ── where templates may be written ───────────────────────────────────────────

def write_root() -> Path | None:
    v = os.environ.get("NEONRP_TEMPLATE_WRITE_DIR", "").strip()
    return Path(v).expanduser().resolve() if v else None


def writable(t: Template) -> bool:
    root = write_root()
    return bool(root and t.dir.resolve().is_relative_to(root))


def mixins_available() -> list[str]:
    from neonrp.packs import mixins as _m

    return sorted(p.stem for p in Path(_m.__file__).parent.glob("*.py") if not p.stem.startswith("_"))


# ── fork ─────────────────────────────────────────────────────────────────────

def fork(src: Template | Path | str, new_id: str, *, title: str | None = None, creation: bool = False) -> Template:
    """Copy a template into the write store under a new id (plots / prompts / overlay / assets come along).
    ``creation`` = the copy is a creation desk's work (template/creation.save): allowed whenever the template opens a
    creation layer, even when it is not forkable — the desk only adds inside that layer."""
    from neonrp.template import can_fork
    from neonrp.template import creation as _creation

    t = src if isinstance(src, Template) else load(src)
    if not can_fork(t) and not (creation and _creation.spec(t)["open"]):  # niko 10-17: of the official worlds only the two the local edition ships offer a copy
        raise TemplateError(f"{t.id}: this official world can be played, not copied (only forkable templates are)")
    root = write_root()
    if root is None:
        raise TemplateError("no writable template store (NEONRP_TEMPLATE_WRITE_DIR)")
    if not ID_RE.match(new_id or ""):
        raise TemplateError("id: 2–48 chars, lowercase letters / digits / '-'")
    if new_id in discover():
        raise TemplateError(f"template {new_id!r} already exists")
    dest = root / f"{new_id}.template"
    if dest.exists():
        raise TemplateError(f"{dest.name} already exists")
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(t.dir, dest, ignore=COPY_IGNORE)
    d = json.loads((dest / "template.json").read_text(encoding="utf-8"))
    d["schema"] = d.get("schema") or SCHEMA
    d["id"] = new_id
    d["version"] = "0.1"
    d["forked_from"] = {"id": t.id, "version": t.version, **({"creation": True} if creation else {})}
    for k in ("forkable", "official", "hub_ref", "hub_revision"):   # 10-17: the copy is no official world
        d.pop(k, None)
    d.pop("zone", None)   # 10-16: the copy is the author's own work — not the default zone the original sits in (only free-zone works export)
    if isinstance(d.get("card"), dict):
        d["card"].pop("zone", None)
    if title:
        d.setdefault("card", {})["title"] = title
    _write_json(dest / "template.json", d)
    workshop(new_id, create=True)
    t2 = load(dest)
    _agent_files(t2)
    return t2


def _agent_files(t: Template) -> None:
    """AGENTS.md / CLAUDE.md / spec/ inside the template and its store (template/agentdocs.py) — never fatal."""
    try:
        from neonrp.template import agentdocs

        agentdocs.write_template(t)
        root = write_root()
        if root is not None:
            agentdocs.write_store(root)
    except Exception:  # noqa: BLE001 — a spec copy failing never stops the fork
        pass


# ── ops ──────────────────────────────────────────────────────────────────────

class _Edit:
    """The template's JSON + overlay files, edited in memory; written only if every op verifies."""

    def __init__(self, t: Template) -> None:
        self.t = t
        self.data = copy.deepcopy(t.data)
        self.files: dict[str, Any] = {}  # path relative to the template → JSON to write

    @property
    def ui(self) -> dict[str, Any]:
        u = self.data.get("ui")
        if not isinstance(u, dict):
            u = self.data["ui"] = {}
        return u

    def overlay_rel(self) -> str:
        w = self.data.get("world")
        if not isinstance(w, dict):
            w = self.data["world"] = {"path": w} if isinstance(w, str) else {}
        if w.get("path"):  # the template carries its own world: edit it in place
            return str(w["path"])
        w.setdefault("overlay", "world-overlay")
        return str(w["overlay"])

    def overlay_json(self, rel: str) -> dict[str, Any]:
        key = f"{self.overlay_rel()}/{rel}"
        if key not in self.files:
            p = self.t.dir / key
            if not p.is_file():  # overlays replace whole files: start from the world's own copy so nothing is lost
                from neonrp.template import world_dir

                wd = world_dir(self.t)
                p = wd / rel if wd is not None and (wd / rel).is_file() else p
            try:
                d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
            except ValueError:
                d = {}
            self.files[key] = d if isinstance(d, dict) else {}
        return self.files[key]


def _pack_classes(t: Template) -> set[str]:
    from neonrp.template import v3

    try:
        with v3._scratch(t, None) as root:
            from neonrp.core.registry import load_registry

            return set(load_registry(root).classes)
    except Exception:  # noqa: BLE001 — a template that does not build: lint says why
        return set()


class _Classes:
    """The world's classes, built only when an op asks (10-19: every write used to build the world first — ~1 s — though
    only register_class / set_class_policy / an entry's class check need them)."""

    def __init__(self, t: Template) -> None:
        self.t, self._s = t, None

    def _get(self) -> set[str]:
        if self._s is None:
            self._s = _pack_classes(self.t)
        return self._s

    def __contains__(self, name: object) -> bool:
        return name in self._get()

    def add(self, name: str) -> None:
        self._get().add(name)


def _one(ed: _Edit, op: dict[str, Any], classes: "_Classes | set[str]") -> dict[str, Any]:
    """Verify + apply one op to the in-memory edit. Returns {what, from, to}; raises TemplateError(why)."""
    name = str(op.get("op") or "")
    d, u = ed.data, ed.ui
    if name == "edit_card":
        card = d.setdefault("card", {})
        changed = {}
        for k in ("title", "pitch", "lang"):
            if k in op:
                v = str(op[k] or "").strip()
                if k == "title" and not v:
                    raise TemplateError("标题不能为空")
                changed[k] = (card.get(k), v)
                card[k] = v
        if "tags" in op:
            tags = [str(x).strip() for x in (op["tags"] or []) if str(x).strip()][:8]
            changed["tags"] = (card.get("tags"), tags)
            card["tags"] = tags
        if not changed:
            raise TemplateError("edit_card 没有要改的字段")
        return {"what": "card." + ",".join(changed), "from": "", "to": "; ".join(f"{k}={v[1]}" for k, v in changed.items())}
    if name == "set_orchestration":
        # the template's edit of the orchestration graph (O1, 1.0 write-back): the editor sends the whole graph it
        # shows; it is stored as a patch against the graph the template gets without one (engine default + the pack's
        # own), so later pack defaults still flow in. Same as the default again → the override is dropped.
        g = op.get("graph")
        if not isinstance(g, dict) or not isinstance(g.get("nodes"), dict) or not isinstance(g.get("edges"), list):
            raise TemplateError("graph needs nodes (object) and edges (list)")
        nodes = g["nodes"]
        for e in g["edges"]:
            if not isinstance(e, dict) or not e.get("from") or not e.get("to") or not isinstance(e.get("on"), dict):
                raise TemplateError(f"an edge needs from / to / on: {json.dumps(e, ensure_ascii=False)[:160]}")
            if (e["from"] != "*" and e["from"] not in nodes) or (e["to"] != "@return" and e["to"] not in nodes):  # "*" = from anywhere
                raise TemplateError(f"edge {e.get('id') or e['from'] + '>' + e['to']} points at a node that does not exist")
        if g.get("start") and g["start"] not in nodes:
            raise TemplateError(f"start {g['start']} is not a node")
        from neonrp.core.orchestration import STATE_MODES

        for _nid, _n in nodes.items():  # a loop node's state parameter (the Resolve's: pseudo | jev, 10-11)
            if isinstance(_n, dict) and _n.get("state") is not None and str(_n["state"]) not in STATE_MODES:
                raise TemplateError(f"node {_nid}: state {_n['state']} is not one of {' | '.join(STATE_MODES)}")
        from neonrp.core import turn_steps  # 10-17 S2: a step setting must name a real setting and fit it

        _bad = turn_steps.check_params(g)
        if _bad:
            raise TemplateError("; ".join(_bad[:4]))
        patch = graph_patch(base_graph(ed.t), g)
        before = "override" if d.get("orchestration") else "default"
        if not patch:
            d.pop("orchestration", None)
            return {"what": "orchestration", "from": before, "to": "default (same as the pack's graph)"}
        ed.files[ORCH_FILE] = patch
        d["orchestration"] = ORCH_FILE
        n = patch.get("nodes") or {}
        return {"what": "orchestration", "from": before,
                "to": f"nodes +{sum(1 for v in n.values() if v is not None)} -{sum(1 for v in n.values() if v is None)} · "
                      f"edges +{len(patch.get('add') or [])} -{len(patch.get('remove') or [])}"}
    if name == "set_soul_orchestration":
        # a character's graph for this world only (niko 10-16, 角色编排台:默认只改这个世界);the character library is not touched
        from neonrp.core import soul_orchestration as SO

        sid = str(op.get("sid") or "")
        folders = {}
        for p in ed.t.soul_files():
            try:
                sj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(sj, dict) and sj.get("sid"):
                folders.setdefault(str(sj["sid"]), p.parent)
        if sid not in folders:
            raise TemplateError(f"{sid or '—'} is not a character of this template")
        try:
            g = SO.check(op.get("graph"))
        except ValueError as e:
            raise TemplateError(str(e)) from e
        rel = f"prompts/souls/{sid}/orchestration.json"
        before = "override" if (ed.t.dir / rel).is_file() else "default"
        patch = SO.patch_of(SO.graph(folders[sid]), g)
        ed.files[rel] = patch   # {} = the same as without one
        return {"what": f"soul.{sid}.orchestration", "from": before, "to": "default (same as the character's own)" if not patch else rel}
    if name == "set_engine_setting":
        # the world's engine settings a bench may write (niko 10-17, 角色编排台 in_world:变体写进模板 engine 配置) — a whitelist
        from neonrp.core import soul_orchestration as SO

        key, value = str(op.get("key") or ""), op.get("value")
        per = SO.VARIANT_KEY + "."
        if key.startswith(per):
            sid = key[len(per):]
            sids = set()
            for p in ed.t.soul_files():
                try:
                    sj = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(sj, dict) and sj.get("sid"):
                    sids.add(str(sj["sid"]))
            sids |= {str(r.get("sid") or r.get("lib")) for r in ed.t.souls or [] if isinstance(r, dict) and (r.get("sid") or r.get("lib"))}   # a library link plays as its sid (or its folder)
            if sid not in sids:
                raise TemplateError(f"{sid or '—'} is not a character of this template")
        elif key != "turn.parallel.souls.default_variant":
            raise TemplateError(f"{key or '—'} is not an engine setting a template may set here")
        if value is not None and str(value) not in SO.variants():
            raise TemplateError(f"{value!r} is not a soul variant ({' · '.join(SO.variants())})")
        if value is None and not key.startswith(per):
            raise TemplateError(f"{key} needs a value")
        eng = d.setdefault("pack", {}).setdefault("engine", {})
        parts = key.split(".")
        cur = eng
        for k in parts[:-1]:
            if not isinstance(cur.get(k), dict):
                cur[k] = {}
            cur = cur[k]
        before = cur.get(parts[-1])
        if value is None:
            cur.pop(parts[-1], None)
        else:
            cur[parts[-1]] = str(value)
        return {"what": f"pack.engine.{key}", "from": before or "", "to": "" if value is None else str(value)}
    if name == "set_soul_ambient":
        # the background a character's tick happens in, for this world only (niko 10-16: 复刻原来的世界背景或自动生成)
        from neonrp.core import soul_ambient

        sid = str(op.get("sid") or "")
        sids = set()
        for p in ed.t.soul_files():
            try:
                sj = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(sj, dict) and sj.get("sid"):
                sids.add(str(sj["sid"]))
        if sid not in sids:
            raise TemplateError(f"{sid or '—'} is not a character of this template")
        if not isinstance(op.get("world"), dict):
            raise TemplateError("world must be an object")
        rel = f"prompts/souls/{sid}/{soul_ambient.FILE}"
        before = "override" if (ed.t.dir / rel).is_file() else "none"
        ed.files[rel] = soul_ambient.normal(op["world"])
        return {"what": f"soul.{sid}.ambient", "from": before, "to": rel}
    if name == "set_cast":
        # who plays in this template: a row is a world-native soul {sid}, a link into the character library
        # {lib} (copied in only when a run is built), a soul inside the template {path}, or a pool {pool, pick}.
        # role: npc · companion · player. The list replaces the old one; [] = every world-native soul.
        from neonrp.template import library_dir

        rows = op.get("souls")
        if not isinstance(rows, list):
            raise TemplateError("souls must be a list")
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def norm(r: Any, where: str) -> dict[str, Any]:
            r = {"sid": r} if isinstance(r, str) else dict(r) if isinstance(r, dict) else None
            if r is None:
                raise TemplateError(f"{where}: a row is a sid or an object")
            if r.get("lib"):
                lib = str(r["lib"])
                if "/" in lib or lib.startswith(".") or not (library_dir(lib) / "soul.json").is_file():
                    raise TemplateError(f"{where}: no soul {lib!r} in the character library")
                r.setdefault("sid", str((_read_json(library_dir(lib) / "soul.json") or {}).get("sid") or lib))
            if not str(r.get("sid") or "").strip():
                raise TemplateError(f"{where}: needs a sid")
            if r.get("role") and r["role"] not in ("npc", "companion", "player"):
                raise TemplateError(f"{where}: role is npc / companion / player")
            if r["sid"] in seen:
                raise TemplateError(f"{where}: {r['sid']} is cast twice")
            seen.add(r["sid"])
            return r

        for i, r in enumerate(rows):
            if isinstance(r, dict) and isinstance(r.get("pool"), list):
                pool = [norm(p, f"souls[{i}].pool[{j}]") for j, p in enumerate(r["pool"])]
                out.append({**r, "pool": pool})
            else:
                out.append(norm(r, f"souls[{i}]"))
        if sum(1 for r in out if r.get("role") == "player") > 1:
            raise TemplateError("only one player")
        before = [str(r.get("lib") or r.get("sid") or "pool") for r in d.get("souls") or [] if isinstance(r, dict)]
        if out:
            d["souls"] = out
        else:
            d.pop("souls", None)
        return {"what": "souls", "from": ", ".join(before), "to": ", ".join(str(r.get("lib") or r.get("sid") or "pool") for r in out)}
    if name == "set_play_contract":
        # the experience the template promises (template/contract.py): "<id>@<version>", or "" to drop it.
        # Verified against the official contracts here; whether the template meets it is lint's job (re-run below).
        from neonrp.template import contract as _contract

        ref = str(op.get("contract") or "").strip()
        before = str(d.get("play_contract") or "")
        if not ref:
            d.pop("play_contract", None)
            return {"what": "play_contract", "from": before, "to": ""}
        if "@" not in ref:
            try:
                ref = f"{ref}@{int(_contract.load(ref).get('version') or 1)}"
            except _contract.ContractError as e:
                raise TemplateError(str(e)) from e
        try:
            _contract.load(ref)
        except _contract.ContractError as e:
            raise TemplateError(str(e)) from e
        d["play_contract"] = ref
        return {"what": "play_contract", "from": before, "to": ref}
    if name == "set_mode":
        mode = d.setdefault("mode", {})
        if "ending" in op and op["ending"] not in ENDING_MODES:
            raise TemplateError(f"结局模式只能是 {' / '.join(ENDING_MODES)}")
        if "freedom" in op and op["freedom"] not in FREEDOM_MODES:
            raise TemplateError(f"自由度只能是 {' / '.join(FREEDOM_MODES)}")
        before = dict(mode)
        for k in ("ending", "freedom"):
            if k in op:
                mode[k] = op[k]
        return {"what": "mode", "from": json.dumps(before, ensure_ascii=False), "to": json.dumps(mode, ensure_ascii=False)}
    if name == "set_mixins":
        want = [str(m) for m in op.get("mixins") or []]
        bad = [m for m in want if m not in mixins_available()]
        if bad:
            raise TemplateError(f"没有扩展 {', '.join(bad)}(可用:{', '.join(mixins_available())})")
        pk = d.get("pack")
        pk = d["pack"] = {"name": pk} if isinstance(pk, str) else dict(pk or {"name": "rpg"})
        before = list(pk.get("mixins") or [])
        pk["mixins"] = want
        return {"what": "pack.mixins", "from": "+".join(before) or "—", "to": "+".join(want) or "—"}
    if name == "add_slot":
        cls, slot = str(op.get("cls") or ""), str(op.get("slot") or "").strip()
        if not NAME_RE.match(slot):
            raise TemplateError("槽位名只能是小写字母、数字和下划线")
        if cls != "level" and cls not in classes:
            raise TemplateError(f"没有类 {cls}")
        kind, req = str(op.get("kind") or "image"), str(op.get("required") or "optional")
        if kind not in SLOT_KINDS:
            raise TemplateError(f"槽位类型只能是 {' / '.join(SLOT_KINDS)}")
        if req not in REQUIRED:
            raise TemplateError(f"required 只能是 {' / '.join(REQUIRED)}")
        from neonrp.template import v3

        if any(s.get("cls") == cls and s.get("slot") == slot for s in v3.ui(_as_template(ed))["slots"]):
            raise TemplateError(f"{cls}.{slot} 已经声明过")
        row = {"cls": cls, "slot": slot, "kind": kind, "required": req,
               **{k: op[k] for k in ("recipe", "ratio", "scope", "fallback") if op.get(k)}}
        u.setdefault("slots", []).append(row)
        return {"what": f"slots/{cls}.{slot}", "from": "—", "to": f"{kind} · {req}"}
    if name == "remove_slot":
        cls, slot = str(op.get("cls") or ""), str(op.get("slot") or "")
        rows = [s for s in u.get("slots") or [] if not (s.get("cls") == cls and s.get("slot") == slot)]
        rows.append({"cls": cls, "slot": slot, "remove": True})
        u["slots"] = rows
        return {"what": f"slots/{cls}.{slot}", "from": "声明", "to": "—"}
    if name == "edit_prompt":
        pid = str(op.get("id") or "")
        if not NAME_RE.match(pid):
            raise TemplateError("提示词 id 只能是小写字母、数字和下划线")
        from neonrp.template import v3

        cur = v3.ui(_as_template(ed))["prompts"].get(pid)
        text = op.get("text")
        u.setdefault("prompts", {})[pid] = None if text is None else str(text)
        return {"what": f"prompts/{pid}", "from": v3._h(cur) if cur is not None else "—", "to": v3._h(text) if text is not None else "—"}
    if name == "edit_recipe":
        key = str(op.get("key") or "")
        if key not in RECIPE_KEYS:
            raise TemplateError(f"配方没有字段 {key}")
        r = d.setdefault("recipe", {})
        before = r.get(key, "")
        r[key] = str(op.get("value") or "")
        return {"what": f"recipe.{key}", "from": before, "to": r[key]}
    if name == "set_view":
        v = op.get("view")
        if not isinstance(v, dict) or not NAME_RE.match(str(v.get("id") or "")):
            raise TemplateError("视图要有 id(小写字母、数字、下划线)")
        from neonrp.template import v3

        if v.get("widget") and v["widget"] not in v3.WIDGETS:
            raise TemplateError(f"没有组件 {v['widget']}(可用:{', '.join(v3.WIDGETS)})")
        rows = [x for x in u.get("views") or [] if x.get("id") != v["id"]]
        rows.append({k: v[k] for k in ("id", "title", "bind", "widget", "actions", "layout") if k in v})
        u["views"] = rows
        return {"what": f"views/{v['id']}", "from": "", "to": str(v.get("widget") or "")}
    if name == "remove_view":
        vid = str(op.get("id") or "")
        u["views"] = [x for x in u.get("views") or [] if x.get("id") != vid] + [{"id": vid, "remove": True}]
        return {"what": f"views/{vid}", "from": "声明", "to": "—"}
    if name == "set_budget":
        try:
            n = int(op.get("value"))
        except (TypeError, ValueError) as e:
            raise TemplateError("预算要是整数") from e
        if not 1000 <= n <= 500000:
            raise TemplateError("预算在 1,000 – 500,000 token 之间")
        before = u.get("budget")
        u["budget"] = n
        return {"what": "budget", "from": before, "to": n}
    if name == "register_class":
        cname = str(op.get("name") or "")
        if not NAME_RE.match(cname):
            raise TemplateError("类名只能是小写字母和下划线")
        cj = ed.overlay_json("game/meta/classes.json")
        if cname in classes or cname in cj:
            raise TemplateError(f"类 {cname} 已存在")
        pol = str(op.get("policy") or "auto")
        if pol not in POLICIES:
            raise TemplateError(f"策略只能是 {' / '.join(POLICIES)}")
        cj[cname] = {"required": ["name"], "policy": pol, "doc": str(op.get("doc") or "")}
        classes.add(cname)
        return {"what": f"classes/{cname}", "from": "—", "to": "新类"}
    if name == "set_policy":
        cname, pol = str(op.get("cls") or ""), str(op.get("policy") or "")
        if cname not in classes:
            raise TemplateError(f"没有类 {cname}")
        if pol not in POLICIES:
            raise TemplateError(f"策略只能是 {' / '.join(POLICIES)}")
        cj = ed.overlay_json("game/meta/classes.json")
        before = (cj.get(cname) or {}).get("policy", "auto")
        cj[cname] = {**(cj.get(cname) or {}), "policy": pol}
        return {"what": f"classes/{cname}.policy", "from": before, "to": pol}
    if name == "set_world_data":
        wname, data = str(op.get("name") or ""), op.get("data")
        if wname not in WORLD_DATA:
            raise TemplateError(f"世界数据只能是 {' / '.join(WORLD_DATA)}")
        if not isinstance(data, dict):
            raise TemplateError("世界数据要是一个 JSON 对象")
        cur = ed.overlay_json(f"game/world/{wname}.json")
        cur.clear()
        cur.update(data)
        return {"what": f"world/{wname}", "from": "", "to": f"{len(json.dumps(data, ensure_ascii=False))} 字节"}
    raise TemplateError(f"未知的创作者 op {name!r}")


ORCH_FILE = "orchestration.json"


def base_graph(t: Template) -> dict[str, Any]:
    """The orchestration graph this template gets without its own override (engine default + the pack's own)."""
    from neonrp.core import orchestration
    from neonrp.template import v3

    t2 = copy.copy(t)
    t2.data = {k: v for k, v in t.data.items() if k != "orchestration"}
    with v3._scratch(t2, None) as root:
        g = orchestration.graph(root)
    return {"start": g.get("start"), "nodes": dict(g.get("nodes") or {}), "edges": list(g.get("edges") or [])}


def _eid(e: dict[str, Any]) -> str:
    return str(e.get("id") or f"{e.get('from')}>{e.get('to')}:{'+'.join(sorted(e.get('on') or {}))}")


def graph_patch(base: dict[str, Any], g: dict[str, Any]) -> dict[str, Any]:
    """``{nodes, remove, add}`` that turns ``base`` into ``g`` (core/orchestration._patch's format); {} when equal."""
    out: dict[str, Any] = {}
    bn, gn = base.get("nodes") or {}, g.get("nodes") or {}
    # a node the base has: only the fields that differ (10-17 S2: a beat's step_params alone, not a frozen copy of its
    # catalog steps / tools — the engine's own fields keep flowing in); a new node: whole
    nodes = {k: (v if not isinstance(bn.get(k), dict) or not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if bn[k].get(kk) != vv})
             for k, v in gn.items() if bn.get(k) != v}
    nodes.update({k: None for k in bn if k not in gn})
    if nodes:
        out["nodes"] = nodes
    keep = ("from", "to", "on", "when", "return", "return_to")  # return: entering pushes a return point (10-17: was dropped on a re-written edge)
    be = {_eid(e): e for e in base.get("edges") or [] if isinstance(e, dict)}
    ge = {_eid(e): e for e in g.get("edges") or [] if isinstance(e, dict)}
    remove = [i for i in be if i not in ge]
    add = [{"id": i, **{k: e[k] for k in keep if k in e}} for i, e in ge.items()
           if i not in be or any(be[i].get(k) != e.get(k) for k in keep)]
    if remove:
        out["remove"] = remove
    if add:
        out["add"] = add
    return out   # the start node is the pack's (core/orchestration._patch does not move it)


def _as_template(ed: _Edit) -> Template:
    """The template as it would be after the edit so far (for ui() merges)."""
    t = copy.copy(ed.t)
    t.data = ed.data
    return t


def apply_ops(t: Template | Path | str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify every op, write all or nothing, re-lint. → {ok, applied, refused, lint, ui}."""
    from neonrp import template as TP
    from neonrp.template import v3

    t = t if isinstance(t, Template) else load(t)
    if not writable(t):
        raise TemplateError(f"模板 {t.id} 是内置的(只读)——先另存一份再改")
    if not isinstance(ops, list) or not ops:
        raise TemplateError("ops 要是非空列表")
    ed = _Edit(t)
    classes = _Classes(t)
    applied, refused = [], []
    for op in ops:
        if not isinstance(op, dict):
            refused.append({"op": op, "why": "op 要是对象"})
            continue
        try:
            applied.append({"op": op.get("op"), **_one(ed, op, classes)})
        except TemplateError as e:
            refused.append({"op": op.get("op"), "why": str(e)})
    if refused:
        return {"ok": False, "applied": [], "refused": refused}
    for rel, data in ed.files.items():
        _write_json(t.dir / rel, data)
    _write_json(t.dir / "template.json", ed.data)
    v3.forget(t)  # the next look reads what was just written (10-21 e2e 编排台: the graph read back within 2 s was the old one)
    t2 = load(t.dir)
    return {"ok": True, "applied": applied, "refused": [], "lint": TP.lint(t2), "ui": v3.ui(t2)}


# ── the asset workshop (worldlines-assets/worlds/<id>) ───────────────────────

def workshop(tid: str, *, create: bool = False) -> Path | None:
    base = os.environ.get("WORLDLINES_ASSETS_DIR", "").strip()
    if not base or not ID_RE.match(tid or ""):
        return None
    d = Path(base).expanduser() / "worlds" / tid
    if create and not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        (d / "prompts.md").write_text(f"# {tid} — 素材记录\n\n生成用的 prompt / 后端 / 时间(可复现)。定稿在模板里,这里留历史。\n\n",
                                      encoding="utf-8")
    return d if d.is_dir() else None


def mirror(t: Template, slot: str, src: Path | None, *, prompt: str | None = None, backend: str = "upload") -> Path | None:
    """Copy a slot's file into the workshop (and log the prompt for generated ones). Never fails the caller."""
    try:
        d = workshop(t.id, create=True)
        if d is None or src is None or not src.is_file():
            return None
        kind, _, rest = slot.partition(":") if slot.startswith(("card:", "plot:")) else ("", "", slot)
        if kind:
            sub = Path(kind) / re.sub(r"[^\w.-]+", "_", rest)
        else:
            head, _, inst = slot.partition(":")
            sub = Path(*head.split(".", 1)) / re.sub(r"[^\w.-]+", "_", inst or "_")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = d / sub.parent / f"{sub.name}--{stamp}{src.suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        with (d / "prompts.md").open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} `{slot}` · {backend} → `{dest.relative_to(d)}`" + (f"\n  > {prompt}" if prompt else "") + "\n")
        return dest
    except OSError:
        return None


def _read_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(p: Path, d: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
