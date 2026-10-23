"""Playthrough manifest — the session-layer world↔soul binding.

Parser + schema for `playthrough.json` (schema_version 2), the authoritative
record of which world instance is bound to which soul instances plus the live
world-agent team. Spec: docs/M17_COMMIT_VERSIONING_DESIGN.md §2.4 and
docs/WORLD_SOUL_FOLDERS.md §3.4.

On-disk location: `<game_dir>/.neonrp/playthrough.json`.

This is a pure schema + parser leaf module: no turn-loop or session coupling.
"""

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# The only schema this module understands. A mismatch is a hard error, never a
# silent migration: the manifest is identity ground-truth, so guessing how to
# upgrade an unknown layout risks corrupting world↔soul bindings.
SCHEMA_VERSION = 2

# Relative location of the manifest inside a game working tree (§3.4 / §4).
_MANIFEST_RELPATH = Path(".neonrp") / "playthrough.json"


class PlaythroughError(Exception):
    """Raised on a malformed manifest, missing required field, or a
    schema_version that does not match this module's expectation.

    Absence of the file is NOT an error (legacy single-player game); callers
    receive ``None`` from :func:`read_playthrough` in that case.
    """


@dataclass(frozen=True)
class WorldRef:
    """The single world instance this playthrough is bound to."""

    wid: str
    instance_id: str
    version_hash: str
    head_commit: str


@dataclass(frozen=True)
class TeamAgent:
    """One sub-agent entry in the seeded world-agent team."""

    id: str
    role: str
    # Most agents are multi-instance domain workers; only the orchestrator is
    # flagged singleton in the spec roster, so it defaults to False.
    singleton: bool = False


@dataclass(frozen=True)
class WorldAgentTeam:
    """Runtime snapshot of the world's sub-agent roster.

    Seeded at playthrough creation from the world bundle's creator-versioned
    `game/agents/manifest.json@<version_hash>`; thereafter authoritative here.
    """

    seeded_from: str
    agents: list[TeamAgent] = field(default_factory=list)


@dataclass(frozen=True)
class SoulRef:
    """One forked soul instance participating in this playthrough."""

    sid: str
    instance_id: str
    version_hash: str
    head_commit: str
    role: str


@dataclass(frozen=True)
class PlayerRef:
    """One human player participating in this playthrough (M20).

    The player is a first-class **non-soul** entity (M20 §1). ``state_path``
    is its private master folder (``game/players/<pid>/``); legacy
    single-player worlds may point it at the ``game/player/`` N=1 alias.
    There is no ``role`` — a player is never a soul.
    """

    pid: str
    name: str
    state_path: str
    kind: str = "human"


@dataclass(frozen=True)
class Playthrough:
    """The full session-layer binding (schema_version 2)."""

    schema_version: int
    playthrough_id: str
    world: WorldRef
    world_agent_team: WorldAgentTeam
    souls: list[SoulRef]
    created_at: str
    # M20: human players (one per end-user; N=1 single-player). OPTIONAL +
    # default-empty so every pre-M20 playthrough.json still parses unchanged
    # (legacy = no players[] ⇒ the game/player/ N=1 alias is used by callers).
    players: tuple[PlayerRef, ...] = ()
    # M18 §2.3: instance_ids of the souls currently *active* (registered as
    # live character-agents this turn). The full cast lives in ``souls``; the
    # active subset is a runtime dial the world-agent rewrites as characters
    # enter/leave a scene (see :func:`set_active_souls`). Absent in the
    # manifest ⇒ every soul is active (legacy "register all" behaviour).
    active_souls: tuple[str, ...] = ()
    # M22: per-turn integration routing (file-as-router for integrators).
    # Each entry: {"world_agent": "world-agent" | "loc:<node>",
    #              "location": <node>, "souls": [instance_id...]}.
    # Written by scene-understanding each turn; absent ⇒ everything is
    # integrated by the primary world-agent (pre-M22 behaviour).
    integrations: tuple[dict[str, Any], ...] = ()

    def active_soul_refs(self) -> list[SoulRef]:
        """The :class:`SoulRef`s whose ``instance_id`` is in ``active_souls``,
        in manifest order. This is the exact set the M18 runtime registers as
        live character-agents for the turn."""
        active = set(self.active_souls)
        return [s for s in self.souls if s.instance_id in active]


def _manifest_path(game_dir: Path) -> Path:
    return game_dir / _MANIFEST_RELPATH


