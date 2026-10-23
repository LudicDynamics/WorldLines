"""Pure commit composition for M17/M18 turn-commit subsystem.

This module is the PURE (non-IO) core of the commit-versioning subsystem:
in-memory dataclasses + deterministic, content-addressed commit-id
derivation. It deliberately performs **no disk IO** and does **not**
implement ``land_commit`` (that is the integration/Phase-D step that
writes blobs and updates refs; it depends on machinery outside this
module's scope).

Design references:
- M17 §2   — commit_id derivation formulas
- M17 §2.1 — world commit schema
- M17 §2.2 — soul commit schema (carries NO world hashes)
- M18 §3.4 — TurnCollection shape, schema_version 2

Hash determinism: a commit_id is ``sha256(canonical)[:12]``. The
canonical form is JSON with ``sort_keys=True`` and fixed compact
separators, UTF-8 / ASCII-escaped. Two processes on any machine encode
the same logical content to the *same bytes*, so the id is portable.

Folder hashing: M17 §5.2 mandates the M4 tree-hash in
``core/hashing.py`` is reused verbatim — no second hash implementation.
That API (``compute_game_hash``) takes a directory ``Path``. Per the
build spec, callers therefore precompute folder hashes (M18 §3.4 step 5
computes them in-memory before this pure layer runs) and pass the
resulting hash strings into the dataclasses. :func:`folder_hash` is a
thin, explicit re-export of that one API for callers that *do* have a
path, so this module never grows its own hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from neonrp.core.hashing import compute_game_hash

# Re-export the M4 tree-hash so callers that hold a directory path use
# the one canonical implementation. We never reimplement folder hashing.
folder_hash = compute_game_hash

SCHEMA_VERSION = 2

# Soul states (M18 §3.4 / §3.4-bis) that mean "this soul did NOT produce a
# fresh, committable mutation this turn" -> passthrough (M17 open-q #3,
# M18 §3.4 last bullet): reuse the prior soul_commit_id, allocate nothing.
_PASSTHROUGH_STATES = frozenset({"interrupted", "degraded"})


def _canonical(payload: dict[str, Any]) -> bytes:
    """Serialize a dict to byte-deterministic canonical JSON.

    sort_keys makes field *order* irrelevant (the M17 §2 formulas list
    fields in an order, but a sorted canonical form is what guarantees a
    byte-identical result across processes/machines regardless of dict
    construction order). Fixed separators drop incidental whitespace;
    ensure_ascii pins the byte encoding so no locale/codec can perturb it.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _commit_id(payload: dict[str, Any]) -> str:
    """sha256-prefix per M17 §2: first 12 hex chars of the digest."""
    return hashlib.sha256(_canonical(payload)).hexdigest()[:12]


# --------------------------------------------------------------------------
# TurnCollection inputs (M18 §3.4) — assembled in-memory by the world-agent.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CharacterDelta:
    """One character-agent's in-memory turn output (M18 §3.4 step 2).

    ``soul_folder_hash`` is precomputed (M18 §3.4 step 5) — typically via
    :func:`folder_hash` on the soul's working tree. ``state`` drives
    passthrough handling (see :data:`_PASSTHROUGH_STATES`).
    """

    sid: str
    instance_id: str
    version_hash: str
    state: str  # "completed" | "interrupted" | "degraded" | ...
    soul_folder_hash: str
    files_modified: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[Any] = field(default_factory=list)
    outbox: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class WorldDelta:
    """World-agent's own ``game/`` delta for this turn (M18 §3.4 step 4)."""

    wid: str
    instance_id: str
    version_hash: str
    game_folder_hash: str
    session_log_hash: str
    files_modified: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class TurnCollection:
    """In-memory accumulator for one turn (M18 §3.4, schema_version 2)."""

    turn_seq: int
    world: WorldDelta
    souls: list[CharacterDelta] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION


# --------------------------------------------------------------------------
# Commit parents.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitParents:
    """Parent commit ids for this turn's commit chains.

    ``world`` is the prior world_commit_id (or None at turn 0).
    ``souls`` maps a soul's ``(sid, instance_id)`` fork identity to its
    prior soul_commit_id. A passthrough soul's prior id is read straight
    out of this map (no new id is derived for it).
    """

    world: str | None = None
    souls: dict[tuple[str, str], str | None] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Commit objects (M17 §2.1 / §2.2) — independent schemas.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SoulCommit:
    """Soul-instance commit (M17 §2.2). Fully independent.

    INVARIANT: carries NO world hashes / wid / world_commit field — the
    soul never knows which world it is in (M17 §1.2, §2.2). ``turn_seq``
    is a loose ordering breadcrumb only, never a world pointer.
    """

    soul_commit_id: str
    parent: str | None
    sid: str
    instance_id: str
    version_hash: str
    folder_hash: str
    turn_seq: int
    branch: str = "main"
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class SoulSceneEntry:
    """Read-only observation pointer in the world commit (M17 §1.5, §2.3).

    Points AT a soul-instance commit so a restore can reassemble the
    scene. NOT identity written into the soul; one direction only.
    """

    sid: str
    instance_id: str
    soul_commit: str
    role: str = "npc"


