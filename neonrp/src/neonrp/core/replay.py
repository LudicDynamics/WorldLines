"""Replay engine for determinism verification.

Replays events from a save baseline to verify game-state consistency.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from neonrp.core.hashing import compute_game_hash
from neonrp.core.paths import (
    GAME_DIR_NAME,
    get_neonrp_dir,
    get_game_dir,
    validate_branch_name,
)
from neonrp.core.proposal import Proposal, UpsertTextOp, DeleteOp, parse_ops
from neonrp.core.storage import atomic_write_dir, atomic_write_text


@dataclass
class ReplayEvent:
    """Result of replaying a single event."""

    event_id: int
    event_type: str
    actor: str
    success: bool
    error: Optional[str] = None
    game_hash: Optional[str] = None


@dataclass
class ReplayResult:
    """Result of a replay verification."""

    success: bool
    from_save: str
    branch: str
    target_event: int
    events_total: int
    events_replayed: int
    events_skipped: int = 0
    replayed_events: list[ReplayEvent] = field(default_factory=list)
    divergent_event: Optional[dict] = None
    error: Optional[str] = None

def load_proposal_from_logs(root: Path, run_id: str) -> Optional[Proposal]:
    """Load a proposal from the agent logs by run_id.

    Args:
        root: Project root directory.
        run_id: The run ID to look up.

    Returns:
        Proposal if found and valid, None otherwise.
    """
    logs_dir = get_neonrp_dir(root) / "logs" / "agents" / run_id
    proposal_path = logs_dir / "proposal.json"

    if not proposal_path.exists():
        return None

    try:
        with open(proposal_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Parse ops
        ops = parse_ops(data.get("ops", []))
        return Proposal(
            agent_id=data["agent_id"],
            branch=data["branch"],
            base_head_event=data["base_head_event"],
            rationale=data.get("rationale", ""),
            ops=ops,
            run_id=data.get("run_id", run_id),
            query=data.get("query", ""),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def apply_ops_to_staging(staging_game: Path, proposal: Proposal) -> list[str]:
    """Apply proposal ops to staging game directory.

    Args:
        staging_game: Path to the staging game directory.
        proposal: The proposal containing ops to apply.

    Returns:
        List of paths that were modified.
    """
    applied_paths = []
    for op in proposal.ops:
        target_path = (staging_game / op.path).resolve()
        try:
            target_path.relative_to(staging_game.resolve())
        except ValueError:
            raise ValueError(f"Path traversal detected: '{op.path}' resolves outside staging game")

        if isinstance(op, UpsertTextOp):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target_path, op.content)
            applied_paths.append(op.path)
        elif isinstance(op, DeleteOp):
            if target_path.exists():
                target_path.unlink()
            applied_paths.append(op.path)

    return applied_paths


def replay_verify(
    root: Path,
    save_id: str,
    branch: Optional[str] = None,
    to_event: Optional[int] = None,
) -> ReplayResult:
    """Replay events from a save to verify determinism.

    Args:
        root: Project root directory.
        save_id: The save ID to replay from.
        branch: Branch to replay on (defaults to save's branch).
        to_event: Target event ID (defaults to current head).

    Returns:
        ReplayResult with verification status and details.
    """
    from neonrp.commands.save import get_saves_dir
    from neonrp.core.event_log import read_events

    saves_dir = get_saves_dir(root)
    save_dir = saves_dir / save_id

    # Validate save exists
    if not save_dir.exists():
        return ReplayResult(
            success=False,
            from_save=save_id,
            branch=branch or "unknown",
            target_event=to_event or -1,
            events_total=0,
            events_replayed=0,
            error=f"Save '{save_id}' not found",
        )

    # Load save meta
    meta_path = save_dir / "meta.json"
    if not meta_path.exists():
        return ReplayResult(
            success=False,
            from_save=save_id,
            branch=branch or "unknown",
            target_event=to_event or -1,
            events_total=0,
            events_replayed=0,
            error=f"Save '{save_id}' is missing meta.json (old format)",
        )

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    save_branch = meta["branch"]
    save_head_event = meta["head_event"]

    # Use save's branch if not specified
    if branch is None:
        branch = save_branch

    # Read current events for the branch
    events = read_events(root, branch)

    # Determine target event
    if to_event is None:
        to_event = events[-1].id if events else save_head_event

    # Filter events: only those after save_head_event and up to to_event
    # and only replayable types (agent, system)
    replayable_types = {"agent", "system"}
    events_to_replay = [e for e in events if e.id > save_head_event and e.id <= to_event and e.type in replayable_types]

    # Count skipped events (non-replayable types in range)
    all_in_range = [e for e in events if e.id > save_head_event and e.id <= to_event]
    events_skipped = len(all_in_range) - len(events_to_replay)

    # Create staging directory
    staging_dir = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="neonrp_replay_"))
        staging_game = staging_dir / GAME_DIR_NAME

        # Copy save game data to staging
        save_game = save_dir / GAME_DIR_NAME
        shutil.copytree(save_game, staging_game)

        replayed_events = []

        # Replay each event
        for event in events_to_replay:
            run_id = event.payload.get("run_id")
            if not run_id:
                replayed_events.append(
                    ReplayEvent(
                        event_id=event.id,
                        event_type=event.type,
                        actor=event.actor or "unknown",
                        success=False,
                        error="Event has no run_id in payload",
                    )
                )
                continue

            # Load proposal
            proposal = load_proposal_from_logs(root, run_id)
            if proposal is None:
                replayed_events.append(
                    ReplayEvent(
                        event_id=event.id,
                        event_type=event.type,
                        actor=event.actor or "unknown",
                        success=False,
                        error=f"Proposal not found for run_id '{run_id}'",
                    )
                )
                continue

            # Apply ops to staging
            try:
                apply_ops_to_staging(staging_game, proposal)
            except Exception as e:
                replayed_events.append(
                    ReplayEvent(
                        event_id=event.id,
                        event_type=event.type,
                        actor=event.actor or "unknown",
                        success=False,
                        error=f"Failed to apply ops: {e}",
                    )
                )
                continue

            # Compute hash after applying
            current_hash = compute_game_hash(staging_game)

            replayed_events.append(
                ReplayEvent(
                    event_id=event.id,
                    event_type=event.type,
                    actor=event.actor or "unknown",
                    success=True,
                    game_hash=current_hash,
                )
            )

        # Check final game hash against current game state
        final_staging_hash = compute_game_hash(staging_game)
        current_game = get_game_dir(root)
        current_game_hash = compute_game_hash(current_game)

        # If hashes don't match after all replays, find divergence
        # Also check when events_to_replay is empty (save state vs current game)
        divergent = None
        if final_staging_hash != current_game_hash:
            # Find first file that differs
            divergent_file = _find_first_divergent_file(staging_game, current_game)
            if events_to_replay:
                last_event = events_to_replay[-1]
                divergent = {
                    "event_id": last_event.id,
                    "type": last_event.type,
                    "actor": last_event.actor or "unknown",
                    "first_divergent_file": divergent_file,
                    "expected_hash": current_game_hash,
                    "actual_hash": final_staging_hash,
                }
            else:
                divergent = {
                    "event_id": -1,
                    "type": "none",
                    "actor": "none",
                    "first_divergent_file": divergent_file,
                    "expected_hash": current_game_hash,
                    "actual_hash": final_staging_hash,
                    "note": "Game state diverges from save baseline with no replayable events in range",
                }

        # Replay fails if any event failed OR if game hashes diverge
        any_failed = any(not e.success for e in replayed_events)
        overall_success = divergent is None and not any_failed

        return ReplayResult(
            success=overall_success,
            from_save=save_id,
            branch=branch,
            target_event=to_event,
            events_total=len(all_in_range),
            events_replayed=len([e for e in replayed_events if e.success]),
            events_skipped=events_skipped,
            replayed_events=replayed_events,
            divergent_event=divergent,
        )

    finally:
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def _find_first_divergent_file(staging_game: Path, actual_game: Path) -> Optional[str]:
    """Find the first file that differs between staging and actual game data."""
    from neonrp.core.hashing import compute_file_hash

    staging_files = {f.relative_to(staging_game).as_posix(): f for f in staging_game.rglob("*") if f.is_file()}
    actual_files = {f.relative_to(actual_game).as_posix(): f for f in actual_game.rglob("*") if f.is_file()}

    all_paths = sorted(set(staging_files.keys()) | set(actual_files.keys()))

    for path in all_paths:
        staging_file = staging_files.get(path)
        actual_file = actual_files.get(path)

        if staging_file is None:
            return f"{path} (missing in replay)"
        if actual_file is None:
            return f"{path} (extra in replay)"

        if compute_file_hash(staging_file) != compute_file_hash(actual_file):
            return path

    return None


def replay_to_sandbox(
    root: Path,
    save_id: str,
    to_event: int,
    branch_name: str,
) -> dict:
    """Replay events to target point and create a sandbox branch.

    Args:
        root: Project root directory.
        save_id: The save ID to replay from.
        to_event: Target event ID to replay to.
        branch_name: Name for the new sandbox branch.

    Returns:
        dict with success status and details.
    """
    from neonrp.commands.save import get_saves_dir
    from neonrp.core.event_log import read_events
    from neonrp.core.manifest import BranchMetadata, Manifest
    from neonrp.core.paths import get_manifest_path, get_neonrp_dir
    from neonrp.core.storage import atomic_write_json

    saves_dir = get_saves_dir(root)
    save_dir = saves_dir / save_id

    # Validate save exists
    if not save_dir.exists():
        return {"success": False, "error": f"Save '{save_id}' not found"}

    meta_path = save_dir / "meta.json"
    if not meta_path.exists():
        return {"success": False, "error": f"Save '{save_id}' is missing meta.json (old format)"}

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    save_branch = meta["branch"]
    save_head_event = meta["head_event"]

    # Validate branch name
    name_error = validate_branch_name(branch_name)
    if name_error:
        return {"success": False, "error": name_error}

    if branch_name == "main":
        return {"success": False, "error": "Cannot create sandbox with name 'main'"}

    # Load manifest
    manifest_path = get_manifest_path(root)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    if branch_name in manifest.branches:
        return {"success": False, "error": f"Branch '{branch_name}' already exists"}

    # Read events for the branch
    events = read_events(root, save_branch)

    # Filter events to replay
    replayable_types = {"agent", "system"}
    events_to_replay = [e for e in events if e.id > save_head_event and e.id <= to_event and e.type in replayable_types]

    # Create staging directory
    staging_dir = None
    try:
        staging_dir = Path(tempfile.mkdtemp(prefix="neonrp_checkout_"))
        staging_game = staging_dir / GAME_DIR_NAME

        # Copy save game data to staging
        save_game = save_dir / GAME_DIR_NAME
        shutil.copytree(save_game, staging_game)

        # Replay each event
        for event in events_to_replay:
            run_id = event.payload.get("run_id")
            if not run_id:
                continue  # Skip events without run_id

            proposal = load_proposal_from_logs(root, run_id)
            if proposal is None:
                continue  # Skip events without proposal

            apply_ops_to_staging(staging_game, proposal)

        # Compute final hash
        game_hash = compute_game_hash(staging_game)

        # Create sandbox branch
        branches_dir = get_neonrp_dir(root) / "branches"
        branches_dir.mkdir(exist_ok=True)
        sandbox_game_dir = branches_dir / branch_name / GAME_DIR_NAME

        # Copy staging to sandbox branch atomically
        atomic_write_dir(sandbox_game_dir, staging_game)

        # Create sandbox branch metadata
        sandbox_meta = BranchMetadata(
            head_event=to_event,
            kind="sandbox",
            parent=save_branch,
            fork_event=to_event,
            base_save=save_id,
        )
        manifest.branches[branch_name] = sandbox_meta

        # Build sandbox event log from the branch event log (not the save's snapshot)
        # This ensures the sandbox has all events up to to_event, including
        # those that were replayed beyond the save's head.
        from neonrp.core.event_log import get_event_log_path

        events_dir = get_neonrp_dir(root) / "events"
        sandbox_events = events_dir / f"{branch_name}.jsonl"

        branch_events_path = get_event_log_path(root, save_branch)
        if branch_events_path.exists():
            with open(branch_events_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Keep only events up to to_event
            filtered_lines = []
            for line in lines:
                if line.strip():
                    try:
                        evt = json.loads(line)
                        if evt.get("id", 0) <= to_event:
                            filtered_lines.append(line)
                    except json.JSONDecodeError:
                        continue
            atomic_write_text(sandbox_events, "".join(filtered_lines))
        else:
            atomic_write_text(sandbox_events, "")

        # Save manifest
        atomic_write_json(manifest_path, manifest.model_dump())

        return {
            "success": True,
            "branch": branch_name,
            "from_save": save_id,
            "head_event": to_event,
            "game_hash": game_hash,
            "events_replayed": len(events_to_replay),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        if staging_dir and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


