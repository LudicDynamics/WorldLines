"""Soul turn result + soul-folder hashing — the live M18 contract.

Historically this module also held a bespoke ``CharacterAgent`` class
that ran a soul via its own tool-less LLM loop + mailbox primitives
(M18 Phase B/C scaffold). That scaffold was retired: a soul is now a
regular agent run through ``run_conversation_turn`` (see
``soul_agent.resolve_soul_agent_data`` + ``conversation``'s multi-agent
turn). All that remains here is the data the M17 landing actually
consumes: :class:`CharacterDelta` and :func:`_hash_soul_folder`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from neonrp.core.hashing import compute_game_hash

CharacterState = Literal["completed", "interrupted", "degraded"]


@dataclass
class CharacterDelta:
    """One soul's per-turn result, in the M18 §3.4 shape the M17 landing
    consumes.

    ``soul_folder_hash`` is the post-turn content hash of the soul folder
    (or, for an ``interrupted``/``degraded`` soul, the prior hash —
    passthrough §3.4, so the world commit's soul scene index points at
    the unchanged prior soul commit). ``files_modified`` is informational;
    M17's content-addressed dedup keys off ``soul_folder_hash``.
    """

    sid: str
    instance_id: str
    version_hash: str
    state: CharacterState
    soul_folder_hash: str
    files_modified: list[dict[str, str]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "instance_id": self.instance_id,
            "version_hash": self.version_hash,
            "state": self.state,
            "soul_folder_hash": self.soul_folder_hash,
            "files_modified": self.files_modified,
            "tool_calls": self.tool_calls,
            "outbox": self.outbox,
        }


def _hash_soul_folder(soul_dir: Path) -> str:
    """Stable content hash of the soul folder snapshot (read-only).

    Compatibility wrapper around the one canonical tree-hash implementation.
    WORLD_SOUL_FOLDERS §5 requires ``*_folder_hash`` values to reuse
    ``core.hashing.compute_game_hash`` verbatim; this wrapper exists only
    because the live M18 spine already imports the historical name.
    """
    return compute_game_hash(soul_dir)
