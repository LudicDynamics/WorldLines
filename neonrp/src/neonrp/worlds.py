"""WorldLines world registry and game directory management."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("neonrp")

# Built-in worlds are declared in templates/worlds.manifest.json (single source
# of truth) so adding a world is "drop a template folder + a manifest row" with
# no code change. Each manifest entry's `template` names a folder under
# neonrp/templates/. The manifest ships in the wheel alongside the templates.
WORLDS_MANIFEST = "worlds.manifest.json"


@lru_cache(maxsize=1)
def _load_worlds() -> dict[str, dict[str, Any]]:
    """Load the built-in world registry from the packaged manifest.

    Returns a dict keyed by world id whose values match the historical
    in-memory shape (name / name_local / template / desc / source_lang /
    optional hidden / name_i18n / desc_i18n, plus mode / order). Ordered by
    each entry's ``order`` so the launcher listing is stable.
    """
    from importlib import resources

    raw = (
        resources.files("neonrp.templates")
        .joinpath(WORLDS_MANIFEST)
        .read_text(encoding="utf-8")
    )
    entries = json.loads(raw).get("worlds", [])
    pkg = resources.files("neonrp.templates")
    out: dict[str, dict[str, Any]] = {}
    for entry in sorted(entries, key=lambda e: e.get("order", 999)):
        tpl = entry.get("template")
        if tpl and not pkg.joinpath(tpl).is_dir():
            continue  # a release that leaves a world's folder out drops its row too
        info = {k: v for k, v in entry.items() if k != "id"}
        # Defensive fallbacks so a sparse entry still satisfies callers that
        # read name/desc directly (e.g. get_world(...)["template"]).
        src = info.get("source_lang", "en")
        name_i18n = info.get("name_i18n") or {}
        desc_i18n = info.get("desc_i18n") or {}
        info.setdefault("name", name_i18n.get(src) or info.get("name_local") or entry["id"])
        info.setdefault("name_local", "")
        info.setdefault("desc", desc_i18n.get(src, ""))
        out[entry["id"]] = info
    return out


# Module-level dict, preserved for backwards compatibility with existing
# callers that import and read ``WORLDS`` directly.
WORLDS: dict[str, dict[str, Any]] = _load_worlds()

# --- world/run separation (mirrors the hub: worlds are downloadable sources;
# a play is a run/session of one) -------------------------------------------
#   WORLDS_HOME : the world LIBRARY — worlds you own as reusable sources
#                 (created locally or downloaded from the hub). ↔ hub `worlds`.
#   PLAYS_HOME  : play INSTANCES — one dir per run; mutable play state, the
#                 cast placed in this run, hosted-play saves restore here.
#                 ↔ hub hosted-play saves (`.session-meta.json`).
#   GAME_HOME   : LEGACY flat pile (both at once). Migrated into the two above
#                 on first launch; kept only so migration + old callers resolve.
WORLDS_HOME = Path.home() / ".worldlines" / "worlds"
PLAYS_HOME = Path.home() / ".worldlines" / "plays"
GAME_HOME = Path.home() / ".worldlines" / "games"
#   STUDIO_HOME : creation BYPRODUCTS keyed by world id — canvas files
#                 (flow.json / relationships.json, docs/STUDIO-CANVAS-PLAN.md).
#                 Design-state only: never read by the engine at runtime,
#                 never exported/uploaded with the world. The world SOURCE
#                 under WORLDS_HOME stays pure content.
STUDIO_HOME = Path.home() / ".worldlines" / "studio"


def get_studio_dir(world_id: str, *, create: bool = False) -> Path:
    """The creation-byproduct dir for a world (canvas files live here)."""
    d = STUDIO_HOME / world_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d

# Written into every hosted-play session workdir by the play gateway
# (rp-infra play_gateway.save_zip ships it inside the downloadable save
# zip). A save downloaded from the web and restored with `load-world`
# carries this instead of `.worldhub.json`.
SESSION_META_FILENAME = ".session-meta.json"


def read_local_world_name(game_dir: Path) -> str | None:
    """Best-effort human-readable name for a user-created/imported world.

    Created (``world-game-authoring``) and imported (``tavern-game-import``)
    worlds carry no hub/session metadata — their identity lives in the world
    content the skill wrote under ``game/``. We look for a name in, in order:

    - ``game/meta/game-start.json`` ``name`` (the startup card the authoring
      skills write, e.g. "修仙世界·开局")
    - any ``game/town/*.json`` / ``game/location/*.json`` ``name`` (the first
      place — a reasonable world label when there's no startup card yet)

    Returns None when nothing usable is found (caller falls back to the dir
    slug). ``game`` may be renamed via the runtime contract's ``data_dir``;
    resolve that first so freshly-built worlds with a custom data dir still
    surface a name.
    """
    import json

    try:
        from neonrp.core.paths import get_game_dir

        data_dir = get_game_dir(game_dir)
    except Exception:
        data_dir = game_dir / "game"

    def _name_from(path: Path) -> str | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(data, dict):
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    start = _name_from(data_dir / "meta" / "game-start.json")
    if start:
        return start
    for sub in ("town", "location"):
        d = data_dir / sub
        if not d.is_dir():
            continue
        try:
            files = sorted(p for p in d.iterdir() if p.is_file() and p.suffix == ".json")
        except OSError:
            files = []
        for p in files:
            name = _name_from(p)
            if name:
                return name
    return None


# Marker file the creation engine drops at the root of every CREATED world dir
# (``world-game-authoring``): ``{"kind":"world","slug":…,"from_creation_engine":
# true,…}``. Its presence is how we tell a first-class authored world apart from
# an abandoned built-in instance or a hub download inside GAME_HOME.
CREATED_MARKER_FILENAME = "CREATED.json"


def read_created_marker(game_dir: Path) -> dict[str, Any] | None:
    """Read a created world's root ``CREATED.json`` marker, if it is one.

    Returns the parsed marker dict only when the file exists, parses, and has
    ``kind == "world"`` (the shape the creation engine writes). Anything else —
    missing file, unreadable JSON, a non-world marker — yields None so callers
    can treat the dir as not-a-created-world.
    """
    import json

    marker_path = game_dir / CREATED_MARKER_FILENAME
    if not marker_path.is_file():
        return None
    try:
        data = json.loads(marker_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict) and data.get("kind") == "world":
        return data
    return None


# --- owned world library (WORLDS_HOME) -------------------------------------
# An owned world is one dir under WORLDS_HOME, named by its world-id. It is a
# reusable SOURCE (the baked souls/ + playthrough + game/ live here); playing
# it instantiates a fresh run under PLAYS_HOME. Detection is by location, not a
# fragile marker — every dir under WORLDS_HOME is a world (so the agentic
# builder path no longer has to remember to drop CREATED.json).


def _owned_world_origin(world_dir: Path) -> str:
    """'downloaded' if the dir carries hub provenance, else 'created'."""
    if (world_dir / ".worldhub.json").is_file():
        return "downloaded"
    return "created"


def list_owned_worlds() -> list[dict[str, Any]]:
    """User-owned worlds under WORLDS_HOME as world-library entries.

    Each dir under WORLDS_HOME is a world the user owns (created locally or
    downloaded from the hub). Entries mirror the built-in shape (id / name /
    name_local / template / desc / display_name / source_lang / shelf) and add:

    - ``owned``      : True
    - ``source_dir`` : the WORLDS_HOME/<id> source dir
    - ``origin``     : 'created' | 'downloaded'

    Playing an owned world instantiates a run via :func:`instantiate_run` — it
    is NOT scaffolded from a packaged template. ``template`` is set to the
    source-dir path so callers that read ``["template"]`` don't KeyError.
    """
    if not WORLDS_HOME.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        entries = sorted(WORLDS_HOME.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    for world_dir in entries:
        if not world_dir.is_dir():
            continue
        world_id = world_dir.name
        origin = _owned_world_origin(world_dir)
        name = read_local_world_name(world_dir) or world_id
        out.append({
            "id": world_id,
            "name": name,
            "name_local": "",
            "template": str(world_dir),
            "desc": "",
            "display_name": name,
            "source_lang": "en",
            "shelf": "created" if origin == "created" else "standard",
            "owned": True,
            "origin": origin,
            "source_dir": world_dir,
        })
    return out


def get_owned_world_dir(world_id: str) -> Path | None:
    """The WORLDS_HOME source dir for an owned world id, or None."""
    d = WORLDS_HOME / world_id
    return d if d.is_dir() else None


def delete_owned_world(world_id: str) -> bool:
    """Delete an OWNED world (WORLDS_HOME/<id>) and its runs. Best-effort.

    Removes the library source dir plus every run of that world under
    PLAYS_HOME (dirs named ``<world-id>-<timestamp>``) so no orphan runs
    linger. Refuses (returns False) for built-in manifest worlds — those are
    packaged and not deletable — or when the source dir doesn't exist. Never
    raises; returns True only when the source dir was actually removed.
    """
    import logging
    import shutil

    # Built-in manifest worlds are packaged sources, never deletable.
    if world_id in WORLDS:
        return False
    source = WORLDS_HOME / world_id
    if not source.is_dir():
        return False

    log = logging.getLogger("neonrp")
    try:
        shutil.rmtree(source)
    except OSError:
        log.warning("delete_owned_world: failed to remove %s", source, exc_info=True)
        return False

    # Drop this world's runs too (timestamp-suffixed dirs under PLAYS_HOME),
    # matching the same shape create_run_dir / instantiate_run produce.
    if PLAYS_HOME.is_dir():
        try:
            run_dirs = list(PLAYS_HOME.iterdir())
        except OSError:
            run_dirs = []
        for run_dir in run_dirs:
            if not run_dir.is_dir() or not run_dir.name.startswith(f"{world_id}-"):
                continue
            rest = run_dir.name[len(world_id) + 1:]
            if len(rest) >= 8 and rest[:8].isdigit():
                try:
                    shutil.rmtree(run_dir)
                except OSError:
                    log.warning(
                        "delete_owned_world: failed to remove run %s", run_dir,
                        exc_info=True,
                    )
    return True


def register_owned_world(source_dir: Path, world_id: str | None = None) -> Path:
    """Install ``source_dir`` into the world library as ``WORLDS_HOME/<id>``.

    Used by the create flow (authored world → library) and hub download
    (extracted world → library). Copies the full source (souls/ + playthrough +
    game/ included — placement/casting then happens per-run, never here). Idempotent:
    an existing same-id world is left as-is. Returns the library dir.
    """
    import shutil

    wid = world_id or _slugify_world(source_dir.name)
    dest = WORLDS_HOME / wid
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest)
    return dest


BLANK_WORLD_TEMPLATE = "white-blank"


def create_blank_world(
    name: str, *, premise: str = "", template: str = BLANK_WORLD_TEMPLATE, model_ref: str | None = None
) -> Path:
    """A brand-new owned world SOURCE under ``WORLDS_HOME/<slug>``, from the
    blank template, carrying the name the author gave it.

    This is what `/init <名字> [设定]` does before handing the folder to the
    build agent (新游戏和新建的世界都在 .worldlines 里).
    The template is structurally complete and immediately playable, so the
    agent starts from a world that runs, not from an empty directory. Nothing
    here talks to a model: naming is a file edit, authoring is the agent's.

    A same-name world gets a ``-2`` suffix rather than being merged into —
    two worlds with the same title are still two worlds.
    """
    import json

    slug = _slugify_world(name)
    # 避开内置世界 id(bug:owned 同 id 会顶替内置并挤掉它,
    # 导致内置角色立绘"没了")。撞内置就加 -N,再交 _dedupe_path 处理已存在目录。
    if slug in WORLDS:
        n = 2
        while f"{slug}-{n}" in WORLDS or (WORLDS_HOME / f"{slug}-{n}").exists():
            n += 1
        slug = f"{slug}-{n}"
    dest = _dedupe_path(WORLDS_HOME / slug)
    dest.parent.mkdir(parents=True, exist_ok=True)
    scaffold_template_into(template, dest, model_ref=model_ref)

    try:
        from neonrp.core.paths import get_game_dir

        data_dir = get_game_dir(dest)
    except Exception:
        data_dir = dest / "game"

    def _patch(path: Path, mutate) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        mutate(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _name_start(data: dict[str, Any]) -> None:
        data["name"] = name
        info = data.get("world_info")
        if isinstance(info, dict):
            info["world_name"] = name
            if premise:
                info["premise"] = premise

    def _name_map(data: dict[str, Any]) -> None:
        data["name"] = name

    _patch(data_dir / "meta" / "game-start.json", _name_start)
    _patch(data_dir / "world" / "world_map.json", _name_map)
    return dest


# --- play instances (PLAYS_HOME) -------------------------------------------


def create_run_dir(world_id: str) -> Path:
    """Create an empty run dir ``PLAYS_HOME/<world-id>-<YYYYMMDD-HHMMSS>/``.

    Used for built-in worlds, which scaffold from their packaged template into
    this fresh run. Owned worlds use :func:`instantiate_run` (a copy) instead.
    """
    from datetime import timedelta

    PLAYS_HOME.mkdir(parents=True, exist_ok=True)
    # Never reuse a dir: two new runs in the same second used to share one (exist_ok) — the second build then
    # failed and its cleanup deleted the FIRST run, the one being played (10-08). Taken → the next free second, so the
    # name keeps the "<world>-<YYYYMMDD-HHMMSS>" shape every parser strips.
    now = datetime.now()
    for n in range(1000):
        run_dir = PLAYS_HOME / f"{world_id}-{(now + timedelta(seconds=n)).strftime('%Y%m%d-%H%M%S')}"
        try:
            run_dir.mkdir()
            return run_dir
        except FileExistsError:
            continue
    raise OSError(f"no free run dir for {world_id}")


def scaffold_builtin_run(world_id: str, locale: str = "en", *, model_ref: str | None = None) -> Path:
    """Scaffold a fresh, playable run of a BUILT-IN world into PLAYS_HOME.

    Headless equivalent of the launcher's `worldlines_init` scaffold sequence
    (cli.py) minus its interactive parts (preset picker, casting, player
    profile, surface launch). Used by the web launcher's "start a new run"
    path so built-ins are playable without the TUI.

    Raises KeyError for an unknown world id.
    """
    if world_id not in WORLDS:
        raise KeyError(f"not a built-in world: {world_id!r}")
    template_name = resolve_template(world_id, locale)
    run_dir = create_run_dir(world_id)
    scaffold_template_into(template_name, run_dir, model_ref=model_ref)
    return run_dir


def seed_run_model(run_dir: Path, model_ref: str | None = None) -> str | None:
    """Point a run at a real model: write `llm.model_ref` (+ that model's
    entry) into `<run>/.neonrp/config.json`, keeping whatever else is there.

    Returns the ref written, or None when nothing usable is configured (the
    run then resolves to the stub and the TUI says to open /settings).
    """
    from neonrp.core.paths import get_neonrp_dir
    from neonrp.core.storage import atomic_write_json
    from neonrp.presets import build_config_dict, default_model_ref

    ref = (model_ref or "").strip() or default_model_ref()
    if not ref:
        return None
    try:
        fresh = build_config_dict(ref)
    except KeyError:
        return None
    cfg_path = get_neonrp_dir(run_dir) / "config.json"
    data: dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
    for key, value in fresh.items():
        if key == "llm":
            llm = data.get("llm")
            if not isinstance(llm, dict):
                llm = data["llm"] = {}
            llm["model_ref"] = ref
        elif key == "models":
            models = data.get("models")
            if not isinstance(models, dict):
                models = data["models"] = {}
            models.update(value)
        else:
            data.setdefault(key, value)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(cfg_path, data)
    return ref


def scaffold_template_into(template_name: str, dest: Path, *, model_ref: str | None = None) -> Path:
    """Materialize a packaged template into ``dest`` as a playable world.

    Template entities + agents + runtime contract + support files +
    souls/playthrough + rule/skill samples, with the manifest initialized and
    a default-preset config seeded. Shared by the web launcher's builtin
    "new run" path and the creation flow's white-template scaffold
    (docs/WEBUI-UNIFICATION.md L0.4) — the same sequence cli.py runs
    interactively.
    """
    import json as _json

    from neonrp.commands.game import create_rule_samples, create_skill_samples
    from neonrp.core.manifest import Manifest
    from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_neonrp_dir
    from neonrp.core.proposal import UpsertTextOp
    from neonrp.core.storage import atomic_write_json, ensure_dirs
    from neonrp.core.system_proposal import apply_system_proposal
    from neonrp.core.template_assets import (
        copy_agent_from_template,
        copy_game_support_files_from_template,
        copy_runtime_contract_from_template,
        copy_souls_and_playthrough_from_template,
        list_template_agent_ids,
        load_game_template,
    )

    run_dir = dest
    run_dir.mkdir(parents=True, exist_ok=True)
    ensure_dirs(run_dir)
    atomic_write_json(get_manifest_path(run_dir), Manifest().model_dump())
    # Model config — only when absent, so a preset-aware caller can pre-write
    # one. `model_ref` is the caller's choice (the TUI passes the model the
    # current world is on); otherwise the user's own default. Never
    # `list_presets()[0]`: that is the Claude Code virtual preset (= stub)
    # whenever the `claude` CLI is installed.
    cfg_path = get_neonrp_dir(run_dir) / "config.json"
    if not cfg_path.is_file():
        seed_run_model(run_dir, model_ref)

    data_dir_name = get_data_dir_name(run_dir)
    ops = [
        UpsertTextOp(path=rel, content=_json.dumps(data, indent=2, ensure_ascii=False))
        for rel, data in load_game_template(template_name, data_dir_name)
    ]
    result = apply_system_proposal(
        run_dir,
        ops,
        rationale=f"web launcher: create game from template '{template_name}'",
        command="scaffold_builtin_run",
    )
    if not getattr(result, "success", False):
        raise RuntimeError(
            f"template scaffold failed: {getattr(result, 'error', '') or 'unknown'}"
        )
    for agent_id in list_template_agent_ids(template_name):
        copy_agent_from_template(
            run_dir, template_name=template_name, agent_id=agent_id,
            data_dir_name=data_dir_name, force=True,
        )
    copy_runtime_contract_from_template(
        run_dir, template_name=template_name, data_dir_name=data_dir_name, force=True
    )
    copy_game_support_files_from_template(
        run_dir, template_name=template_name, data_dir_name=data_dir_name, force=True
    )
    copy_souls_and_playthrough_from_template(
        run_dir, template_name=template_name, force=True
    )
    create_rule_samples(run_dir)
    create_skill_samples(run_dir)
    return run_dir


def instantiate_run(world_id: str, *, model_ref: str | None = None) -> Path:
    """Start a run of an OWNED world by copying its source into PLAYS_HOME.

    ``WORLDS_HOME/<id>`` → ``PLAYS_HOME/<id>-<ts>``. The run is the mutable
    instance: play state, the cast placed THIS run, and hosted-play saves all
    live here, never touching the library source. Raises KeyError if the world
    is not an owned world (built-ins go through create_run_dir + scaffold).
    """
    import shutil

    source = get_owned_world_dir(world_id)
    if source is None:
        raise KeyError(f"not an owned world: {world_id!r}")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = PLAYS_HOME / f"{world_id}-{timestamp}"
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    # 剥离易变引擎状态:工坊(build)会话会把 .neonrp/sessions 等写进
    # 世界源,原样拷贝会让新 run 被 _is_game_started 误判为「已开局」,
    # kickoff 拒发开场 —— 玩家卡在「世界正在苏醒」。
    # 新 run 只要内容+配置,不要建造期的会话/事件/日志。
    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        if Path(dirpath).name == ".neonrp" and Path(dirpath).parent == source:
            return {n for n in names if n in ("sessions", "events", "logs")}
        return set()

    shutil.copytree(source, run_dir, ignore=_ignore)
    # 下载/导出形状的世界把 playthrough.json 放在根(模板与 zip 的源形状),
    # 而引擎只认 .neonrp/playthrough.json(playthrough.py 的 canonical 位置)。
    # 不迁移的话,multi-agent 世界会被 conversation 静默降级成单叙述者
    # (GM 独奏、无 soul_status,伴随 souls/** 权限报错)—— hosted 新局实测
    # 踩中。语义与 template_assets.ensure_template 的迁移一致。
    root_pt = run_dir / "playthrough.json"
    dest_pt = run_dir / ".neonrp" / "playthrough.json"
    if root_pt.is_file() and not dest_pt.exists():
        dest_pt.parent.mkdir(parents=True, exist_ok=True)
        dest_pt.write_text(root_pt.read_text(encoding="utf-8"), encoding="utf-8")
    # 新局用**现在**在用的模型(TUI 里 /open 时传进来),不是源里当年选的
    # 那一个 —— 源可能还停在 stub 上(老的 /init),玩家到了新局才发现没模型。
    if model_ref:
        seed_run_model(run_dir, model_ref)
    return run_dir


def _slugify_world(name: str) -> str:
    import re
    s = re.sub(r"-\d{8}-\d{6}.*$", "", str(name))  # strip a run timestamp suffix
    s = re.sub(r"[^\w\-]", "-", s.strip()).strip("-")
    return s or "world"


def _dedupe_path(p: Path) -> Path:
    if not p.exists():
        return p
    i = 2
    while p.with_name(f"{p.name}-{i}").exists():
        i += 1
    return p.with_name(f"{p.name}-{i}")


def migrate_legacy_games() -> dict[str, int]:
    """One-shot, idempotent migration of the legacy flat ``games/`` pile into
    the world/run split. Moves (never deletes) each dir; logs every move.

    Classification:
    - ``.session-meta.json`` (hosted-play save) → ``plays/`` (a run)
    - a run of a packaged built-in world           → ``plays/`` (a run)
    - ``.worldhub.json`` (downloaded) or authored content (souls/ or game/) →
      ``worlds/<id>`` for the FIRST dir of each world (the library source),
      extra runs of the same world → ``plays/``
    - anything unrecognised is left in place (never lose data)

    Returns ``{"worlds": n, "plays": n, "skipped": n}``.
    """
    import logging
    import shutil

    log = logging.getLogger("neonrp")
    report = {"worlds": 0, "plays": 0, "skipped": 0}
    if not GAME_HOME.is_dir():
        return report
    try:
        entries = sorted(GAME_HOME.iterdir(), key=lambda p: p.name)
    except OSError:
        return report
    WORLDS_HOME.mkdir(parents=True, exist_ok=True)
    PLAYS_HOME.mkdir(parents=True, exist_ok=True)

    for d in entries:
        if not d.is_dir():
            continue
        try:
            name = d.name
            is_session = (d / SESSION_META_FILENAME).is_file()
            is_hub = (d / ".worldhub.json").is_file()
            builtin_id = infer_world_id_from_game_dir(d)
            authored = (d / "souls").is_dir() or (d / "game").is_dir()

            if is_session or (builtin_id and builtin_id in WORLDS):
                # A run of a packaged/hosted world → plays/
                target = _dedupe_path(PLAYS_HOME / name)
                shutil.move(str(d), str(target))
                report["plays"] += 1
            elif is_hub or authored:
                # An owned world (downloaded or authored). First dir of each
                # world id seeds the library; further runs become plays.
                wid = _slugify_world(name)
                lib = WORLDS_HOME / wid
                if not lib.exists():
                    shutil.move(str(d), str(lib))
                    report["worlds"] += 1
                else:
                    target = _dedupe_path(PLAYS_HOME / name)
                    shutil.move(str(d), str(target))
                    report["plays"] += 1
            else:
                report["skipped"] += 1
                continue
            log.info("migrated legacy game %s", name)
        except Exception:
            log.warning("legacy-game migration skipped for %s", d.name, exc_info=True)
            report["skipped"] += 1
    return report


def read_session_meta(game_dir: Path) -> dict[str, Any] | None:
    """Read `.session-meta.json` from a restored hosted-play save, if any.

    Shape (written by the play gateway): ``{uid, sid, kind, slug, name,
    started}``. Returns None when the file is absent or unreadable.
    """
    import json

    meta_path = game_dir / SESSION_META_FILENAME
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def list_worlds(locale: str = "en") -> list[dict[str, Any]]:
    """Return list of available worlds with display info.

    ``locale`` controls how ``display_name`` is rendered — uses the card
    i18n block when available, falls back to the source-language name.
    """
    from neonrp.core.i18n_card import card_field, card_name_for_locale

    result: list[dict[str, Any]] = []
    for world_id, info in WORLDS.items():
        if info.get("hidden"):
            continue  # e.g. soul-talk — a character mode, not a browseable world
        source_lang = info.get("source_lang", "en")
        name_i18n = info.get("name_i18n")
        desc_i18n = info.get("desc_i18n")
        name = info["name"]
        name_local = info.get("name_local", "")
        result.append({
            "id": world_id,
            "name": name,
            "name_local": name_local,
            "template": info["template"],
            "desc": card_field(desc_i18n or info["desc"], locale, source_lang=source_lang),
            "display_name": card_name_for_locale(
                name, name_local, locale, source_lang=source_lang, name_i18n=name_i18n,
            ),
            "source_lang": source_lang,
            # Picker shelf: "builtin" (the 3 engine test worlds) or "standard"
            # (polished content worlds — shown under 已下载, not 内置).
            "shelf": info.get("shelf", "builtin"),
        })
    # Append user-CREATED worlds AFTER the built-ins, deduped by id (a created
    # dir name never collides with a manifest id, but guard anyway so a future
    # built-in named like a dir can't be shadowed). These grow the 世界库 count
    # and launch via the launch-existing path, not template scaffolding.
    seen_ids = {w["id"] for w in result}
    for entry in list_owned_worlds():
        if entry["id"] in seen_ids:
            continue
        seen_ids.add(entry["id"])
        result.append(entry)
    return result


def get_world(world_id: str) -> dict[str, str]:
    """Get world info by ID.

    Resolves built-in worlds from the manifest, then falls back to an OWNED
    world under WORLDS_HOME (its info dict carries ``owned`` / ``source_dir`` so
    callers can instantiate a run). Raises KeyError when the id matches neither.
    """
    if world_id in WORLDS:
        return {**WORLDS[world_id], "id": world_id}
    for entry in list_owned_worlds():
        if entry["id"] == world_id:
            return entry
    raise KeyError(f"Unknown world: {world_id}")


def resolve_template(world_id: str, locale: str | None = None) -> str:
    """Resolve the concrete template folder for a world in a given UI locale.

    Multi-language worlds declare a ``templates`` map (locale -> template name)
    in the manifest; the game content (NPC lines, opening scene) is then served
    in the player's UI language. Resolution order: ``templates[locale]`` →
    ``templates[source_lang]`` → the entry's plain ``template`` → any first
    mapped template. Single-language worlds (no ``templates`` map) just return
    their ``template``. Display names/descriptions stay localised separately via
    the i18n blocks regardless of which content language is served.
    """
    info = WORLDS[world_id] if world_id in WORLDS else get_world(world_id)
    tmap = info.get("templates")
    if tmap:
        if locale and tmap.get(locale):
            return tmap[locale]
        src = info.get("source_lang", "en")
        if tmap.get(src):
            return tmap[src]
        if info.get("template"):
            return info["template"]
        return next(iter(tmap.values()))
    return info["template"]


def create_game_dir(world_id: str) -> Path:
    """Create a new RUN directory for the given world (back-compat alias).

    A run now lives under ``PLAYS_HOME`` (``~/.worldlines/plays/``), not the
    legacy ``games/``. Kept under the old name so existing callers (built-in
    world scaffolding) need no change. New code should call
    :func:`create_run_dir` / :func:`instantiate_run`.
    """
    return create_run_dir(world_id)


def infer_world_id_from_game_dir(game_dir: Path) -> str | None:
    """Infer the built-in world id from a game directory name, or None.

    A game instance is created as ``<world_id>-YYYYMMDD-HHMMSS`` (see
    ``create_game_dir``), so the suffix after ``<world_id>-`` must be
    timestamp-shaped. Requiring that prevents a longer, distinct world from
    being swallowed by a shorter one's prefix — e.g. ``kagura-island-lite``
    (its own hub world) must NOT be read as the built-in ``kagura-island``.
    """
    dir_name = game_dir.name
    for world_id in WORLDS:
        if dir_name.startswith(f"{world_id}-"):
            rest = dir_name[len(world_id) + 1:]
            if len(rest) >= 8 and rest[:8].isdigit():
                return world_id
    return None


def resolve_wid(game_dir: Path) -> str | None:
    """Return the stable world identifier for a game directory.

    The wid is the logical story id, suitable for grouping / filtering
    in analytics dashboards — it ignores per-run noise like
    timestamps or ``-restored-…`` suffixes:

    - Built-in worlds (in ``WORLDS``)  → the builtin id (``stone-ford``)
    - WorldHub-downloaded games        → ``.worldhub.json#slug`` (``dark-train``)
    - Anything else                    → ``None`` (caller falls back to dir name)
    """
    builtin = infer_world_id_from_game_dir(game_dir)
    if builtin is not None:
        return builtin
    try:
        from neonrp.core.worldhub import read_worldhub_meta
    except Exception:
        return None
    meta = read_worldhub_meta(game_dir)
    if meta is not None:
        slug = meta.get("slug")
        return str(slug) if slug else None
    # Restored hosted-play save (downloaded from the web): the slug lives
    # in `.session-meta.json` instead.
    sess = read_session_meta(game_dir)
    if sess is None:
        return None
    slug = sess.get("slug")
    return str(slug) if slug else None


def _is_game_started(game_dir: Path) -> bool:
    """True if the engine has logged at least one session for this game.

    `.neonrp/sessions/` is populated on first turn regardless of execution
    mode (fast / orchestrator / mcp), so the existence of any non-empty
    `.jsonl` there is the most reliable "has been played" signal —
    semantically more correct than checking `run_state.turn_count`,
    which orch-mode games don't always bump.
    """
    sessions = game_dir / ".neonrp" / "sessions"
    if not sessions.is_dir():
        return False
    try:
        for entry in sessions.iterdir():
            if entry.is_file() and entry.suffix == ".jsonl" and entry.stat().st_size > 0:
                return True
    except OSError:
        return False
    return False


def list_saved_games() -> list[dict[str, Any]]:
    """List existing game directories with metadata.

    Returns a list sorted by modification time (newest first).
    Each entry carries:

    - `path`           : absolute path
    - `world_id`       : back-compat. Builtin id (e.g. "stone-ford") or
                         "hub:<slug>" for hub-downloaded games
    - `wid`            : same as world_id for builtins; the raw slug
                         (no "hub:" prefix) for hub-downloaded games.
                         Used for grouping in the picker.
    - `display_name`   : human-readable label
    - `version`        : hub-downloaded games only (None otherwise)
    - `started`        : True if `.neonrp/sessions/` shows the engine
                         has run at least one turn. False = freshly
                         downloaded / loaded, no scene played yet.
    - `mtime`/`mtime_display`/`dir_name`
    """
    # Runs live under PLAYS_HOME (post world/run split). Legacy GAME_HOME dirs
    # are relocated here by migrate_legacy_games() at startup.
    if not PLAYS_HOME.exists():
        return []

    games = []
    for game_dir in PLAYS_HOME.iterdir():
        if not game_dir.is_dir():
            continue
        dir_name = game_dir.name

        # Skip Claude Code workspace siblings (they end with one or more -cc).
        if dir_name.endswith("-cc") or "-cc-" in dir_name:
            continue

        # Must be initialised (has .neonrp/).
        neonrp_dir = game_dir / ".neonrp"
        if not neonrp_dir.exists():
            continue

        world_id: str | None = None
        wid: str | None = None
        version: str | None = None

        # Timestamp-aware match (NOT a bare prefix) so e.g. a downloaded
        # `kagura-island-lite` isn't mislabelled as the built-in kagura.
        builtin = infer_world_id_from_game_dir(game_dir)
        if builtin is not None:
            world_id = builtin
            wid = builtin

        if world_id is not None:
            world_info = WORLDS[world_id]
            display_name = f"{world_info['name']} ({world_info['name_local']})"
        else:
            # Fall back to WorldHub metadata if this game came in via
            # `worldlines world download …`.
            from neonrp.core.worldhub import read_worldhub_meta

            wh_meta = read_worldhub_meta(game_dir)
            if wh_meta is not None:
                slug = wh_meta.get("slug") or wh_meta.get("hash") or dir_name
                version = wh_meta.get("version")
                wid = str(slug)
                world_id = f"hub:{wid}"
                name = wh_meta.get("name", dir_name)
                display_name = f"{name} (v{version})" if version else name
            else:
                # A save downloaded from hosted play and restored with
                # `load-world` — the session workdir carries
                # `.session-meta.json` rather than `.worldhub.json`.
                sess_meta = read_session_meta(game_dir)
                if sess_meta is not None:
                    slug = sess_meta.get("slug") or dir_name
                    wid = str(slug)
                    world_id = f"hub:{wid}"
                    display_name = (
                        sess_meta.get("name") or sess_meta.get("slug") or dir_name
                    )
                else:
                    # User-CREATED (`world-game-authoring`) or IMPORTED
                    # (`tavern-game-import`) world: no builtin prefix, no hub
                    # meta, no session meta — its identity lives in the world
                    # content under `game/`. These are first-class local worlds
                    # and must be uploadable/continuable, so surface them with a
                    # `local:` world_id (never collides with WORLDS, so the
                    # picker won't filter them as "abandoned builtin instances")
                    # and a name mined from the world content. Skip only if it
                    # has no real `game/` world dir (bare scaffold / cruft).
                    from neonrp.core.paths import get_game_dir

                    try:
                        data_dir = get_game_dir(game_dir)
                    except Exception:
                        data_dir = game_dir / "game"
                    if not data_dir.is_dir():
                        continue
                    wid = f"local:{dir_name}"
                    world_id = wid
                    display_name = read_local_world_name(game_dir) or dir_name

        mtime = game_dir.stat().st_mtime
        mtime_dt = datetime.fromtimestamp(mtime)

        games.append({
            "path": game_dir,
            "world_id": world_id,
            "wid": wid,
            "display_name": display_name,
            "version": version,
            "started": _is_game_started(game_dir),
            "mtime": mtime,
            "mtime_display": mtime_dt.strftime("%m/%d %H:%M"),
            "dir_name": dir_name,
        })

    # Sort by modification time, newest first
    games.sort(key=lambda g: g["mtime"], reverse=True)
    return games


def group_games_by_wid(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bucket games by wid; each bucket sorted by mtime newest-first.

    Returns a list of buckets:

      [
        {"wid": "dark-train", "display_name": "Dark Train (BRP) (v2.0)",
         "runs": [<game dict>, <game dict>, ...]},
        ...
      ]

    Buckets themselves are sorted by their newest run.
    """
    by_wid: dict[str, list[dict[str, Any]]] = {}
    for g in games:
        key = g.get("wid") or g.get("world_id") or g["dir_name"]
        by_wid.setdefault(key, []).append(g)

    buckets: list[dict[str, Any]] = []
    for wid, runs in by_wid.items():
        runs.sort(key=lambda g: g["mtime"], reverse=True)
        buckets.append({
            "wid": wid,
            "display_name": runs[0]["display_name"],
            "runs": runs,
        })
    buckets.sort(key=lambda b: b["runs"][0]["mtime"], reverse=True)
    return buckets
