"""Runtime contract for project-specific engine behavior.

This keeps engine logic data-driven instead of hardcoding project domains.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neonrp.core.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR_NAME = "game"
RUNTIME_CONTRACT_FILENAME = "runtime_contract.json"
# Agent ids treated as "the router/narrator" by convention. Order = priority
# when auto-detecting from a world's agents/ folder. `world-agent` is included
# so worlds that orchestrate through it (kagura-island, stoneford-orch) are
# recognized as their own router — i.e. narrator ≡ world-agent — instead of
# defaulting to a non-existent "narrator" and blocking delegation. `narrator`/
# `orchestrator` keep priority so classic worlds that ship them are unaffected.
# (Both this branch and main independently converged on the same fix for the
# "Agent 'narrator' not found" error on stale instances.)
CONVENTIONAL_ROUTER_AGENT_IDS: tuple[str, ...] = ("narrator", "orchestrator", "world-agent")
# 2026-08-10:模式收敛为二 —— orchestrator + multi-agent
# (产品名 MT Agent Team)。旧 "fast" 一律 normalize 到 orchestrator
# (fail-open 迁移:旧档/旧配置/hosted 传入都不报错)。
VALID_ROUTER_EXECUTION_MODES: tuple[str, ...] = ("orchestrator", "multi-agent")
_LEGACY_MODE_ALIASES: dict[str, str] = {"fast": "orchestrator"}
VALID_STARTUP_ROUTER_TYPES: tuple[str, ...] = ("sticky", "one-shot")


@dataclass(frozen=True)
class RuntimeLocationSource:
    entity_id: str
    field: str


@dataclass(frozen=True)
class RuntimeRouterContract:
    agent_id: str
    state_file: str
    startup_file: str
    execution_mode: str = "orchestrator"

    @property
    def state_entity_id(self) -> str:
        return Path(self.state_file).stem

    @property
    def startup_entity_id(self) -> str:
        return Path(self.startup_file).stem


@dataclass(frozen=True)
class RuntimeRoutingContract:
    location_source: RuntimeLocationSource
    domain_agent_map: dict[str, str]
    fallback_agent: str


@dataclass(frozen=True)
class RuntimeContextPackContract:
    seed_entity_ids: tuple[str, ...]
    max_entities: int


@dataclass(frozen=True)
class RuntimeContract:
    data_dir: str
    router: RuntimeRouterContract
    routing: RuntimeRoutingContract
    context_pack: RuntimeContextPackContract
    source: str = "default"

    @property
    def active_agent_relpath(self) -> str:
        return f"{self.data_dir}/{self.router.state_file}"

    @property
    def startup_relpath(self) -> str:
        return f"{self.data_dir}/{self.router.startup_file}"


def get_runtime_contract_path(root: Path) -> Path:
    return root / ".neonrp" / RUNTIME_CONTRACT_FILENAME


def _agent_dirs_with_json(agents_root: Path) -> list[Path]:
    """Agent dirs that actually ship an ``agent.json`` (a real, loadable agent),
    sorted by name for stable resolution."""
    try:
        return sorted(
            (c for c in agents_root.iterdir()
             if c.is_dir() and (c / "agent.json").exists()),
            key=lambda p: p.name,
        )
    except Exception:
        return []


def _normalize_agent_identity(agent_dir: Path, agent_id: str) -> None:
    """Make agent.json ``id``/``system_prompt`` consistent with the (renamed)
    dir and the system prompt file actually present (prefer ``system.md``)."""
    aj = agent_dir / "agent.json"
    data: dict[str, Any] = {}
    if aj.exists():
        try:
            loaded = json.loads(aj.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}
    data["id"] = agent_id
    sp = str(data.get("system_prompt") or "").strip()
    if not sp or not (agent_dir / sp).exists():
        for cand in ("system.md", "system_prompt.md", "persona.md"):
            if (agent_dir / cand).exists():
                data["system_prompt"] = cand
                break
        else:
            data.setdefault("system_prompt", "system.md")
    try:
        aj.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _write_minimal_world_agent(agent_dir: Path) -> None:
    """Write a minimal, playable world-agent (orchestrator narrator)."""
    agent_dir.mkdir(parents=True, exist_ok=True)
    aj = agent_dir / "agent.json"
    if not aj.exists():
        aj.write_text(json.dumps({
            "id": "world-agent",
            "name": "World Agent",
            "description": "Narrates the world and routes the player's turns.",
            "version": "1.0",
            "system_prompt": "system.md",
            "context_limit": 30,
            "triggers": [".*"],
            "priority": 100,
            "permissions": {
                "read_globs": ["game/**"],
                "write_globs": ["game/**"],
                "deny_globs": [],
                "direct_write_globs": [],
            },
            "defaults": {"context_limit": 30, "temperature": 0.7},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    sp = agent_dir / "system.md"
    if not sp.exists():
        sp.write_text(
            "You are the world agent. Narrate vividly and concretely, grounded "
            "in the world's `game/` files. Drive the scene, respond to the "
            "player's actions, and keep the story moving. Never break character "
            "or mention game mechanics.\n",
            encoding="utf-8",
        )


def _contract_router_exists_on_disk(root: Path) -> bool:
    """True when ``.neonrp/runtime_contract.json`` names a router agent that
    actually exists as ``agents/<id>/agent.json`` on disk.

    This is the idempotency gate: a world that already has a valid contract
    pointing at a present agent is left untouched by ``ensure_playable_world``.
    """
    contract_path = get_runtime_contract_path(root)
    if not contract_path.exists():
        return False
    try:
        raw = json.loads(contract_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(raw, dict):
        return False
    router = raw.get("router")
    if not isinstance(router, dict):
        return False
    agent_id = str(router.get("agent_id") or "").strip()
    if not agent_id:
        return False
    return (root / "agents" / agent_id / "agent.json").exists()


def _ensure_game_start_entry_agent(root: Path, router_id: str) -> None:
    """Guarantee game-start's ``agent_routing.entry_agent`` points at the real
    router agent, written at the TOP LEVEL where ``get_startup_entry_agent``
    reads. Idempotent: if it already matches, this is a no-op.

    Honours the world's configured ``startup_file`` (defaults to
    ``game/meta/game-start.json``). If the file is missing, a minimal startup
    file is written so the engine resolves a real entry agent rather than a
    phantom one.
    """
    contract = load_runtime_contract(root)
    gs_path = root / contract.startup_relpath
    data: dict[str, Any] = {}
    if gs_path.exists():
        try:
            loaded = json.loads(gs_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception:
            data = {}

    routing = data.get("agent_routing")
    if not isinstance(routing, dict):
        routing = {}
    current = str(routing.get("entry_agent") or "").strip()
    if current == router_id and gs_path.exists():
        return  # already correct — no-op

    routing["entry_agent"] = router_id
    routing.setdefault("router_type", "sticky")
    data["agent_routing"] = routing
    # If the file was freshly synthesised, give it enough shape to be valid.
    data.setdefault("id", Path(contract.startup_relpath).stem)
    data.setdefault("kind", "meta")
    data.setdefault("name", "Game Start")
    try:
        gs_path.parent.mkdir(parents=True, exist_ok=True)
        gs_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def ensure_playable_world(world_dir: Path) -> str:
    """Guarantee ``world_dir`` is *playable* and return the resolved router id.

    A world is playable when (a) a recognized router agent exists on disk as
    ``agents/<id>/agent.json``, (b) ``.neonrp/runtime_contract.json`` points
    ``router.agent_id`` at it, and (c) game-start's top-level
    ``agent_routing.entry_agent`` names it. Authored/imported worlds often miss
    one or more of these, which makes play error with "Agent '<id>' not found".

    Resolution (shared by both the create path and the import/play path):

      1. If a valid contract already names a router agent that EXISTS on disk,
         this is a NO-OP (so it is safe to call on built-in worlds every play).
      2. Otherwise resolve the world's real controlling agent — a conventional
         router id (``narrator``/``orchestrator``/``world-agent``) present on
         disk; else the sole generated agent, NORMALIZED to
         ``agents/world-agent/`` (rename dir + fix agent.json id/system_prompt);
         else (multiple, none conventional) point the contract at one
         (alphabetical, for stability); else (no agents at all) write a minimal
         ``agents/world-agent/``.
      3. Write ``.neonrp/runtime_contract.json`` (``execution_mode:
         "orchestrator"``) and set game-start's top-level entry_agent.

    Returns the resolved router agent id (always present on disk afterwards).
    """
    world_dir = Path(world_dir)

    # 1. Idempotent fast-path: a valid contract + a present router agent means
    #    nothing to do (built-ins, already-fixed worlds).
    if _contract_router_exists_on_disk(world_dir):
        contract_path = get_runtime_contract_path(world_dir)
        try:
            raw = json.loads(contract_path.read_text(encoding="utf-8"))
            router_id = str(raw["router"]["agent_id"]).strip()
        except Exception:
            router_id = resolve_router_agent_id(world_dir)
        return router_id

    agents_root = world_dir / "agents"
    agents_root.mkdir(parents=True, exist_ok=True)

    dirs = _agent_dirs_with_json(agents_root)
    existing_ids = {d.name for d in dirs}

    # 2. Resolve the router agent.
    router_id = next(
        (cid for cid in CONVENTIONAL_ROUTER_AGENT_IDS if cid in existing_ids),
        None,
    )
    if router_id is None:
        if len(dirs) == 1:
            src = dirs[0]
            dst = agents_root / "world-agent"
            if src.name != "world-agent":
                try:
                    src.rename(dst)
                except Exception:
                    dst = src  # rename failed — keep the original dir as router
            else:
                dst = src
            router_id = dst.name
            _normalize_agent_identity(dst, router_id)
        elif len(dirs) >= 2:
            router_id = dirs[0].name
        else:
            router_id = "world-agent"
            _write_minimal_world_agent(agents_root / router_id)

    # 3a. Write/refresh the runtime contract (orchestrator, real router id).
    contract_path = get_runtime_contract_path(world_dir)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {}
    if contract_path.exists():
        try:
            loaded = json.loads(contract_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}
    router = raw.get("router")
    if not isinstance(router, dict):
        router = {}
    router["agent_id"] = router_id
    router.setdefault("execution_mode", "orchestrator")
    router.setdefault("state_file", "meta/active-agent.json")
    router.setdefault("startup_file", "meta/game-start.json")
    raw["router"] = router
    try:
        contract_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass

    # 3b. Point game-start's top-level entry_agent at the real router.
    _ensure_game_start_entry_agent(world_dir, router_id)

    return router_id


def load_startup_payload(root: Path) -> dict[str, Any] | None:
    """Load the configured startup file payload if present and valid."""
    contract = load_runtime_contract(root)
    path = root / contract.startup_relpath
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse startup file '%s': %s", path, exc)
        return None
    return raw if isinstance(raw, dict) else None


def get_startup_entry_agent(root: Path) -> str | None:
    """Return the entry agent defined by the startup file, if any."""
    payload = load_startup_payload(root)
    if not isinstance(payload, dict):
        return None
    routing = payload.get("agent_routing")
    if not isinstance(routing, dict):
        return None
    entry_agent = str(routing.get("entry_agent", "") or "").strip()
    return entry_agent or None


def get_startup_router_type(root: Path) -> str | None:
    """Return startup router type defined by the startup file.

    Current fast-mode startup only guarantees sticky semantics.
    Any unsupported value falls back to ``sticky``.
    """
    payload = load_startup_payload(root)
    if not isinstance(payload, dict):
        return None
    routing = payload.get("agent_routing")
    if not isinstance(routing, dict):
        return None
    raw = str(routing.get("router_type", "") or "").strip().lower().replace("_", "-")
    if not raw:
        return "sticky"
    if raw not in VALID_STARTUP_ROUTER_TYPES:
        logger.warning("Unknown startup router_type '%s'; falling back to sticky", raw)
        return "sticky"
    if raw == "one-shot":
        logger.warning("startup router_type=one-shot is not implemented; falling back to sticky")
        return "sticky"
    return raw


_DATA_DIRS: dict[tuple[str, int, int], str] = {}


def load_data_dir(root: Path) -> str:
    """``load_runtime_contract(root).data_dir`` without inferring the router / routing (config + every agents/*.json).

    paths.get_data_dir_name asks this thousands of times in one world build (every loader, every register) and only
    ever needs the folder name: the inferred contract always says ``game``, so only the contract file can change it.
    The file's answer is remembered by (path, mtime, size)."""
    path = get_runtime_contract_path(root)
    try:
        st = path.stat()
    except OSError:
        return DEFAULT_DATA_DIR_NAME
    key = (str(path), st.st_mtime_ns, st.st_size)
    hit = _DATA_DIRS.get(key)
    if hit is not None:
        return hit
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — load_runtime_contract logs it and falls back the same way
        raw = None
    out = _normalize_rel_segment(raw.get("data_dir"), fallback=DEFAULT_DATA_DIR_NAME) if isinstance(raw, dict) else DEFAULT_DATA_DIR_NAME
    if len(_DATA_DIRS) > 1024:
        _DATA_DIRS.clear()
    _DATA_DIRS[key] = out
    return out


def load_runtime_contract(root: Path) -> RuntimeContract:
    """Load the effective runtime contract for a project."""
    base = _infer_runtime_contract(root)
    path = get_runtime_contract_path(root)
    if not path.exists():
        return base

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse runtime contract '%s': %s", path, exc)
        return base

    if not isinstance(raw, dict):
        logger.warning("Runtime contract '%s' must be a JSON object", path)
        return base

    return _merge_runtime_contract(base, raw, source="file")


def _infer_runtime_contract(root: Path) -> RuntimeContract:
    narrator_agent_id = _get_configured_router_agent_id(root)
    router_state_file = "meta/active-agent.json"
    router_startup_file = "meta/game-start.json"
    data_dir = DEFAULT_DATA_DIR_NAME
    location_source = RuntimeLocationSource(entity_id="player", field="location")
    domain_agent_map = _infer_domain_agent_map(root, narrator_agent_id)
    seed_entity_ids = tuple(
        dict.fromkeys(
            [
                location_source.entity_id,
                Path(router_state_file).stem,
                Path(router_startup_file).stem,
            ]
        )
    )
    return RuntimeContract(
        data_dir=data_dir,
        router=RuntimeRouterContract(
            agent_id=narrator_agent_id,
            state_file=router_state_file,
            startup_file=router_startup_file,
            execution_mode="orchestrator",
        ),
        routing=RuntimeRoutingContract(
            location_source=location_source,
            domain_agent_map=domain_agent_map,
            fallback_agent=narrator_agent_id,
        ),
        context_pack=RuntimeContextPackContract(seed_entity_ids=seed_entity_ids, max_entities=6),
        source="inferred",
    )


def _merge_runtime_contract(base: RuntimeContract, raw: dict[str, Any], *, source: str) -> RuntimeContract:
    data_dir = _normalize_rel_segment(raw.get("data_dir"), fallback=base.data_dir)

    router_raw = raw.get("router")
    router = base.router
    if isinstance(router_raw, dict):
        router = RuntimeRouterContract(
            agent_id=_normalize_name(router_raw.get("agent_id"), fallback=base.router.agent_id),
            state_file=_normalize_relpath(router_raw.get("state_file"), fallback=base.router.state_file),
            startup_file=_normalize_relpath(router_raw.get("startup_file"), fallback=base.router.startup_file),
            execution_mode=_normalize_router_execution_mode(
                router_raw.get("execution_mode"), fallback=base.router.execution_mode
            ),
        )

    routing_raw = raw.get("routing")
    routing = base.routing
    if isinstance(routing_raw, dict):
        location_source_raw = routing_raw.get("location_source")
        location_source = base.routing.location_source
        if isinstance(location_source_raw, dict):
            location_source = RuntimeLocationSource(
                entity_id=_normalize_name(location_source_raw.get("entity_id"), fallback=base.routing.location_source.entity_id),
                field=_normalize_name(location_source_raw.get("field"), fallback=base.routing.location_source.field),
            )

        domain_agent_map = _normalize_domain_agent_map(routing_raw.get("domain_agent_map"), fallback=base.routing.domain_agent_map)
        fallback_agent = _normalize_name(routing_raw.get("fallback_agent"), fallback=base.routing.fallback_agent)
        routing = RuntimeRoutingContract(
            location_source=location_source,
            domain_agent_map=domain_agent_map,
            fallback_agent=fallback_agent,
        )

    context_pack_raw = raw.get("context_pack")
    context_pack = base.context_pack
    if isinstance(context_pack_raw, dict):
        seed_entity_ids = _normalize_seed_ids(context_pack_raw.get("seed_entity_ids"), fallback=base.context_pack.seed_entity_ids)
        max_entities = _normalize_positive_int(context_pack_raw.get("max_entities"), fallback=base.context_pack.max_entities)
        context_pack = RuntimeContextPackContract(seed_entity_ids=seed_entity_ids, max_entities=max_entities)

    return RuntimeContract(
        data_dir=data_dir,
        router=router,
        routing=routing,
        context_pack=context_pack,
        source=source,
    )


def _infer_domain_agent_map(root: Path, narrator_agent_id: str) -> dict[str, str]:
    agents_root = root / "agents"
    if not agents_root.exists():
        return {}

    router_aliases = get_router_agent_aliases(narrator_agent_id)
    mapping: dict[str, str] = {}
    for agent_dir in sorted(child for child in agents_root.iterdir() if child.is_dir()):
        agent_id = agent_dir.name.strip()
        if not agent_id or agent_id in router_aliases:
            continue
        agent_json = agent_dir / "agent.json"
        if not agent_json.exists():
            continue
        try:
            payload = json.loads(agent_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        sticky_domain_kinds = payload.get("sticky_domain_kinds")
        if not isinstance(sticky_domain_kinds, list):
            continue
        for raw_kind in sticky_domain_kinds:
            kind = _normalize_name(raw_kind, fallback="")
            if kind and kind not in mapping:
                mapping[kind] = agent_id
    return mapping


def _get_configured_router_agent_id(root: Path) -> str:
    return resolve_router_agent_id(root)


def get_router_agent_aliases(router_agent_id: str | None = None) -> set[str]:
    aliases = {agent_id for agent_id in CONVENTIONAL_ROUTER_AGENT_IDS if agent_id}
    normalized = _normalize_name(router_agent_id, fallback="")
    if normalized:
        aliases.add(normalized)
    return aliases


def resolve_router_agent_id(root: Path) -> str:
    try:
        configured = str(load_config(root).tui.narrator_agent_id or "").strip()
    except Exception:
        configured = ""

    if configured and configured not in CONVENTIONAL_ROUTER_AGENT_IDS:
        return configured

    agents_root = root / "agents"
    if agents_root.exists():
        existing_ids = {
            child.name.strip()
            for child in agents_root.iterdir()
            if child.is_dir() and (child / "agent.json").exists() and child.name.strip()
        }
        for candidate in CONVENTIONAL_ROUTER_AGENT_IDS:
            if candidate in existing_ids:
                return candidate

    if configured:
        return configured
    return CONVENTIONAL_ROUTER_AGENT_IDS[0]


def get_router_execution_mode(root: Path) -> str:
    contract = load_runtime_contract(root)
    return _normalize_router_execution_mode(contract.router.execution_mode, fallback="orchestrator")


def _read_raw_contract(root: Path) -> dict[str, Any]:
    """Best-effort raw parse of ``.neonrp/runtime_contract.json``.

    Used to read declarative markers (e.g. ``surface_modes``) that aren't part
    of the typed :class:`RuntimeContract` dataclass. Returns ``{}`` on any
    missing/malformed file.
    """
    path = get_runtime_contract_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def get_surface_modes(root: Path) -> dict[str, str] | None:
    """Per-render-surface execution modes, if the world declares them.

    A world becomes surface-dependent ONLY by shipping a ``surface_modes`` map
    in its runtime_contract, e.g. Soul Talk::

        "surface_modes": {"web": "multi-agent", "tui": "orchestrator"}

    Returns the normalized ``{surface: execution_mode}`` map (surfaces
    lower-cased, modes validated against :data:`VALID_ROUTER_EXECUTION_MODES`),
    or ``None`` when the world has no marker (the overwhelming majority — they
    keep their single baked mode on every surface).
    """
    raw = _read_raw_contract(root).get("surface_modes")
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for surface, mode in raw.items():
        s = _normalize_name(surface, fallback="").lower()
        m = _normalize_router_execution_mode(mode, fallback="")
        if s and m:
            out[s] = m
    return out or None


def get_surface_mode_router(root: Path, execution_mode: str) -> str | None:
    """Router agent id a surface-mode world wants for a given execution mode.

    Reads the optional ``surface_mode_routers`` map (e.g. Soul Talk maps
    ``multi-agent`` → ``narrator``, ``orchestrator`` → ``world-agent``). Returns
    ``None`` when unmapped, so callers fall back to normal router resolution.
    """
    raw = _read_raw_contract(root).get("surface_mode_routers")
    if not isinstance(raw, dict):
        return None
    mode = _normalize_router_execution_mode(execution_mode, fallback="")
    if not mode:
        return None
    return _normalize_name(raw.get(mode), fallback="") or None


def apply_surface_execution_mode(root: Path, render_surface: str) -> str | None:
    """Pin a surface-mode world's execution mode + router to the render surface.

    No-op (returns ``None``) for ordinary worlds — only worlds that declare a
    ``surface_modes`` marker (Soul Talk) are surface-dependent. For those, this
    selects the mode for ``render_surface`` (e.g. ``web`` → multi-agent,
    ``tui`` → orchestrator), writes it via :func:`set_router_execution_mode`,
    points ``router.agent_id`` + game-start's ``entry_agent`` at the matching
    router (so play resolves the real agent), and returns the applied mode.

    Surfaces not present in the marker (or absent markers) leave the world's
    baked mode untouched.
    """
    modes = get_surface_modes(root)
    if not modes:
        return None
    surface = (render_surface or "").strip().lower()
    mode = modes.get(surface)
    if not mode:
        return None

    set_router_execution_mode(root, mode)

    # Point the contract's router + game-start entry_agent at the matching
    # router so both web (get_startup_entry_agent) and TUI (first-turn entry)
    # resolve a real agent for the chosen mode.
    router_id = get_surface_mode_router(root, mode)
    if router_id and (root / "agents" / router_id / "agent.json").exists():
        raw = _read_raw_contract(root)
        router = raw.get("router")
        if not isinstance(router, dict):
            router = {}
        router["agent_id"] = router_id
        raw["router"] = router
        try:
            get_runtime_contract_path(root).write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        try:
            _ensure_game_start_entry_agent(root, router_id)
        except Exception:
            pass
    return mode


def is_soul_world(root: Path) -> bool:
    """True when the world is structured for multi-agent — it ships a
    ``playthrough.json`` (the world↔soul-team binding; each cast soul runs as
    its own agent). This is a property of the world's STRUCTURE, not a
    togglable runtime flag. An empty-cast multi-agent shell (e.g. Soul Talk
    before you bring a character in) still counts — the structure is there."""
    from neonrp.core.playthrough import read_playthrough

    try:
        return read_playthrough(root) is not None
    except Exception:  # noqa: BLE001 — a malformed manifest is not a soul world here
        return False


def valid_execution_modes(root: Path) -> tuple[str, ...]:
    """Execution modes compatible with this world's structure.

    Soul worlds (souls + playthrough) run ``multi-agent`` — switching to
    fast/orchestrator would orphan the souls. Flat worlds (no souls) run
    ``fast`` or ``orchestrator`` (one protocol, freely interchangeable) and
    cannot be *switched* to multi-agent — that needs souls, i.e. a rebuild.
    Use this to gate user-facing mode switches (``neonrp mode`` /
    ``/router-mode``); the low-level setter stays unconstrained for
    instantiation, which writes a world's own baked mode.

    Surface-mode worlds (those declaring a ``surface_modes`` marker, e.g. Soul
    Talk) are the ONE exception: they legitimately run different modes on
    different render surfaces, so every mode named in the marker is valid. All
    other worlds — ordinary soul worlds and flat worlds alike — keep the
    contract above exactly.
    """
    surface_modes = get_surface_modes(root)
    if surface_modes:
        # Preserve declaration order, dedup. Keep multi-agent first when present
        # so the showcase mode reads as the primary.
        seen: dict[str, None] = {}
        for mode in surface_modes.values():
            seen.setdefault(mode, None)
        ordered = list(seen)
        if "multi-agent" in seen:
            ordered = ["multi-agent"] + [m for m in ordered if m != "multi-agent"]
        return tuple(ordered)
    return ("multi-agent",) if is_soul_world(root) else ("orchestrator",)


def set_router_execution_mode(root: Path, execution_mode: str) -> str:
    normalized = _normalize_router_execution_mode(execution_mode, fallback="")
    if not normalized:
        raise ValueError(
            f"Invalid router execution mode: {execution_mode}. "
            f"Use one of: {', '.join(VALID_ROUTER_EXECUTION_MODES)}"
        )

    path = get_runtime_contract_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except Exception:
            raw = {}

    router = raw.get("router")
    if not isinstance(router, dict):
        router = {}
        raw["router"] = router
    router["execution_mode"] = normalized
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def _normalize_router_execution_mode(value: object, *, fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        normalized = _LEGACY_MODE_ALIASES.get(normalized, normalized)
        if normalized in VALID_ROUTER_EXECUTION_MODES:
            return normalized
    return fallback


def _normalize_name(value: object, *, fallback: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return fallback


def _normalize_rel_segment(value: object, *, fallback: str) -> str:
    candidate = _normalize_relpath(value, fallback=fallback)
    if "/" in candidate:
        return fallback
    return candidate


def _normalize_relpath(value: object, *, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.replace("\\", "/").strip().strip("/")
    if not normalized or normalized.startswith(".") or ".." in normalized.split("/"):
        return fallback
    return normalized


def _normalize_positive_int(value: object, *, fallback: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return fallback


def _normalize_domain_agent_map(value: object, *, fallback: dict[str, str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return dict(fallback)
    normalized: dict[str, str] = {}
    for raw_domain, raw_agent in value.items():
        domain = _normalize_name(raw_domain, fallback="")
        agent_id = _normalize_name(raw_agent, fallback="")
        if domain and agent_id and domain not in normalized:
            normalized[domain.lower()] = agent_id
    return normalized or dict(fallback)


def _normalize_seed_ids(value: object, *, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return fallback
    seed_ids: list[str] = []
    for raw in value:
        seed_id = _normalize_name(raw, fallback="")
        if seed_id and seed_id not in seed_ids:
            seed_ids.append(seed_id)
    return tuple(seed_ids or fallback)
