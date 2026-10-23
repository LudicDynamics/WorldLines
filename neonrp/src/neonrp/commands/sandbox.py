"""Sandbox commands for isolated experimental branches.

Sandboxes allow creating isolated copies of game state from saves
for experimentation without affecting the main branch.
"""

import json
import shutil
import sys
from pathlib import Path

import click

from neonrp.core.manifest import BranchMetadata, Manifest
from neonrp.core.paths import (
    GAME_DIR_NAME,
    get_manifest_path,
    get_neonrp_dir,
    get_project_root,
    get_game_dir,
    validate_branch_name,
)
from neonrp.core.storage import atomic_write_json
from neonrp.commands.save import get_saves_dir


def _fail(message: str, json_output: bool) -> None:
    """Print error and exit with code 1."""
    if json_output:
        click.echo(json.dumps({"success": False, "error": message}, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _load_manifest(root: Path) -> Manifest:
    """Load and return the manifest."""
    manifest_path = get_manifest_path(root)
    with open(manifest_path, "r", encoding="utf-8") as f:
        return Manifest(**json.load(f))


def _save_manifest(root: Path, manifest: Manifest) -> None:
    """Save the manifest atomically."""
    manifest_path = get_manifest_path(root)
    atomic_write_json(manifest_path, manifest.model_dump())


@click.group("sandbox")
def sandbox_group():
    """Manage sandbox branches for experimentation."""
    pass


@sandbox_group.command("new")
@click.argument("name")
@click.option("--from", "from_save", required=True, help="Save ID to create sandbox from")
@click.option("--switch", is_flag=True, help="Switch to the new sandbox after creation")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def sandbox_new(name: str, from_save: str, switch: bool, json_output: bool):
    """Create a new sandbox from a save.

    NAME is the sandbox branch name.
    """
    root = get_project_root()
    saves_dir = get_saves_dir(root)
    save_dir = saves_dir / from_save

    # Validate save exists and has meta
    if not save_dir.exists():
        _fail(f"Save '{from_save}' not found", json_output)

    meta_path = save_dir / "meta.json"
    if not meta_path.exists():
        _fail(f"Save '{from_save}' is missing meta.json (old format). Please re-save.", json_output)

    # Load save meta
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Validate name
    name_error = validate_branch_name(name)
    if name_error:
        _fail(name_error, json_output)

    if name == "main":
        _fail("Cannot create sandbox with name 'main'", json_output)

    # Load manifest
    manifest = _load_manifest(root)

    if name in manifest.branches:
        _fail(f"Branch '{name}' already exists", json_output)

    # Create sandbox branch metadata
    sandbox_meta = BranchMetadata(
        head_event=meta["head_event"],
        kind="sandbox",
        parent=meta["branch"],
        fork_event=meta["head_event"],
        base_save=from_save,
    )
    manifest.branches[name] = sandbox_meta

    # Copy events log for the sandbox
    events_dir = get_neonrp_dir(root) / "events"
    sandbox_events = events_dir / f"{name}.jsonl"

    # Copy events from save
    save_events = save_dir / "events.jsonl"
    if save_events.exists():
        shutil.copy2(save_events, sandbox_events)
    else:
        sandbox_events.write_text("", encoding="utf-8")

    # Create sandbox game directory from save
    branches_dir = get_neonrp_dir(root) / "branches"
    branches_dir.mkdir(exist_ok=True)
    sandbox_game_dir = branches_dir / name / GAME_DIR_NAME

    # Copy game data from save
    save_game = save_dir / GAME_DIR_NAME
    if sandbox_game_dir.parent.exists():
        shutil.rmtree(sandbox_game_dir.parent)
    sandbox_game_dir.parent.mkdir(parents=True)
    shutil.copytree(save_game, sandbox_game_dir)

    # Save manifest
    _save_manifest(root, manifest)

    # Switch if requested
    if switch:
        _do_switch(root, manifest, name, json_output)
        return

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "sandbox": name,
                    "from_save": from_save,
                    "head_event": meta["head_event"],
                    "parent": meta["branch"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"Created sandbox '{name}' from save '{from_save}'")
        click.echo(f"  Parent: {meta['branch']}")
        click.echo(f"  Head event: {meta['head_event']}")
        click.echo(f"To switch: neonrp sandbox switch {name}")


@sandbox_group.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def sandbox_list(json_output: bool):
    """List all branches (main and sandboxes)."""
    root = get_project_root()
    manifest = _load_manifest(root)

    branches_info = []
    for name, meta in manifest.branches.items():
        info = {
            "name": name,
            "kind": getattr(meta, "kind", "main"),
            "head_event": meta.head_event,
            "current": name == manifest.current_branch,
        }
        if hasattr(meta, "parent") and meta.parent:
            info["parent"] = meta.parent
        if hasattr(meta, "base_save") and meta.base_save:
            info["base_save"] = meta.base_save
        branches_info.append(info)

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "current_branch": manifest.current_branch,
                    "branches": branches_info,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo("Branches:")
        for info in branches_info:
            marker = "*" if info["current"] else " "
            kind_label = f"[{info['kind']}]" if info["kind"] != "main" else ""
            parent_info = f" (from {info.get('parent', 'n/a')})" if info["kind"] == "sandbox" else ""
            click.echo(f"  {marker} {info['name']} {kind_label}{parent_info} - head: {info['head_event']}")


@sandbox_group.command("switch")
@click.argument("name")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def sandbox_switch(name: str, json_output: bool):
    """Switch to a different branch (main or sandbox)."""
    root = get_project_root()

    # Validate name (allow "main" for switching)
    if name != "main":
        name_error = validate_branch_name(name)
        if name_error:
            _fail(name_error, json_output)

    manifest = _load_manifest(root)

    if name not in manifest.branches:
        _fail(f"Branch '{name}' not found", json_output)

    if name == manifest.current_branch:
        if json_output:
            click.echo(
                json.dumps({"success": True, "branch": name, "message": "Already on this branch"}, indent=2, ensure_ascii=False)
            )
        else:
            click.echo(f"Already on branch '{name}'")
        return

    _do_switch(root, manifest, name, json_output)


def _do_switch(root: Path, manifest: Manifest, name: str, json_output: bool) -> None:
    """Perform branch switch with atomic game-directory replacement."""
    old_branch = manifest.current_branch
    game_dir = get_game_dir(root)
    branches_dir = get_neonrp_dir(root) / "branches"

    # Save current game data to branch storage
    old_branch_dir = branches_dir / old_branch / GAME_DIR_NAME
    old_branch_dir.parent.mkdir(parents=True, exist_ok=True)

    if game_dir.exists():
        # Use atomic swap to save current game data
        game_tmp = game_dir.with_suffix(".switching")
        if game_tmp.exists():
            shutil.rmtree(game_tmp)
        if old_branch_dir.exists():
            shutil.rmtree(old_branch_dir)
        shutil.copytree(game_dir, old_branch_dir)

    # Load new branch game data
    new_branch_dir = branches_dir / name / GAME_DIR_NAME

    if not new_branch_dir.exists():
        _fail(f"Branch '{name}' has no game directory. This may be a corrupted sandbox.", json_output)

    # Replace game directory with branch copy.
    # On Windows, Path.rename() fails with "Access denied" when file handles are open.
    if game_dir.exists():
        shutil.rmtree(game_dir)
    shutil.copytree(new_branch_dir, game_dir)

    # Update manifest
    manifest.current_branch = name
    manifest.entities = {}  # Invalidate entity index
    _save_manifest(root, manifest)

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "branch": name,
                    "from_branch": old_branch,
                    "index_invalidated": True,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"Switched to branch '{name}'")
        click.echo("  Entity index invalidated. It will auto-refresh on next find/context/list_entities query.")


@sandbox_group.command("drop")
@click.argument("name")
@click.option("--force", is_flag=True, help="Force drop even if on this branch (switches to main first)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def sandbox_drop(name: str, force: bool, json_output: bool):
    """Delete a sandbox branch.

    Cannot drop 'main'. Cannot drop current branch without --force.
    """
    root = get_project_root()

    # Validate name before filesystem operations
    name_error = validate_branch_name(name)
    if name_error:
        _fail(name_error, json_output)

    manifest = _load_manifest(root)

    if name == "main":
        _fail("Cannot drop the 'main' branch", json_output)

    if name not in manifest.branches:
        _fail(f"Branch '{name}' not found", json_output)

    branch_meta = manifest.branches[name]
    if getattr(branch_meta, "kind", "main") != "sandbox":
        _fail(f"Branch '{name}' is not a sandbox", json_output)

    if name == manifest.current_branch:
        if not force:
            _fail(f"Cannot drop current branch '{name}'. Switch to another branch first, or use --force.", json_output)
        # Switch to main first
        _do_switch(root, manifest, "main", json_output=False)
        # Reload manifest after switch
        manifest = _load_manifest(root)

    # Remove branch metadata
    del manifest.branches[name]
    _save_manifest(root, manifest)

    # Remove branch files
    branches_dir = get_neonrp_dir(root) / "branches"
    branch_dir = branches_dir / name
    if branch_dir.exists():
        shutil.rmtree(branch_dir)

    # Remove events log
    events_dir = get_neonrp_dir(root) / "events"
    events_file = events_dir / f"{name}.jsonl"
    if events_file.exists():
        events_file.unlink()

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "dropped": name,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"Dropped sandbox '{name}'")


