import click
import json
from datetime import datetime, timezone
from pathlib import Path
from neonrp.core.paths import (
    GAME_DIR_NAME,
    get_manifest_path,
    get_neonrp_dir,
    get_project_root,
    get_game_dir,
)
from neonrp.core.manifest import Manifest
from neonrp.core.hashing import compute_game_hash
from neonrp.core.event_log import get_event_log_path
from neonrp.core.session import clear_session, get_session_path


def get_saves_dir(root: Path) -> Path:
    return get_neonrp_dir(root) / "saves"


def get_save_session_path(root: Path, snapshot_id: str) -> Path:
    return get_saves_dir(root) / snapshot_id / "session.jsonl"


def list_loadable_save_snapshots(root: Path) -> list[dict]:
    """List snapshots that have the minimal structure required for load.

    Returns newest-first when timestamps are available.
    """
    saves_dir = get_saves_dir(root)
    if not saves_dir.exists():
        return []

    snapshots: list[dict] = []
    for save_dir in saves_dir.iterdir():
        if not save_dir.is_dir():
            continue

        source = save_dir / GAME_DIR_NAME
        meta_path = save_dir / "meta.json"
        if not source.exists() or not meta_path.exists():
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        branch = meta.get("branch")
        head_event = meta.get("head_event")
        created = meta.get("created")
        save_id = meta.get("save_id") or save_dir.name
        if not isinstance(branch, str) or not branch:
            continue
        if not isinstance(head_event, int):
            continue
        if not isinstance(save_id, str) or not save_id:
            continue

        snapshots.append(
            {
                "save_id": save_id,
                "branch": branch,
                "head_event": head_event,
                "created": created if isinstance(created, str) else "",
            }
        )

    snapshots.sort(key=lambda item: (item.get("created") or "", item["save_id"]), reverse=True)
    return snapshots


# ---------------------------------------------------------------------------
# Core functions (usable from both CLI and TUI)
# ---------------------------------------------------------------------------


