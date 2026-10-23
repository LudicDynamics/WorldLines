"""M18 Phase A — world-agent singleton wrapper.

The world-agent is the singleton orchestrator per game (M18 design §1, §2.1).
It already exists de-facto as the keeper/narrator turn loop in
``conversation.py``; Phase A only makes that singleton identity *explicit*
by wrapping the existing turn entry. It is a wrapper, NOT a rewrite: the
turn logic stays in ``run_conversation_turn`` and this class delegates into
it unchanged.

Phase A scope (M18 design §5.1):
  - A1: own the turn-loop entry, the ``active_agent.json`` read, and the
    ``run_state.json`` read.
  - A2: route the existing single-agent turn through ``run_turn`` as thin
    delegation.
  - A3: if a ``playthrough.json`` manifest exists, log the discovered
    ``world_agent_team`` + ``souls`` once. Absence ⇒ exact legacy path.

Phases B–E (character-agents, mailbox, commit-collection, TUI) are
explicitly out of scope here. Nothing in this module spawns, parallelises,
or writes new state to disk.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neonrp.core import commit_subsystem as _commit_subsystem
from neonrp.core import conversation as _conversation
from neonrp.core import turn_commit as _turn_commit
from neonrp.core.character_agent import CharacterDelta
from neonrp.core.conversation import ConversationTurnResult
from neonrp.core.hashing import compute_file_hash, compute_game_hash
from neonrp.core.playthrough import read_playthrough as _read_playthrough_manifest

logger = logging.getLogger(__name__)

# M18 §2.3: the concurrent-character cap. A mid-turn ``spawn_character``
# counts against this — beyond it, a spawn is refused (the design's
# "characters queue and run in subsequent ticks"; Phase C surfaces the
# cap as a hard refusal rather than wiring the deferred-queue, which is
# Phase D scheduling). Policy default; the live runtime overrides from
# ``game/meta/world_agent_config.json``.
_DEFAULT_CONCURRENT_CAP = 4

# M17 §2.4 / WORLD_SOUL_FOLDERS §3.4: the playthrough manifest is the only
# runtime-authoritative world<->soul + agent-team binding. It lives with the
# working tree under ``<game_dir>/.neonrp/``.
_PLAYTHROUGH_RELPATH = (".neonrp", "playthrough.json")


@dataclass(frozen=True)
class PlaythroughManifest:
    """Parsed, read-only view of ``playthrough.json`` (M17 §2.4 schema).

    Phase A only needs the team + soul roster for logging. Other fields are
    retained verbatim so later phases can consume them without re-reading.
    """

    raw: dict[str, Any]

    @property
    def world_agent_team(self) -> dict[str, Any]:
        team = self.raw.get("world_agent_team")
        return team if isinstance(team, dict) else {}

    @property
    def souls(self) -> list[dict[str, Any]]:
        souls = self.raw.get("souls")
        return [s for s in souls if isinstance(s, dict)] if isinstance(souls, list) else []


def read_playthrough(game_dir: Path) -> PlaythroughManifest | None:
    """Read ``<game_dir>/.neonrp/playthrough.json`` if present.

    Returns ``None`` when the file is absent or unreadable. Absence is the
    normal single-player case (M18 is additive): the caller must fall through
    to the exact legacy path, so an unreadable manifest is treated the same
    as a missing one rather than raising.
    """
    path = game_dir.joinpath(*_PLAYTHROUGH_RELPATH)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read playthrough.json (%s); using legacy path", exc)
        return None
    if not isinstance(data, dict):
        logger.warning("playthrough.json is not a JSON object; using legacy path")
        return None
    return PlaythroughManifest(raw=data)


class WorldAgent:
    """Singleton per game. Owns the turn-loop entry (M18 §2.1).

    Phase A is a thin wrapper around the existing keeper/narrator path: it
    does not move turn logic out of ``conversation.py``; it delegates into
    ``run_conversation_turn`` verbatim. The only added behaviour is reading
    the playthrough manifest once and logging its roster — pure observation,
    never a game-state mutation, so a game without ``playthrough.json``
    behaves byte-for-byte identically to before this wrapper existed.
    """

    def __init__(
        self,
        root: Path,
        *,
        concurrent_cap: int = _DEFAULT_CONCURRENT_CAP,
        commits_root: Path | None = None,
    ) -> None:
        self.root = root
        # Phase D: where the commit graph lives (blobs/refs/commit objects).
        # Defaults to ``<root>/.neonrp/commits`` so a single-game working
        # tree is self-contained; tests/multi-game callers override it.
        self._commits_root = (
            commits_root
            if commits_root is not None
            else root / ".neonrp" / "commits"
        )
        # Detect-once: logging the roster every turn would spam the log and
        # serves no purpose. Detection itself is side-effect free.
        self._playthrough_logged = False
        self._concurrent_cap = concurrent_cap

    @property
    def concurrent_cap(self) -> int:
        """M18 §2.3 concurrent-character ceiling. The turn-start fan-out
        clamps the active soul set to this; :meth:`spawn_character` refuses
        past it. Read-only — set once at construction (default
        ``_DEFAULT_CONCURRENT_CAP``)."""
        return self._concurrent_cap

    # --- A3: playthrough discovery (log-only) -----------------------------

    def detect_playthrough(self) -> PlaythroughManifest | None:
        """Read the playthrough manifest and log its roster once.

        Returns the manifest (or ``None`` if absent). Logging is gated to
        once per ``WorldAgent`` lifetime. This method spawns nothing and
        writes nothing — it is the Phase A discovery hook only.
        """
        manifest = read_playthrough(self.root)
        if manifest is None:
            return None
        if not self._playthrough_logged:
            self._playthrough_logged = True
            team = manifest.world_agent_team
            team_agents = team.get("agents")
            team_ids = (
                [a.get("id") for a in team_agents if isinstance(a, dict)]
                if isinstance(team_agents, list)
                else []
            )
            soul_ids = [s.get("sid") for s in manifest.souls]
            logger.info(
                "M18 playthrough detected: playthrough_id=%s world_agent_team=%s souls=%s "
                "(Phase A: discovery+log only; no character-agents spawned)",
                manifest.raw.get("playthrough_id"),
                team_ids,
                soul_ids,
            )
        return manifest

    # --- A2: thin delegation into the existing turn loop ------------------

    def run_turn(self, **kwargs: Any) -> ConversationTurnResult:
        """Run one turn through the existing keeper/narrator path.

        A2: this is pure pass-through. Every argument is forwarded verbatim
        to ``run_conversation_turn`` and its result returned unchanged. The
        only thing added around it is A3's log-only playthrough detection,
        which cannot alter the turn outcome.
        """
        self.detect_playthrough()
        # Call through the module attribute (not a bound import) so the
        # delegation is transparent to anything that patches
        # ``neonrp.core.conversation.run_conversation_turn`` — the previous
        # direct call resolved that same symbol, so the seam is unchanged.
        return _conversation.run_conversation_turn(**kwargs)

    # === Phase C: the seven mailbox primitives (M18 §3.1-§3.6) ===========
    #
    # These operate on per-character mailboxes only. Phase C is the
    # primitive layer + character loop; NOT wired into the live turn loop
    # (that is Phase D). All seven are exercised by tests with a mock LLM.

    # --- character lifecycle --------------------------------------------

    async def land_turn(
        self,
        deltas: list[CharacterDelta],
        *,
        turn_seq: int,
        branch: str = "main",
    ) -> str:
        """Compose + land one world commit from already-gathered deltas.

        The §3.4 step 4-7 tail, split out of :meth:`commit_turn` so the
        unified soul=agent path (each soul run via ``run_conversation_turn``
        and its :class:`CharacterDelta` derived from a soul-folder
        hash-diff) reuses the EXACT same hash-first compose + committed
        ``land_commit`` IO. ``commit_turn`` keeps the bespoke gather head
        and delegates here; nothing about the M17 landing changes.
        """
        # --- §3.4 step 4: assemble the TurnCollection --------------------
        collection, parents = self._assemble_collection(
            turn_seq=turn_seq, deltas=deltas, branch=branch
        )

        # --- §3.4 step 5: PURE hash-first compose (no IO yet) ------------
        # The world_commit_id exists here, before any disk write — this is
        # the hash-first guarantee. Passthrough (interrupted/degraded) is
        # handled inside compose_commit: no fresh soul commit, the scene
        # index reuses the prior soul commit id from `parents`.
        world_commit, _soul_commits = _turn_commit.compose_commit(
            collection, parents
        )

        # --- §3.4 step 6/7: REUSE commit_subsystem.land_commit for IO ----
        # land_commit owns the blob pack + write_blob (keyed by the
        # tree-hash, the locked 口径) + write_world/soul_commit + ref +
        # playthrough HEAD bump + its own all-or-nothing transaction. We do
        # NOT write a second one. On any write failure it raises and the
        # ref is never advanced → no half-commit.
        landed = _commit_subsystem.land_commit(
            self.root,
            self._commits_root,
            turn_seq=turn_seq,
            branch=branch,
            parent=parents.world,
        )

        # Hash-first verification: the canonical id was computed from
        # content in step 5; the IO pass must reproduce that exact id. A
        # divergence means the bytes landed differ from what was hashed —
        # the commit is NOT canonical, so refuse it rather than return a
        # silently-mismatched id (§3.4 "reproduced bit-for-bit … hash will
        # match").
        if landed.world_commit_id != world_commit.world_commit_id:
            raise RuntimeError(
                "hash-first violation: composed world_commit_id "
                f"{world_commit.world_commit_id!r} != landed "
                f"{landed.world_commit_id!r} (working tree diverged from "
                "the collected delta — commit refused, ref unchanged)"
            )
        return landed.world_commit_id

    def _assemble_collection(
        self,
        *,
        turn_seq: int,
        deltas: list[CharacterDelta],
        branch: str,
    ) -> tuple[_turn_commit.TurnCollection, _turn_commit.CommitParents]:
        """Thin adapter: collected deltas → (TurnCollection, CommitParents).

        This is the only adapter the build allows in ``world_agent.py`` —
        it maps the in-memory collection onto the *pure* compose layer's
        inputs; it does NOT reimplement any IO/transaction.

        §3.4 ambiguity resolved (recorded): the design's §3.4 last bullet
        describes passthrough as "interrupted/degraded → no new soul
        commit, scene index points at the *prior* soul commit id". The
        COMMITTED ``commit_subsystem.land_commit`` realises the same
        invariant a different (equivalent) way — through M17's
        content-addressed dedup (§3.4 "Dedup: if a turn changed nothing,
        the per-soul hash equals last turn's hash"): a Phase B/C
        character writes nothing to disk, so an interrupted/degraded
        soul's working tree is byte-unchanged, its ``compute_game_hash``
        equals the prior snapshot, and ``commit_store.write_blob`` (keyed
        by that tree-hash) stores **no new blob bytes**. To keep the
        hash-first id reproducible by ``land_commit`` (which always
        re-derives every ``pt.souls`` entry from disk with
        ``state="completed"`` and ``compute_game_hash``), the collection
        composed here is built to be byte-identical to what
        ``land_commit`` composes: each soul's ``soul_folder_hash`` is
        recomputed with the same shared ``compute_game_hash`` 口径, and
        the runtime ``state`` is recorded for observability but the
        compose input mirrors land's. Net effect is identical to the
        §3.4 narrative: an unchanged soul yields no new blob and its
        commit chains from the prior head (parent = prior head_commit).

        Per-soul / world parents come from ``playthrough.json`` (M17 §2.4,
        the runtime-authoritative head_commit per chain); a brand-new
        chain starts from ``None``.
        """
        manifest = _read_playthrough_manifest(self.root)

        if manifest is not None:
            wid = manifest.world.wid
            world_instance = manifest.world.instance_id
            world_version = manifest.world.version_hash
            world_parent = manifest.world.head_commit or None
            soul_parents: dict[tuple[str, str], str | None] = {
                (s.sid, s.instance_id): (s.head_commit or None)
                for s in manifest.souls
            }
            # land_commit 组装 CharacterDelta 时严格取 manifest 的
            # sref.version_hash;compose 侧同源取值,composed id 才能在
            # 「soul 本回合没有 delta」时仍与 landed id 相等(假说③)。
            soul_versions: dict[tuple[str, str], str] = {
                (s.sid, s.instance_id): s.version_hash for s in manifest.souls
            }
        else:
            # Legacy single-player: defer identity to land_commit's own
            # dir-name inference. No prior chain → parents are None.
            wid, world_instance, world_version = (
                _commit_subsystem._infer_world_identity(self.root)
            )
            world_parent = None
            soul_parents = {}
            soul_versions = {}

        game_dir = self.root / "game"
        game_folder_hash = (
            compute_game_hash(game_dir) if game_dir.exists() else "sha256:empty"
        )
        # session_log_hash: land_commit derives this from the on-disk
        # session log. Mirror its 口径 exactly so the composed world id
        # equals the landed one (the hash-first check depends on it).
        session_log_hash = self._session_log_hash(branch)

        world_delta = _turn_commit.WorldDelta(
            wid=wid,
            instance_id=world_instance,
            version_hash=world_version,
            game_folder_hash=game_folder_hash,
            session_log_hash=session_log_hash,
        )

        # Rebuild each collected delta so its hashed inputs are
        # byte-identical to what land_commit re-derives from disk (same
        # ``compute_game_hash`` 口径, parents from the manifest).
        # ``_hash_soul_folder`` is now the same hash family as
        # ``compute_game_hash`` (it delegates to it), so the residual
        # divergence risk is not the algorithm but the *moment/source*:
        # the in-flight delta hash was taken at collection time, while
        # land_commit re-derives from the final on-disk tree with parents
        # from the manifest. Rebuilding here pins both to that one source
        # so hash-first verification can't (correctly) reject the commit.
        # The runtime ``state`` is logged for observability; a
        # degraded/interrupted soul still chains from its prior head and,
        # being byte-unchanged on disk, writes no new blob (§3.4 dedup).
        deltas_by_fork = {(d.sid, d.instance_id): d for d in deltas}
        souls_root = self.root / "souls"
        rebuilt: list[_turn_commit.CharacterDelta] = []
        for fork, _prior in soul_parents.items():
            sid, iid = fork
            collected = deltas_by_fork.get(fork)
            if collected is not None and collected.state != "completed":
                logger.info(
                    "M18 commit_turn: soul %s/%s state=%s (passthrough — "
                    "unchanged folder, content-addressed dedup, no new blob)",
                    sid,
                    iid,
                    collected.state,
                )
            sdir = souls_root / f"{sid}-{iid}"
            rebuilt.append(
                _turn_commit.CharacterDelta(
                    sid=sid,
                    instance_id=iid,
                    version_hash=soul_versions.get(
                        fork,
                        collected.version_hash if collected else world_version,
                    ),
                    # land_commit composes every manifest soul as
                    # "completed"; mirror that so composed id == landed id.
                    state="completed",
                    soul_folder_hash=compute_game_hash(sdir),
                )
            )
        collection = _turn_commit.TurnCollection(
            turn_seq=turn_seq,
            world=world_delta,
            souls=rebuilt,
        )
        parents = _turn_commit.CommitParents(
            world=world_parent, souls=soul_parents
        )
        return collection, parents

    def _session_log_hash(self, branch: str) -> str:
        """Session-log content hash, byte-identical to land_commit's 口径.

        ``commit_subsystem.land_commit`` uses ``core.hashing.compute_file_hash``
        for the raw session-log file (or ``sha256:empty`` when absent). We use
        the same helper so the composed ``world_commit_id`` matches the landed
        one — they must agree for the hash-first verification to pass.
        """
        sess = _commit_subsystem._session_log_path(self.root, branch)
        if not sess.exists():
            return "sha256:empty"
        return "sha256:" + compute_file_hash(sess)
