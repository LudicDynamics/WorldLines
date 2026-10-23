"""Thin integration glue for the M17 `neonrp commit` subsystem.

The three committed M17 leaves are intentionally narrow:

* ``core/turn_commit.py``  — *pure* commit composition (no IO, no
  ``land_commit``: it explicitly defers the disk-landing step).
* ``core/commit_store.py`` — blob/ref/commit-object STORAGE IO only
  (it does not decide *what* to pack or *which* refs to bump).
* ``core/playthrough.py``  — manifest schema read/write only.

Nothing wires them into a working commit graph. That seam is this
module. It is deliberately the *only* new core code: every hash, every
byte of compression, every ref mutation is delegated to a leaf. The
functions here are orchestration — they do not reimplement leaf logic.

Scope (M17 §3, §5, §7, local-only v1):

* :func:`land_commit`     — the missing Phase-D step: pack the game
  folder + session log into content-hashed blobs, compose the commit
  via the pure layer (honouring the locked hash 口径 — the blob storage
  key IS the folder tree-hash from ``turn_commit``/``hashing.py``, never
  ``commit_store``'s tar-bytes sha256 which is integrity-only), persist
  the commit object, advance the ref, update ``playthrough.json`` HEAD.
* :func:`walk_log`        — walk the commit DAG by ``parent``.
* :func:`checkout_commit` — rehydrate a working tree (game + soul
  instances) from a commit's blobs.
* :func:`branch_from_head`— fork HEAD onto a new branch (M17 §3.2):
  copy the manifest, mint fresh ``instance_id``s, reset HEAD.
* :func:`verify_commit`   — rehydrate + recompute the tree-hash and
  report match/mismatch (M17 §5 replay-verify, single-machine).
* :func:`backfill_game`   — synthesise one commit for a legacy game dir
  that has no commit graph (M17 §7).

LEAF-API GAP (flagged, not worked around): ``turn_commit`` documents a
``land_commit`` Phase-D step but does not ship it, and no leaf collects
*which files* form the game-folder / session-log / soul blobs. This
module supplies that collection + landing using only documented leaf
APIs; it invents no leaf internals.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from neonrp.core import commit_store
from neonrp.core.hashing import compute_file_hash, compute_game_hash
from neonrp.core.playthrough import (
    Playthrough,
    SoulRef,
    WorldRef,
    read_playthrough,
    write_playthrough,
)
from neonrp.core.turn_commit import (
    CharacterDelta,
    CommitParents,
    TurnCollection,
    WorldDelta,
    compose_commit,
)

# A game working tree's runtime bookkeeping dir (docs/WORLD_SOUL_FOLDERS §4).
_NEONRP_DIR = ".neonrp"
# Player-visible world state lives under game/ (M17 open-q #1 leans toward
# hashing only game/, so the blob + tree-hash cover exactly that subtree —
# engine internals under .neonrp/ can evolve without invalidating commits).
_GAME_SUBDIR = "game"
_SOULS_SUBDIR = "souls"
_HEAD_FILE = "HEAD"
_SESSIONS_DIR = "sessions"


class CommitSubsystemError(Exception):
    """Raised on a structural problem the CLI should report cleanly
    (missing game dir, no commit graph, unknown commit, hash mismatch
    surfaced as an explicit verify result rather than an exception)."""


# --------------------------------------------------------------------------- #
# Small disk helpers (no hashing/compression here — that is leaf territory)
# --------------------------------------------------------------------------- #

def _game_dir(game_root: Path) -> Path:
    return game_root / _GAME_SUBDIR


def _souls_dir(game_root: Path) -> Path:
    return game_root / _SOULS_SUBDIR


def _neonrp_dir(game_root: Path) -> Path:
    return game_root / _NEONRP_DIR


def _head_path(game_root: Path) -> Path:
    return _neonrp_dir(game_root) / _HEAD_FILE


def _session_log_path(game_root: Path, branch: str) -> Path:
    return _neonrp_dir(game_root) / _SESSIONS_DIR / f"{branch}.jsonl"


def _read_head(game_root: Path) -> str | None:
    p = _head_path(game_root)
    if not p.exists():
        return None
    v = p.read_text(encoding="utf-8").strip()
    return v or None


def _write_head(game_root: Path, commit_id: str) -> None:
    p = _head_path(game_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{commit_id}\n", encoding="utf-8")


def _read_run_state_turn(game_root: Path) -> int:
    """Best-effort ``run_state.json.turn_count`` (M17 §7 backfill input).

    Missing/garbled run_state is the M17 §7 "skip with a warning" path; the
    caller decides — here we just signal absence with -1 so callers don't
    have to import json themselves.
    """
    import json

    rs = _game_dir(game_root) / "meta" / "run_state.json"
    if not rs.exists():
        return -1
    try:
        data = json.loads(rs.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return -1
    tc = data.get("turn_count")
    return tc if isinstance(tc, int) else -1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Blob landing — the documented-but-unshipped Phase-D step
# --------------------------------------------------------------------------- #

def _land_blob(commits_root: Path, src_dir: Path, tree_hash: str) -> None:
    """Pack ``src_dir`` and store it under the LOCKED key: the folder
    tree-hash (``hashing.compute_game_hash``), NOT ``pack_dir``'s tar
    sha256. ``commit_store.write_blob`` takes the key as a param exactly
    so this caller can pass the tree-hash (M17 §4.1 reconciled note).
    ``pack_dir``'s own returned hash is the integrity checksum and is
    intentionally discarded as a storage key here.
    """
    if commit_store.has_blob(commits_root, tree_hash):
        return  # unchanged folder (same tree-hash): the blob is already there, don't pack again
    _integrity_hash, blob_bytes = commit_store.pack_dir(src_dir)
    commit_store.write_blob(commits_root, tree_hash, blob_bytes)


def _land_file_blob(commits_root: Path, src_file: Path, key: str) -> None:
    """Store a single file (the session log) as a blob under ``key``.

    Reuses ``pack_dir`` over the file's parent restricted to that one
    file would change the tree-hash semantics, so instead we wrap the
    lone file in a one-entry directory pack via a tmp staging dir is
    avoided: the session log's content key is its own tree-hash slot.
    We pack the file's bytes through the same deterministic store by
    treating the session log as a degenerate single-file blob.
    """
    # The session log hash口径 is the same compute_game_hash family applied
    # to a one-file tree; we stage nothing — pack the parent filtered to
    # the single file via a throwaway dir is overkill. Store raw bytes
    # under the key; read side mirrors this (see _restore_session_log).
    commit_store.write_blob(commits_root, key, src_file.read_bytes())


@dataclass(frozen=True)
class LandedCommit:
    """Result of :func:`land_commit` — what the CLI echoes back."""

    world_commit_id: str
    branch: str
    turn_seq: int
    parent: str | None


def land_commit(
    game_root: Path,
    commits_root: Path,
    *,
    turn_seq: int,
    branch: str = "main",
    parent: str | None = None,
) -> LandedCommit:
    """Pack → compose → persist → advance refs for one turn.

    This is the Phase-D step ``turn_commit`` documents but defers. It
    only orchestrates leaf APIs:

    1. tree-hash the ``game/`` subtree (``hashing.compute_game_hash`` —
       the one shared hash, reused verbatim per M17 §5.2);
    2. pack it into a blob keyed by that tree-hash (locked 口径);
    3. tree-hash + blob each participating soul instance the same way;
    4. ``compose_commit`` (pure) to derive the world/soul commit ids;
    5. ``commit_store.write_world_commit`` / ``write_soul_commit``;
    6. advance the branch ref + the working tree HEAD + manifest
       ``head_commit``s.

    The session log is stored under its own content hash when present.
    """
    game_dir = _game_dir(game_root)
    if not game_dir.exists():
        raise CommitSubsystemError(f"no game/ subtree at {game_root}")

    pt = read_playthrough(game_root)

    # World-instance identity: prefer the authoritative manifest; fall back
    # to dir-name parsing only for legacy/backfill (handled by backfill_game,
    # which always writes a manifest first).
    if pt is not None:
        wid = pt.world.wid
        world_instance = pt.world.instance_id
        world_version = pt.world.version_hash
    else:
        wid, world_instance, world_version = _infer_world_identity(game_root)

    game_tree_hash = compute_game_hash(game_dir)
    _land_blob(commits_root, game_dir, game_tree_hash)

    # Session log: a content-hashed blob keyed by the shared file-hash helper.
    session_hash = "sha256:empty"
    sess = _session_log_path(game_root, branch)
    if sess.exists():
        # A session log is a single file, not a folder tree; keep it on
        # ``core.hashing`` by using the canonical file hash helper.
        session_hash = "sha256:" + compute_file_hash(sess)
        _land_file_blob(commits_root, sess, session_hash)

    # Soul instances: one CharacterDelta per soul working tree present.
    souls_root = _souls_dir(game_root)
    char_deltas: list[CharacterDelta] = []
    soul_parents: dict[tuple[str, str], str | None] = {}
    soul_dirs: dict[tuple[str, str], Path] = {}
    if pt is not None:
        for sref in pt.souls:
            sdir = souls_root / f"{sref.sid}-{sref.instance_id}"
            sfolder_hash = compute_game_hash(sdir)
            char_deltas.append(
                CharacterDelta(
                    sid=sref.sid,
                    instance_id=sref.instance_id,
                    version_hash=sref.version_hash,
                    state="completed",
                    soul_folder_hash=sfolder_hash,
                )
            )
            soul_parents[(sref.sid, sref.instance_id)] = sref.head_commit or None
            soul_dirs[(sref.sid, sref.instance_id)] = sdir

    collection = TurnCollection(
        turn_seq=turn_seq,
        world=WorldDelta(
            wid=wid,
            instance_id=world_instance,
            version_hash=world_version,
            game_folder_hash=game_tree_hash,
            session_log_hash=session_hash,
        ),
        souls=char_deltas,
    )
    world_commit, soul_commits = compose_commit(
        collection, CommitParents(world=parent, souls=soul_parents)
    )

    # Persist soul commits + their folder blobs (independent chains, M17 §2.2).
    soul_head_by_fork: dict[tuple[str, str], str] = {}
    for sc in soul_commits:
        fork = (sc.sid, sc.instance_id)
        sdir = soul_dirs[fork]
        _land_blob(commits_root, sdir, sc.folder_hash)
        commit_store.write_soul_commit(sdir, _soul_commit_obj(sc, branch))
        soul_head_by_fork[fork] = sc.soul_commit_id

    # Persist the world commit object, advance the ref + HEAD.
    commit_store.write_world_commit(
        commits_root,
        _world_commit_obj(
            world_commit,
            branch,
            determinism=_determinism_payload(
                session_log_hash=session_hash,
                session_log_path=sess,
            ),
        ),
    )
    commit_store.write_ref(
        commits_root, wid, world_commit.world_commit_id, name=branch
    )
    _write_head(game_root, world_commit.world_commit_id)

    # Advance manifest head_commits (per-chain, independently).
    if pt is not None:
        _advance_manifest_heads(
            game_root, pt, world_commit.world_commit_id, soul_head_by_fork
        )

    return LandedCommit(
        world_commit_id=world_commit.world_commit_id,
        branch=branch,
        turn_seq=turn_seq,
        parent=parent,
    )


def _world_commit_obj(wc, branch: str, *, determinism: dict | None = None) -> dict:
    """Serialise a pure ``WorldCommit`` to the M17 §2.1 on-disk shape.

    ``determinism`` is optional metadata and is intentionally NOT part of the
    current commit-id formula. It records what replay evidence exists without
    pretending deterministic replay is already implemented.
    """
    payload = {
        "schema_version": wc.schema_version,
        "world_commit_id": wc.world_commit_id,
        "parent": wc.parent,
        "branch": branch,
        "turn_seq": wc.turn_seq,
        "world": {
            "wid": wc.wid,
            "instance_id": wc.instance_id,
            "version_hash": wc.version_hash,
        },
        "game_folder": {"hash": wc.game_folder_hash},
        "session_log": {"hash": wc.session_log_hash},
        "soul_scene_index": [
            {
                "sid": e.sid,
                "instance_id": e.instance_id,
                "soul_commit": e.soul_commit,
                "role": e.role,
            }
            for e in wc.soul_scene_index
        ],
        "labels": [],
        "archived_at": None,
    }
    if determinism is not None:
        payload["determinism"] = determinism
    return payload


def _determinism_payload(
    *,
    session_log_hash: str,
    session_log_path: Path,
) -> dict:
    """Best-effort M17-E determinism metadata.

    This is deliberately conservative: it records the session transcript hash
    that is actually available today and states that exact LLM request/response
    capture plus replay are not implemented yet.
    """
    exists = session_log_path.exists()
    session_relpath = Path(_NEONRP_DIR) / _SESSIONS_DIR / session_log_path.name
    return {
        "schema_version": 1,
        "status": "partial",
        "replay_status": "not_implemented",
        "llm_calls_status": "not_recorded",
        "sources": {
            "session_log": {
                "path": session_relpath.as_posix(),
                "hash": session_log_hash,
                "present": exists,
            }
        },
    }


def _soul_commit_obj(sc, branch: str) -> dict:
    """Serialise a pure ``SoulCommit`` to the M17 §2.2 on-disk shape.

    INVARIANT preserved: no world hashes / wid (M17 §1.2, §2.2).
    """
    return {
        "schema_version": sc.schema_version,
        "soul_commit_id": sc.soul_commit_id,
        "parent": sc.parent,
        "branch": branch,
        "soul": {
            "sid": sc.sid,
            "instance_id": sc.instance_id,
            "version_hash": sc.version_hash,
        },
        "folder_hash": sc.folder_hash,
        "turn_seq": sc.turn_seq,
        "archived_at": None,
    }


def _advance_manifest_heads(
    game_root: Path,
    pt: Playthrough,
    world_head: str,
    soul_heads: dict[tuple[str, str], str],
) -> None:
    new_souls = [
        SoulRef(
            sid=s.sid,
            instance_id=s.instance_id,
            version_hash=s.version_hash,
            head_commit=soul_heads.get((s.sid, s.instance_id), s.head_commit),
            role=s.role,
        )
        for s in pt.souls
    ]
    write_playthrough(
        game_root,
        Playthrough(
            schema_version=pt.schema_version,
            playthrough_id=pt.playthrough_id,
            world=WorldRef(
                wid=pt.world.wid,
                instance_id=pt.world.instance_id,
                version_hash=pt.world.version_hash,
                head_commit=world_head,
            ),
            world_agent_team=pt.world_agent_team,
            souls=new_souls,
            created_at=pt.created_at,
            # Preserve the live active set across the per-turn head bump —
            # otherwise every committed turn would silently reset it to
            # empty and the next turn would run with zero characters.
            active_souls=pt.active_souls,
            # …and the M22 integration routing, for the same reason.
            integrations=pt.integrations,
        ),
    )


def _infer_world_identity(game_root: Path) -> tuple[str, str, str]:
    """Derive ``(wid, instance_id, version_hash)`` from the dir name when
    no manifest exists (legacy/backfill only). Dir form is
    ``<wid>-<world_instance_id>`` per docs/WORLD_SOUL_FOLDERS §4; legacy
    timestamped dirs (``<wid>-<YYYYMMDD-HHMMSS>``) treat the trailing
    token as the instance id. version_hash is unknown for legacy state →
    a stable sentinel so the commit still hashes deterministically.
    """
    name = game_root.name
    if "-" in name:
        wid, _, instance = name.rpartition("-")
    else:
        wid, instance = name, "legacy"
    return wid or name, instance or "legacy", "legacy-unknown"


# --------------------------------------------------------------------------- #
# log — walk the commit DAG
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LogEntry:
    commit_id: str
    parent: str | None
    branch: str
    turn_seq: int
    labels: list[str]


def walk_log(commits_root: Path, head: str) -> list[LogEntry]:
    """Walk ``parent`` from ``head`` (newest → oldest), M17 §3 DAG.

    A dangling parent (already GC'd) stops the walk — same convention as
    ``commit_store``'s internal GC walk.
    """
    out: list[LogEntry] = []
    cursor: str | None = head
    seen: set[str] = set()
    while cursor and cursor not in seen:
        seen.add(cursor)
        try:
            obj = commit_store.read_world_commit(commits_root, cursor)
        except FileNotFoundError:
            break
        out.append(
            LogEntry(
                commit_id=cursor,
                parent=obj.get("parent"),
                branch=obj.get("branch", "main"),
                turn_seq=obj.get("turn_seq", -1),
                labels=list(obj.get("labels") or []),
            )
        )
        cursor = obj.get("parent")
    return out


# --------------------------------------------------------------------------- #
# checkout — rehydrate a working tree
# --------------------------------------------------------------------------- #

def _restore_blob_dir(commits_root: Path, tree_hash: str, dest: Path) -> None:
    if tree_hash in ("sha256:empty", "", None):
        return
    blob = commit_store.read_blob(commits_root, tree_hash)
    commit_store.unpack_dir(blob, dest)


def checkout_commit(
    commits_root: Path, commit_id: str, dest_root: Path
) -> dict:
    """Restore ``game/`` + every soul instance from ``commit_id`` into
    ``dest_root`` (M17 §3 / acceptance: checkout restores soul folders
    too via the read-only ``soul_scene_index``).

    Returns the commit object for the CLI to summarise.
    """
    try:
        obj = commit_store.read_world_commit(commits_root, commit_id)
    except FileNotFoundError as e:
        raise CommitSubsystemError(f"unknown commit {commit_id!r}") from e

    gf = (obj.get("game_folder") or {}).get("hash")
    if gf:
        _restore_blob_dir(commits_root, gf, dest_root / _GAME_SUBDIR)

    # Session log → restore under the branch the commit was on.
    sl = (obj.get("session_log") or {}).get("hash")
    if sl and sl != "sha256:empty":
        branch = obj.get("branch", "main")
        sess = _session_log_path(dest_root, branch)
        sess.parent.mkdir(parents=True, exist_ok=True)
        sess.write_bytes(commit_store.read_blob(commits_root, sl))

    # Soul instances via the read-only scene index (M17 §2.3, one-way).
    for entry in obj.get("soul_scene_index") or []:
        if not isinstance(entry, dict):
            continue  # 防御:老档/手改档的畸形条目(list/str)不炸回滚
        sid = entry.get("sid")
        iid = entry.get("instance_id")
        soul_commit_id = entry.get("soul_commit")
        if not (sid and iid and soul_commit_id):
            continue
        sdir = _souls_dir(dest_root) / f"{sid}-{iid}"
        try:
            sc = commit_store.read_soul_commit(sdir, soul_commit_id)
        except FileNotFoundError:
            # Soul commit object lives in the soul instance's own .commits/;
            # absent on a fresh dest is expected — fall back to no restore
            # for that soul rather than aborting the whole checkout.
            continue
        fh = sc.get("folder_hash")
        if fh:
            _restore_blob_dir(commits_root, fh, sdir)

    _write_head(dest_root, commit_id)
    return obj


# --------------------------------------------------------------------------- #
# branch — fork HEAD onto a new branch (M17 §3.2)
# --------------------------------------------------------------------------- #

def branch_from_head(
    game_root: Path, commits_root: Path, branch_name: str
) -> str:
    """Fork the current HEAD onto a new branch (M17 §3.2).

    Per §3.2 / §2.4: create a new branch ref at HEAD, copy
    ``playthrough.json`` verbatim, mint fresh ``instance_id``s for
    participants that should diverge, reset HEAD to the fork point. No
    merge (M17 §3.3).
    """
    head = _read_head(game_root)
    if head is None:
        raise CommitSubsystemError("no HEAD — nothing to branch from")

    pt = read_playthrough(game_root)
    if pt is not None:
        wid = pt.world.wid
    else:
        wid, _, _ = _infer_world_identity(game_root)

    # commit_store.create_branch is non-idempotent by design (it raises
    # FileExistsError) so a fork never clobbers a divergent line.
    try:
        commit_store.create_branch(commits_root, wid, branch_name, head)
    except FileExistsError as e:
        raise CommitSubsystemError(str(e)) from e

    if pt is not None:
        # Mint a fresh world instance_id so the new branch's chain diverges
        # without entangling the parent's instance (M17 §1.2, §3.2). Souls
        # likewise fork: new instance_id, head reset to the fork commit's
        # corresponding soul commit (read from the fork commit's scene index).
        fork_obj = commit_store.read_world_commit(commits_root, head)
        scene = {
            (e["sid"]): e for e in (fork_obj.get("soul_scene_index") or []) if isinstance(e, dict)
        }
        new_souls = []
        for s in pt.souls:
            new_iid = f"si-{uuid.uuid4().hex[:12]}"
            head_commit = s.head_commit
            ent = scene.get(s.sid)
            if ent and ent.get("soul_commit"):
                head_commit = ent["soul_commit"]
            new_souls.append(
                SoulRef(
                    sid=s.sid,
                    instance_id=new_iid,
                    version_hash=s.version_hash,
                    head_commit=head_commit,
                    role=s.role,
                )
            )
        forked = Playthrough(
            schema_version=pt.schema_version,
            playthrough_id=f"pt-{uuid.uuid4().hex[:12]}",
            world=WorldRef(
                wid=pt.world.wid,
                instance_id=f"wi-{uuid.uuid4().hex[:12]}",
                version_hash=pt.world.version_hash,
                head_commit=head,
            ),
            world_agent_team=pt.world_agent_team,
            souls=new_souls,
            created_at=_now_iso(),
            # A fork inherits the source scene's active cast + routing.
            active_souls=pt.active_souls,
            integrations=pt.integrations,
        )
        write_playthrough(game_root, forked)

    _write_head(game_root, head)
    return head


# --------------------------------------------------------------------------- #
# rollback — fork a PAST commit onto a new branch (M17 §3.2, applied)
# --------------------------------------------------------------------------- #


def rollback_to_commit(
    game_root: Path,
    commits_root: Path,
    commit_id: str,
    new_branch: str,
) -> dict:
    """Roll the working tree back to a past turn's ``commit_id`` as a NEW
    divergent branch, leaving the source line completely untouched.

    Unlike ``checkout_commit`` (which rewrites the *source* branch's session
    log and moves nobody's ref) followed by ``branch_from_head`` (which mints
    fresh soul ``instance_id``s but does NOT materialise their folders), this
    is the one-shot, playable rollback:

      1. create the branch ref at ``commit_id`` (raises if it already exists);
      2. restore ``game/`` into the working tree from the commit's blob;
      3. for each soul in the commit's ``soul_scene_index``: mint a fresh
         ``instance_id`` AND materialise its folder from the soul commit's
         blob (+ carry its ``.commits`` history so ``head_commit`` resolves);
      4. write a forked ``playthrough.json`` pointing at the new instances;
      5. seed the NEW branch's session log from the commit's session blob —
         the source branch's ``<branch>.jsonl`` is never written (no clobber);
      6. move the working-tree HEAD to ``commit_id``.

    Manifest coordination (``current_branch`` + ``branches`` entry) and the
    events/orchestration journals are the caller's job — this touches only
    the commit DAG, the working tree, and ``playthrough.json``. Returns a
    summary dict (branch, commit_id, turn_seq, wid, souls[old→new]).
    """
    try:
        obj = commit_store.read_world_commit(commits_root, commit_id)
    except FileNotFoundError as e:
        raise CommitSubsystemError(f"unknown commit {commit_id!r}") from e

    pt = read_playthrough(game_root)
    if pt is not None:
        wid = pt.world.wid
        world_version = pt.world.version_hash
    else:
        wid, _, world_version = _infer_world_identity(game_root)

    # 1. Branch ref at the target commit (non-idempotent — never clobbers a
    #    divergent line; a repeated rollback picks a fresh branch name).
    try:
        commit_store.create_branch(commits_root, wid, new_branch, commit_id)
    except FileExistsError as e:
        raise CommitSubsystemError(str(e)) from e

    # 2. Restore game/ working tree from the target commit's blob.
    gf = (obj.get("game_folder") or {}).get("hash")
    if gf:
        _restore_blob_dir(commits_root, gf, _game_dir(game_root))

    # 3 + 4. Fork each soul at the target commit: fresh instance_id + a
    #        MATERIALISED folder (the piece branch_from_head omits).
    old_by_sid = {s.sid: s for s in (pt.souls if pt is not None else [])}
    souls_root = _souls_dir(game_root)
    new_souls: list[SoulRef] = []
    materialised: list[dict] = []
    for entry in obj.get("soul_scene_index") or []:
        if not isinstance(entry, dict):
            continue  # 防御:老档/手改档的畸形条目(list/str)不炸回滚
        sid = entry.get("sid")
        old_iid = entry.get("instance_id")
        soul_commit = entry.get("soul_commit")
        if not (sid and old_iid and soul_commit):
            continue
        old_sdir = souls_root / f"{sid}-{old_iid}"
        new_iid = f"si-{uuid.uuid4().hex[:12]}"
        new_sdir = souls_root / f"{sid}-{new_iid}"
        try:
            sc = commit_store.read_soul_commit(old_sdir, soul_commit)
            fh = sc.get("folder_hash")
            if fh:
                _restore_blob_dir(commits_root, fh, new_sdir)
        except FileNotFoundError:
            # Soul commit object missing (legacy/partial) — skip its folder
            # restore rather than aborting the whole rollback.
            pass
        # Carry the soul's own commit history so head_commit resolves and a
        # future turn on the new branch can land against it.
        old_commits = old_sdir / ".commits"
        if old_commits.is_dir():
            shutil.copytree(old_commits, new_sdir / ".commits", dirs_exist_ok=True)
        base = old_by_sid.get(sid)
        new_souls.append(
            SoulRef(
                sid=sid,
                instance_id=new_iid,
                version_hash=base.version_hash if base is not None else "",
                head_commit=soul_commit,
                role=base.role if base is not None else "npc",
            )
        )
        materialised.append({"sid": sid, "from": old_iid, "to": new_iid})

    forked = Playthrough(
        schema_version=pt.schema_version if pt is not None else 1,
        playthrough_id=f"pt-{uuid.uuid4().hex[:12]}",
        world=WorldRef(
            wid=wid,
            instance_id=f"wi-{uuid.uuid4().hex[:12]}",
            version_hash=world_version,
            head_commit=commit_id,
        ),
        world_agent_team=pt.world_agent_team if pt is not None else [],
        souls=new_souls,
        created_at=_now_iso(),
        active_souls=pt.active_souls if pt is not None else [],
        integrations=pt.integrations if pt is not None else {},
    )
    write_playthrough(game_root, forked)

    # 5. Seed the NEW branch's session log from the commit — source untouched.
    sl = (obj.get("session_log") or {}).get("hash")
    new_sess = _session_log_path(game_root, new_branch)
    new_sess.parent.mkdir(parents=True, exist_ok=True)
    if sl and sl != "sha256:empty":
        new_sess.write_bytes(commit_store.read_blob(commits_root, sl))
    else:
        new_sess.write_bytes(b"")

    # 6. Working-tree HEAD → the target commit.
    _write_head(game_root, commit_id)

    return {
        "branch": new_branch,
        "commit_id": commit_id,
        "turn_seq": obj.get("turn_seq"),
        "wid": wid,
        "souls": materialised,
    }


# --------------------------------------------------------------------------- #
# verify — rehydrate + recompute hash (M17 §5, single-machine)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VerifyResult:
    commit_id: str
    recorded_hash: str
    recomputed_hash: str
    match: bool
    determinism_status: str
    determinism_message: str


def verify_commit(
    commits_root: Path, commit_id: str, scratch_root: Path
) -> VerifyResult:
    """Rehydrate ``commit_id`` into ``scratch_root`` and recompute the
    game-folder tree-hash; compare against the recorded hash (M17 §5
    replay-verify, single-machine first).

    Deterministic next-turn replay is a separate M17-E payload. Until the
    commit object contains real determinism data, verification must say
    "unverifiable" instead of silently implying replay completeness.
    """
    try:
        obj = commit_store.read_world_commit(commits_root, commit_id)
    except FileNotFoundError as e:
        raise CommitSubsystemError(f"unknown commit {commit_id!r}") from e

    recorded = (obj.get("game_folder") or {}).get("hash", "")
    determinism_status, determinism_message = _determinism_verify_status(obj)
    checkout_commit(commits_root, commit_id, scratch_root)
    recomputed = compute_game_hash(scratch_root / _GAME_SUBDIR)
    return VerifyResult(
        commit_id=commit_id,
        recorded_hash=recorded,
        recomputed_hash=recomputed,
        match=(recorded == recomputed),
        determinism_status=determinism_status,
        determinism_message=determinism_message,
    )


def _determinism_verify_status(obj: dict) -> tuple[str, str]:
    determinism = obj.get("determinism")
    if determinism is None:
        return (
            "unverifiable",
            "missing determinism payload; verified snapshot hash only",
        )
    if not isinstance(determinism, dict):
        return (
            "invalid",
            "determinism payload is not an object",
        )
    replay_status = str(determinism.get("replay_status") or "").strip()
    llm_calls_status = str(determinism.get("llm_calls_status") or "").strip()
    if replay_status == "not_implemented":
        detail = "determinism metadata recorded; replay check is not implemented yet"
        if llm_calls_status:
            detail += f"; llm_calls={llm_calls_status}"
        return ("recorded_unverified", detail)
    return (
        "recorded_unverified",
        "determinism payload present; deterministic replay check is not implemented yet",
    )


# --------------------------------------------------------------------------- #
# backfill — synthesise a single commit for a legacy game dir (M17 §7)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class BackfillResult:
    game_root: Path
    world_commit_id: str
    turn_seq: int


def backfill_game(
    game_root: Path, commits_root: Path
) -> BackfillResult:
    """M17 §7: a legacy ``games/<dir>`` with no commit graph → ONE commit
    at ``run_state.json.turn_count``, ``parent=null``, ``branch="main"``.
    No intermediate commits are synthesised (they'd be fake — §7 step 1).

    Games without ``run_state.json`` are skipped with an error the CLI
    surfaces as a warning (§7 step 3).
    """
    if not _game_dir(game_root).exists():
        raise CommitSubsystemError(f"no game/ subtree at {game_root}")

    existing_head = _read_head(game_root)
    if existing_head is not None:
        raise CommitSubsystemError(
            f"{game_root.name} already has a commit graph (HEAD={existing_head})"
        )

    turn = _read_run_state_turn(game_root)
    if turn < 0:
        raise CommitSubsystemError(
            f"{game_root.name}: no usable run_state.json.turn_count — "
            "skipping (manual cleanup, M17 §7 step 3)"
        )

    # Ensure a manifest exists so the synthetic commit has authoritative
    # world identity; legacy dirs predate playthrough.json, so synthesise a
    # minimal one from the dir name (the §7 backfill is the one place a
    # manifest may be freshly minted).
    if read_playthrough(game_root) is None:
        wid, world_instance, world_version = _infer_world_identity(game_root)
        write_playthrough(
            game_root,
            Playthrough(
                schema_version=2,
                playthrough_id=f"pt-{uuid.uuid4().hex[:12]}",
                world=WorldRef(
                    wid=wid,
                    instance_id=world_instance,
                    version_hash=world_version,
                    head_commit="",
                ),
                world_agent_team=_empty_team(),
                souls=[],
                created_at=_now_iso(),
            ),
        )

    landed = land_commit(
        game_root,
        commits_root,
        turn_seq=turn,
        branch="main",
        parent=None,
    )
    return BackfillResult(
        game_root=game_root,
        world_commit_id=landed.world_commit_id,
        turn_seq=turn,
    )


def _empty_team():
    from neonrp.core.playthrough import WorldAgentTeam

    # Legacy backfill has no seeded roster on disk; the manifest schema
    # requires the block, so seed an explicit empty team labelled as
    # backfilled rather than guessing an agent list.
    return WorldAgentTeam(seeded_from="backfill@legacy", agents=[])