def create_save_snapshot(root: Path, name: str | None = None) -> dict:
    """Create a save snapshot of the current game state.

    Returns a dict with save_id, branch, head_event, game_hash on success.
    Raises ValueError or OSError on failure.
    """
    from neonrp.core.storage import atomic_copy_file, atomic_write_dir, atomic_write_json, atomic_write_text

    saves_dir = get_saves_dir(root)
    game_dir = get_game_dir(root)

    if not game_dir.exists():
        raise ValueError("game/ directory not found")

    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        raise ValueError("Project not initialized. Run 'neonrp init' first.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = Manifest(**json.load(f))

    snapshot_id = name if name else datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    save_dir = saves_dir / snapshot_id
    dest = save_dir / GAME_DIR_NAME

    if save_dir.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' already exists")

    # 1. Copy game directory
    atomic_write_dir(dest, game_dir)

    # 2. Compute game hash
    game_hash = compute_game_hash(dest)

    # 3. Create meta.json
    current_branch = manifest.current_branch
    head_event = manifest.branches[current_branch].head_event

    meta = {
        "save_id": snapshot_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "branch": current_branch,
        "head_event": head_event,
        "game_hash": game_hash,
        "events_file": "events.jsonl",
        "session_file": "session.jsonl",
        "manifest_version": manifest.version,
    }
    atomic_write_json(save_dir / "meta.json", meta)

    # 4. Copy events log
    events_src = get_event_log_path(root, current_branch)
    events_dest = save_dir / "events.jsonl"
    if events_src.exists():
        atomic_copy_file(events_src, events_dest)
    else:
        atomic_write_text(events_dest, "")

    # 5. Copy current branch session snapshot
    session_src = get_session_path(root, current_branch)
    session_dest = get_save_session_path(root, snapshot_id)
    if session_src.exists():
        atomic_copy_file(session_src, session_dest)
    else:
        atomic_write_text(session_dest, "")

    return {
        "save_id": snapshot_id,
        "branch": current_branch,
        "head_event": head_event,
        "game_hash": game_hash,
    }


def load_save_snapshot(root: Path, snapshot_id: str) -> None:
    """Restore the game state from a snapshot.

    Raises ValueError if snapshot not found, OSError on filesystem errors.
    """
    from neonrp.core.storage import atomic_copy_file, atomic_write_dir, atomic_write_json, atomic_write_text

    saves_dir = get_saves_dir(root)
    source = saves_dir / snapshot_id / GAME_DIR_NAME
    meta_path = saves_dir / snapshot_id / "meta.json"
    events_src = saves_dir / snapshot_id / "events.jsonl"
    session_src = get_save_session_path(root, snapshot_id)

    if not source.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' not found.")
    if not meta_path.exists():
        raise ValueError(f"Snapshot '{snapshot_id}' is missing meta.json.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    branch = meta.get("branch")
    head_event = meta.get("head_event")
    if not isinstance(branch, str) or not branch:
        raise ValueError(f"Snapshot '{snapshot_id}' has invalid branch in meta.json.")
    if not isinstance(head_event, int):
        raise ValueError(f"Snapshot '{snapshot_id}' has invalid head_event in meta.json.")

    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        raise ValueError("Project not initialized. Run 'neonrp init' first.")
    manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
    if branch not in manifest.branches:
        raise ValueError(f"Snapshot branch '{branch}' not found in manifest.")

    # 1) Restore active game directory atomically
    game_dir = get_game_dir(root)
    atomic_write_dir(game_dir, source)
    expected_game_hash = meta.get("game_hash")
    if isinstance(expected_game_hash, str) and expected_game_hash:
        actual_game_hash = compute_game_hash(game_dir)
        if actual_game_hash != expected_game_hash:
            raise OSError(
                f"Game hash mismatch after load: expected {expected_game_hash}, got {actual_game_hash}"
            )

    # 2) Restore branch events atomically
    branch_events_path = get_event_log_path(root, branch)
    if events_src.exists():
        atomic_copy_file(events_src, branch_events_path)
    else:
        atomic_write_text(branch_events_path, "")

    # 3) Restore branch pointers
    manifest.current_branch = branch
    manifest.branches[branch].head_event = head_event
    if manifest.branches[branch].max_event is None or manifest.branches[branch].max_event < head_event:
        manifest.branches[branch].max_event = head_event
    atomic_write_json(manifest_path, manifest.model_dump())

    # 4) Restore current branch session snapshot
    branch_session_path = get_session_path(root, branch)
    if session_src.exists():
        atomic_copy_file(session_src, branch_session_path)
    else:
        clear_session(root, branch)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@click.command()
@click.argument("name", required=False)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def save(name, json_output):
    """Save the current game state to a snapshot."""
    import sys

    root = get_project_root()
    try:
        result = create_save_snapshot(root, name)
        if json_output:
            click.echo(json.dumps({"success": True, **result}, indent=2, ensure_ascii=False))
        else:
            click.echo(f"Saved snapshot: {result['save_id']}")
            click.echo(f"  Branch: {result['branch']}")
            click.echo(f"  Head event: {result['head_event']}")
            click.echo(f"  Game hash: {result['game_hash'][:20]}...")
    except (ValueError, OSError) as e:
        if json_output:
            click.echo(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            click.echo(f"Error: {e}")
        sys.exit(1)


@click.command()
@click.argument("snapshot_id", required=False)
def load(snapshot_id):
    """Restore the game state from a snapshot."""
    root = get_project_root()
    if not snapshot_id:
        snapshots = list_loadable_save_snapshots(root)
        if not snapshots:
            click.echo("No loadable snapshots found.")
            return

        click.echo(f"Loadable snapshots: {len(snapshots)}")
        for snapshot in snapshots:
            created = snapshot.get("created") or "unknown"
            click.echo(
                f"- {snapshot['save_id']}  branch={snapshot['branch']}  head_event={snapshot['head_event']}  created={created}"
            )
        click.echo("Use: neonrp load <snapshot_id>")
        return

    try:
        load_save_snapshot(root, snapshot_id)
        click.echo(f"Loaded snapshot: {snapshot_id}")
    except (ValueError, OSError) as e:
        click.echo(f"Error: {e}")