def _require(obj: dict[str, Any], key: str, where: str) -> Any:
    # Membership rather than truthiness: an empty souls list or empty string is
    # structurally valid; only an absent key is a schema violation here.
    if key not in obj:
        raise PlaythroughError(f"playthrough.json: missing required field '{key}' in {where}")
    return obj[key]


def _require_dict(obj: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = _require(obj, key, where)
    if not isinstance(value, dict):
        raise PlaythroughError(
            f"playthrough.json: field '{key}' in {where} must be an object, got {type(value).__name__}"
        )
    return value


def _require_list(obj: dict[str, Any], key: str, where: str) -> list[Any]:
    value = _require(obj, key, where)
    if not isinstance(value, list):
        raise PlaythroughError(
            f"playthrough.json: field '{key}' in {where} must be an array, got {type(value).__name__}"
        )
    return value


def _parse_world(raw: dict[str, Any]) -> WorldRef:
    return WorldRef(
        wid=_require(raw, "wid", "world"),
        instance_id=_require(raw, "instance_id", "world"),
        version_hash=_require(raw, "version_hash", "world"),
        head_commit=_require(raw, "head_commit", "world"),
    )


def _parse_team(raw: dict[str, Any]) -> WorldAgentTeam:
    agents_raw = _require_list(raw, "agents", "world_agent_team")
    agents: list[TeamAgent] = []
    for i, a in enumerate(agents_raw):
        if not isinstance(a, dict):
            raise PlaythroughError(
                f"playthrough.json: world_agent_team.agents[{i}] must be an object"
            )
        where = f"world_agent_team.agents[{i}]"
        agents.append(
            TeamAgent(
                id=_require(a, "id", where),
                role=_require(a, "role", where),
                # singleton is optional in the spec roster; absence means False.
                singleton=bool(a.get("singleton", False)),
            )
        )
    return WorldAgentTeam(
        seeded_from=_require(raw, "seeded_from", "world_agent_team"),
        agents=agents,
    )


def _parse_souls(raw: list[Any]) -> list[SoulRef]:
    souls: list[SoulRef] = []
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise PlaythroughError(f"playthrough.json: souls[{i}] must be an object")
        where = f"souls[{i}]"
        souls.append(
            SoulRef(
                sid=_require(s, "sid", where),
                instance_id=_require(s, "instance_id", where),
                version_hash=_require(s, "version_hash", where),
                head_commit=_require(s, "head_commit", where),
                role=_require(s, "role", where),
            )
        )
    return souls


def _parse_players(raw: Any) -> tuple[PlayerRef, ...]:
    """Parse the OPTIONAL M20 ``players[]`` list.

    Tolerant by design: absent / non-list ⇒ ``()`` (legacy single-player; the
    ``game/player/`` N=1 alias is used by callers). Present entries must carry
    ``pid``; ``name``/``state_path``/``kind`` default sensibly so a minimal
    ``[{"pid": "..."}]`` is valid.
    """
    if not isinstance(raw, list):
        return ()
    players: list[PlayerRef] = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            raise PlaythroughError(f"playthrough.json: players[{i}] must be an object")
        pid = _require(p, "pid", f"players[{i}]")
        players.append(
            PlayerRef(
                pid=str(pid),
                name=str(p.get("name") or pid),
                state_path=str(p.get("state_path") or "game/player"),
                kind=str(p.get("kind") or "human"),
            )
        )
    return tuple(players)


def read_playthrough(game_dir: Path) -> Playthrough | None:
    """Read `<game_dir>/.neonrp/playthrough.json`.

    Returns ``None`` if the file does not exist — that is the legacy
    single-player case, not an error. Raises :class:`PlaythroughError` on
    malformed JSON, a missing required field, or a schema_version mismatch.
    """
    path = _manifest_path(game_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Absence is meaningful, not an error: legacy single-player game.
        return None

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise PlaythroughError(f"playthrough.json: malformed JSON: {e}") from e

    if not isinstance(data, dict):
        raise PlaythroughError(
            f"playthrough.json: top-level value must be an object, got {type(data).__name__}"
        )

    found_version = _require(data, "schema_version", "<root>")
    if found_version != SCHEMA_VERSION:
        raise PlaythroughError(
            f"playthrough.json: schema_version mismatch — found {found_version!r}, "
            f"expected {SCHEMA_VERSION}. Refusing to migrate automatically."
        )

    souls = _parse_souls(_require_list(data, "souls", "<root>"))

    # active_souls is optional. Absent ⇒ the whole cast is active (preserves
    # the pre-M18.2 "register every playthrough soul" behaviour, so existing
    # worlds/tests are byte-identical). Present ⇒ must be a list of strings;
    # ids that don't resolve to a soul are kept (a future spawn may add them)
    # but simply won't match anything in active_soul_refs().
    raw_active = data.get("active_souls")
    if raw_active is None:
        active_souls: tuple[str, ...] = tuple(s.instance_id for s in souls)
    else:
        if not isinstance(raw_active, list):
            raise PlaythroughError(
                "playthrough.json: field 'active_souls' in <root> must be an "
                f"array, got {type(raw_active).__name__}"
            )
        active_souls = tuple(str(x) for x in raw_active)

    # integrations is optional (M22). Absent / malformed ⇒ () — everything
    # integrated by the primary world-agent, pre-M22 behaviour.
    raw_integrations = data.get("integrations")
    integrations: tuple[dict[str, Any], ...] = ()
    if isinstance(raw_integrations, list):
        integrations = tuple(e for e in raw_integrations if isinstance(e, dict))

    return Playthrough(
        schema_version=SCHEMA_VERSION,
        playthrough_id=_require(data, "playthrough_id", "<root>"),
        world=_parse_world(_require_dict(data, "world", "<root>")),
        world_agent_team=_parse_team(_require_dict(data, "world_agent_team", "<root>")),
        souls=souls,
        created_at=_require(data, "created_at", "<root>"),
        players=_parse_players(data.get("players")),
        active_souls=active_souls,
        integrations=integrations,
    )


def _to_dict(pt: Playthrough) -> dict[str, Any]:
    return {
        "schema_version": pt.schema_version,
        "playthrough_id": pt.playthrough_id,
        "world": {
            "wid": pt.world.wid,
            "instance_id": pt.world.instance_id,
            "version_hash": pt.world.version_hash,
            "head_commit": pt.world.head_commit,
        },
        "world_agent_team": {
            "seeded_from": pt.world_agent_team.seeded_from,
            "agents": [
                {"id": a.id, "role": a.role, "singleton": a.singleton}
                for a in pt.world_agent_team.agents
            ],
        },
        "souls": [
            {
                "sid": s.sid,
                "instance_id": s.instance_id,
                "version_hash": s.version_hash,
                "head_commit": s.head_commit,
                "role": s.role,
            }
            for s in pt.souls
        ],
        "created_at": pt.created_at,
        "players": [
            {
                "pid": p.pid,
                "name": p.name,
                "state_path": p.state_path,
                "kind": p.kind,
            }
            for p in pt.players
        ],
        "active_souls": list(pt.active_souls),
        "integrations": [dict(e) for e in pt.integrations],
    }


def write_playthrough(game_dir: Path, pt: Playthrough) -> None:
    """Atomically write the manifest to `<game_dir>/.neonrp/playthrough.json`.

    Writes a sibling temp file then renames it, so a crash mid-write can never
    leave a half-written identity manifest on disk.
    """
    path = _manifest_path(game_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    payload = json.dumps(_to_dict(pt), indent=2, ensure_ascii=False) + "\n"
    try:
        tmp.write_text(payload, encoding="utf-8")
        # Rename is atomic within the same directory on POSIX/Windows.
        os.replace(tmp, path)
    finally:
        # Best-effort cleanup if the rename never happened (e.g. write failed).
        if tmp.exists():
            tmp.unlink()


def set_active_souls(
    game_dir: Path,
    instance_ids: list[str],
    *,
    integrations: list[dict[str, Any]] | None = None,
) -> Playthrough:
    """Rewrite only the live active-soul set (and, when given, the M22
    integration routing) atomically, leaving the rest of the identity
    manifest untouched.

    This is the dynamic dial behind M18 activate/deactivate — written by the
    deterministic scene-understanding step each turn. Order is preserved; the
    runtime intersects it with the cast in :meth:`Playthrough.active_soul_refs`
    and the concurrent-character cap is enforced separately by the runtime.
    Returns the re-read manifest so the caller sees exactly what landed.
    """
    pt = read_playthrough(game_dir)
    if pt is None:
        raise PlaythroughError(
            f"set_active_souls: no playthrough.json under {game_dir}"
        )
    updated = replace(pt, active_souls=tuple(instance_ids))
    if integrations is not None:
        updated = replace(updated, integrations=tuple(integrations))
    write_playthrough(game_dir, updated)
    reread = read_playthrough(game_dir)
    assert reread is not None  # we just wrote it
    return reread
