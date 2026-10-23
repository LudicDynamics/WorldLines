import click
import json
from copy import deepcopy
from datetime import datetime, timezone

from neonrp.core.paths import (
    GAME_DIR_NAME,
    get_manifest_path,
    get_neonrp_dir,
    get_project_root,
    get_game_dir,
)
from neonrp.core.manifest import Manifest
from neonrp.core.storage import atomic_write_json, atomic_write_dir
from neonrp.core.checkpoint import (
    restore_checkpoint,
    find_checkpoint_for_undo,
    find_checkpoint_for_redo,
)


def get_branch_storage_path(root, branch_name):
    branch_root = get_neonrp_dir(root) / "branches" / branch_name
    game_path = branch_root / GAME_DIR_NAME
    return game_path


def sync_game_to_storage(root, branch_name):
    """Backup current game directory to branch storage."""
    game_dir = get_game_dir(root)
    storage_dir = get_branch_storage_path(root, branch_name)
    if game_dir.exists():
        atomic_write_dir(storage_dir, game_dir)


def restore_game_from_storage(root, branch_name):
    """Restore game directory from branch storage.
    """
    game_dir = get_game_dir(root)
    storage_dir = get_branch_storage_path(root, branch_name)

    if storage_dir.exists():
        atomic_write_dir(game_dir, storage_dir)
    else:
        # Storage missing - create empty game directory (for new branches)
        if not game_dir.exists():
            game_dir.mkdir(exist_ok=True)


@click.command()
@click.argument("name")
def branch(name):
    """Create a new branch from current state."""
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        click.echo("Error: Not initialized.")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
        manifest = Manifest(**manifest_data)

    old_branch_name = manifest.current_branch

    if name in manifest.branches:
        # M0 requirement implies CREATE. But if we want to allow switching...
        # Let's support switching if it exists, for verification.
        click.echo(f"Switching to existing branch '{name}'...")

        # 1. Save current state
        sync_game_to_storage(root, old_branch_name)

        # 2. Update manifest
        manifest.current_branch = name
        atomic_write_json(manifest_path, manifest.model_dump())

        # 3. Restore new state
        restore_game_from_storage(root, name)
        click.echo(f"Switched to branch: {name}")
        return

    # Creating new branch
    current = manifest.branches[old_branch_name]

    # 1. Save current state (so old branch is safe)
    sync_game_to_storage(root, old_branch_name)

    # 2. Fork: Copy metadata
    new_branch = deepcopy(current)
    new_branch.created = datetime.now(timezone.utc)

    # 3. Fork data: Copy storage from old to new
    old_storage = get_branch_storage_path(root, old_branch_name)
    new_storage = get_branch_storage_path(root, name)

    if old_storage.exists():
        atomic_write_dir(new_storage, old_storage)
    else:
        # If old storage didn't exist (fresh init), ensure target dir created
        new_storage.mkdir(parents=True, exist_ok=True)

    manifest.branches[name] = new_branch
    manifest.current_branch = name

    atomic_write_json(manifest_path, manifest.model_dump())
    click.echo(f"Created and switched to new branch: {name}")


def perform_undo(root) -> dict:
    """Undo the last change (restore checkpoint + move head_event back).

    Plain-callable core shared by the CLI command and the web facade
    (POST /api/v1/play/session/<sid>/undo). Returns
    ``{"ok": bool, "message": str, "head_event": int | None}``.
    """
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        return {"ok": False, "message": "Not initialized.", "head_event": None}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    current_branch_name = manifest.current_branch
    current_branch = manifest.branches[current_branch_name]

    if current_branch.head_event < 0:
        return {
            "ok": False,
            "message": "Nothing to undo (at start of branch).",
            "head_event": current_branch.head_event,
        }

    target_event = find_checkpoint_for_undo(root, current_branch_name, current_branch.head_event)

    if target_event is None:
        # No checkpoint available, just decrement pointer (fallback behavior)
        old_head = current_branch.head_event
        new_head = max(-1, old_head - 1)
        current_branch.head_event = new_head
        if not hasattr(current_branch, "max_event") or current_branch.max_event is None:
            current_branch.max_event = old_head
        atomic_write_json(manifest_path, manifest.model_dump())
        return {
            "ok": True,
            "message": f"Undid event. Head moved from {old_head} to {new_head}. (No checkpoint available)",
            "head_event": new_head,
        }

    if not restore_checkpoint(root, current_branch_name, target_event):
        return {
            "ok": False,
            "message": f"Failed to restore checkpoint for event {target_event}",
            "head_event": current_branch.head_event,
        }

    old_head = current_branch.head_event
    if not hasattr(current_branch, "max_event") or current_branch.max_event is None:
        current_branch.max_event = old_head
    current_branch.head_event = target_event
    atomic_write_json(manifest_path, manifest.model_dump())
    return {
        "ok": True,
        "message": f"Undid change. Game state restored to event {target_event} (was {old_head}).",
        "head_event": target_event,
    }


def perform_redo(root) -> dict:
    """Redo a previously undone change. Same contract as :func:`perform_undo`."""
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        return {"ok": False, "message": "Not initialized.", "head_event": None}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    current_branch_name = manifest.current_branch
    current_branch = manifest.branches[current_branch_name]

    max_event = getattr(current_branch, "max_event", None)
    if max_event is None or current_branch.head_event >= max_event:
        return {"ok": False, "message": "Nothing to redo.", "head_event": current_branch.head_event}

    target_event = find_checkpoint_for_redo(
        root, current_branch_name, current_branch.head_event, max_event
    )
    if target_event is None:
        return {
            "ok": False,
            "message": "No redo checkpoint available.",
            "head_event": current_branch.head_event,
        }

    if not restore_checkpoint(root, current_branch_name, target_event):
        return {
            "ok": False,
            "message": f"Failed to restore checkpoint for event {target_event}",
            "head_event": current_branch.head_event,
        }

    old_head = current_branch.head_event
    current_branch.head_event = target_event
    if target_event >= max_event:
        current_branch.max_event = None
    atomic_write_json(manifest_path, manifest.model_dump())
    return {
        "ok": True,
        "message": f"Redid change. Game state restored to event {target_event} (was {old_head}).",
        "head_event": target_event,
    }


@click.command()
def undo():
    """Undo the last change: restore game state from checkpoint and decrement head_event."""
    result = perform_undo(get_project_root())
    click.echo(result["message"], err=not result["ok"] and "Failed" in result["message"])


@click.command()
def redo():
    """Redo a previously undone change: restore game state from checkpoint and increment head_event."""
    result = perform_redo(get_project_root())
    click.echo(result["message"], err=not result["ok"] and "Failed" in result["message"])