@dataclass(frozen=True)
class WorldCommit:
    """World-instance commit (M17 §2.1).

    ``soul_scene_index`` is the read-only pointer set (M17 §2.3); for a
    passthrough soul it points at that soul's *prior* commit id.
    """

    world_commit_id: str
    parent: str | None
    turn_seq: int
    wid: str
    instance_id: str
    version_hash: str
    game_folder_hash: str
    session_log_hash: str
    soul_scene_index: list[SoulSceneEntry]
    branch: str = "main"
    schema_version: int = SCHEMA_VERSION


# --------------------------------------------------------------------------
# compose_commit — the pure composition step (M18 §3.4 step 5).
# --------------------------------------------------------------------------


def _soul_scene_index_payload(
    entries: list[SoulSceneEntry],
) -> list[dict[str, str]]:
    """Stable payload form of the scene index for the world id formula.

    Sorted by the soul fork identity so the world_commit_id is invariant
    to the order souls happened to be collected in.
    """
    rows = [
        {
            "sid": e.sid,
            "instance_id": e.instance_id,
            "soul_commit": e.soul_commit,
            "role": e.role,
        }
        for e in entries
    ]
    rows.sort(key=lambda r: (r["sid"], r["instance_id"]))
    return rows


def compose_commit(
    collection: TurnCollection,
    parents: CommitParents,
) -> tuple[WorldCommit, list[SoulCommit]]:
    """Compose one WorldCommit + N SoulCommits from a TurnCollection.

    Pure: no disk IO, no ref writes (that is ``land_commit``, out of
    scope). Deterministic: identical inputs -> byte-identical ids.

    Per M18 §3.4 / M17 open-q #3: one SoulCommit per *mutated* soul. A
    soul whose ``state`` is interrupted/degraded is a **passthrough** —
    it reuses its prior soul_commit_id, no new SoulCommit is allocated,
    and the world commit's ``soul_scene_index`` simply points at that
    prior commit.
    """
    soul_commits: list[SoulCommit] = []
    scene_entries: list[SoulSceneEntry] = []

    for delta in collection.souls:
        fork = (delta.sid, delta.instance_id)
        prior = parents.souls.get(fork)

        if delta.state in _PASSTHROUGH_STATES:
            # Passthrough: no fresh state -> reuse the prior commit id.
            # A passthrough with no prior commit (soul never committed and
            # was interrupted on its first turn) has nothing to point at.
            if prior is None:
                continue
            scene_entries.append(
                SoulSceneEntry(
                    sid=delta.sid,
                    instance_id=delta.instance_id,
                    soul_commit=prior,
                )
            )
            continue

        # Mutated soul -> derive a fresh, independent soul_commit_id.
        # M17 §2 soul formula: parent + sid + instance_id + version_hash
        # + soul_folder_hash + turn_seq. NO world fields.
        soul_id = _commit_id(
            {
                "parent_soul_commit_id": prior,
                "sid": delta.sid,
                "instance_id": delta.instance_id,
                "version_hash": delta.version_hash,
                "soul_folder_hash": delta.soul_folder_hash,
                "turn_seq": collection.turn_seq,
            }
        )
        soul_commits.append(
            SoulCommit(
                soul_commit_id=soul_id,
                parent=prior,
                sid=delta.sid,
                instance_id=delta.instance_id,
                version_hash=delta.version_hash,
                folder_hash=delta.soul_folder_hash,
                turn_seq=collection.turn_seq,
            )
        )
        scene_entries.append(
            SoulSceneEntry(
                sid=delta.sid,
                instance_id=delta.instance_id,
                soul_commit=soul_id,
            )
        )

    scene_payload = _soul_scene_index_payload(scene_entries)

    # M17 §2 world formula: parent + wid + instance_id + version_hash +
    # game_folder_hash + session_log_hash + turn_seq + soul_scene_index.
    world = collection.world
    world_id = _commit_id(
        {
            "parent_world_commit_id": parents.world,
            "wid": world.wid,
            "instance_id": world.instance_id,
            "version_hash": world.version_hash,
            "game_folder_hash": world.game_folder_hash,
            "session_log_hash": world.session_log_hash,
            "turn_seq": collection.turn_seq,
            "soul_scene_index": scene_payload,
        }
    )

    world_commit = WorldCommit(
        world_commit_id=world_id,
        parent=parents.world,
        turn_seq=collection.turn_seq,
        wid=world.wid,
        instance_id=world.instance_id,
        version_hash=world.version_hash,
        game_folder_hash=world.game_folder_hash,
        session_log_hash=world.session_log_hash,
        # Keep the same stable ordering used for the id.
        soul_scene_index=sorted(
            scene_entries, key=lambda e: (e.sid, e.instance_id)
        ),
    )

    return world_commit, soul_commits
