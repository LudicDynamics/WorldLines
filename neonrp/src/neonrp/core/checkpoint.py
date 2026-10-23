"""Checkpoint subsystem for NeonRP.

This module provides checkpoint management for undo/redo functionality.
Checkpoints are full snapshots of the game/ directory at specific event IDs.

Checkpoint storage: .neonrp/checkpoints/<branch>/<event_id>/
"""

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from neonrp.core.paths import get_neonrp_dir, get_game_dir
from neonrp.core.storage import atomic_write_dir

# Maximum number of checkpoints to retain per branch
MAX_CHECKPOINTS_PER_BRANCH = 50


@dataclass
class Checkpoint:
    """Represents a checkpoint snapshot."""

    branch: str
    event_id: int
    path: Path
    created: datetime


def get_checkpoints_dir(root: Path, branch: str) -> Path:
    """Get the checkpoints directory for a branch."""
    return get_neonrp_dir(root) / "checkpoints" / branch


def get_checkpoint_path(root: Path, branch: str, event_id: int) -> Path:
    """Get the path for a specific checkpoint."""
    return get_checkpoints_dir(root, branch) / str(event_id)


def list_checkpoints(root: Path, branch: str) -> list[Checkpoint]:
    """List all checkpoints for a branch, sorted by event_id ascending.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        List of Checkpoint objects sorted by event_id
    """
    checkpoints_dir = get_checkpoints_dir(root, branch)
    if not checkpoints_dir.exists():
        return []

    checkpoints = []
    for entry in checkpoints_dir.iterdir():
        if entry.is_dir():
            try:
                event_id = int(entry.name)
                # Get creation time from directory mtime
                created = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
                checkpoints.append(
                    Checkpoint(
                        branch=branch,
                        event_id=event_id,
                        path=entry,
                        created=created,
                    )
                )
            except ValueError:
                # Skip non-numeric directory names
                continue

    # Sort by event_id ascending
    return sorted(checkpoints, key=lambda c: c.event_id)


def create_checkpoint(root: Path, branch: str, event_id: int) -> Optional[Checkpoint]:
    """Create a checkpoint of the current game state.

    Args:
        root: Project root directory
        branch: Branch name
        event_id: Event ID to associate with this checkpoint

    Returns:
        Checkpoint object if created successfully, None if world doesn't exist
    """
    game_dir = get_game_dir(root)
    if not game_dir.exists():
        return None

    checkpoint_path = get_checkpoint_path(root, branch, event_id)

    # Create checkpoint directory
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomically copy world to checkpoint
    atomic_write_dir(checkpoint_path, game_dir)

    # Rotate old checkpoints
    rotate_checkpoints(root, branch)

    return Checkpoint(
        branch=branch,
        event_id=event_id,
        path=checkpoint_path,
        created=datetime.now(timezone.utc),
    )


def restore_checkpoint(root: Path, branch: str, event_id: int) -> bool:
    """Restore the game state from a checkpoint.

    Args:
        root: Project root directory
        branch: Branch name
        event_id: Event ID of the checkpoint to restore

    Returns:
        True if restored successfully, False if checkpoint doesn't exist
    """
    checkpoint_path = get_checkpoint_path(root, branch, event_id)
    if not checkpoint_path.exists():
        return False

    game_dir = get_game_dir(root)

    # Use atomic_write_dir for crash-safe restore
    # This performs: copy checkpoint -> .new, rename current -> .old, rename .new -> current, remove .old
    atomic_write_dir(game_dir, checkpoint_path)

    return True


def find_checkpoint_for_undo(root: Path, branch: str, current_event: int) -> Optional[int]:
    """Find the event ID to restore for an undo operation.

    For undo, we want to restore the state BEFORE the current event.
    This means finding the checkpoint with event_id < current_event.

    Args:
        root: Project root directory
        branch: Branch name
        current_event: Current head event ID

    Returns:
        Event ID to restore to, or None if no suitable checkpoint exists
    """
    checkpoints = list_checkpoints(root, branch)
    if not checkpoints:
        return None

    # Find the highest checkpoint with event_id < current_event
    for checkpoint in reversed(checkpoints):
        if checkpoint.event_id < current_event:
            return checkpoint.event_id

    return None


def find_checkpoint_for_redo(root: Path, branch: str, current_event: int, max_event: int) -> Optional[int]:
    """Find the event ID to restore for a redo operation.

    For redo, we want to restore the state AFTER the current event,
    but not beyond max_event (the furthest we've been).

    Args:
        root: Project root directory
        branch: Branch name
        current_event: Current head event ID
        max_event: Maximum event ID we've reached (stored in branch metadata)

    Returns:
        Event ID to restore to, or None if no suitable checkpoint exists
    """
    if current_event >= max_event:
        return None

    checkpoints = list_checkpoints(root, branch)
    if not checkpoints:
        return None

    # Find the lowest checkpoint with event_id > current_event and <= max_event
    for checkpoint in checkpoints:
        if current_event < checkpoint.event_id <= max_event:
            return checkpoint.event_id

    return None


def rotate_checkpoints(root: Path, branch: str, max_count: int = MAX_CHECKPOINTS_PER_BRANCH) -> int:
    """Remove old checkpoints to stay within the limit.

    Keeps the most recent checkpoints based on event_id.

    Args:
        root: Project root directory
        branch: Branch name
        max_count: Maximum number of checkpoints to keep

    Returns:
        Number of checkpoints removed
    """
    checkpoints = list_checkpoints(root, branch)
    if len(checkpoints) <= max_count:
        return 0

    # Remove oldest checkpoints (lowest event_ids)
    to_remove = checkpoints[:-max_count]
    removed = 0

    for checkpoint in to_remove:
        try:
            shutil.rmtree(checkpoint.path)
            removed += 1
        except Exception:
            # Log but don't fail
            pass

    return removed


def delete_checkpoint(root: Path, branch: str, event_id: int) -> bool:
    """Delete a specific checkpoint.

    Args:
        root: Project root directory
        branch: Branch name
        event_id: Event ID of the checkpoint to delete

    Returns:
        True if deleted, False if didn't exist
    """
    checkpoint_path = get_checkpoint_path(root, branch, event_id)
    if not checkpoint_path.exists():
        return False

    shutil.rmtree(checkpoint_path)
    return True


def delete_branch_checkpoints(root: Path, branch: str) -> int:
    """Delete all checkpoints for a branch.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        Number of checkpoints deleted
    """
    checkpoints_dir = get_checkpoints_dir(root, branch)
    if not checkpoints_dir.exists():
        return 0

    count = len(list(checkpoints_dir.iterdir()))
    shutil.rmtree(checkpoints_dir)
    return count


