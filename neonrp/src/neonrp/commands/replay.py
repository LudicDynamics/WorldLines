"""Replay commands for determinism verification.

Provides commands to replay events and verify game state consistency.
"""

import json
import sys

import click
from pathlib import Path

from neonrp.core.paths import get_project_root
from neonrp.core.replay import replay_verify


def _fail(message: str, json_output: bool) -> None:
    """Print error and exit with code 1."""
    if json_output:
        click.echo(json.dumps({"success": False, "error": message}, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)
    sys.exit(1)


@click.group("replay")
def replay_group():
    """Replay commands for determinism verification."""
    pass


@replay_group.command("verify")
@click.option("--from", "from_save", required=True, help="Save ID to replay from")
@click.option("--branch", default=None, help="Branch to replay on (defaults to save's branch)")
@click.option("--to", "to_event", type=int, default=None, help="Target event ID (defaults to head)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def verify(from_save: str, branch: str, to_event: int, json_output: bool):
    """Verify determinism by replaying events from a save.

    Replays events from the save baseline to either the target event or
    the current head, comparing game state after each event.

    Does NOT modify the real game/ directory.
    """
    root = get_project_root()

    result = replay_verify(root, from_save, branch, to_event)

    if json_output:
        output = {
            "success": result.success,
            "from_save": result.from_save,
            "branch": result.branch,
            "target_event": result.target_event,
            "events_total": result.events_total,
            "events_replayed": result.events_replayed,
            "events_skipped": result.events_skipped,
        }

        if result.error:
            output["error"] = result.error

        if result.divergent_event:
            output["divergent_event"] = result.divergent_event

        # Include replay events summary if any failed
        failed_events = [e for e in result.replayed_events if not e.success]
        if failed_events:
            output["failed_events"] = [
                {"event_id": e.event_id, "type": e.event_type, "error": e.error} for e in failed_events
            ]

        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        if not result.success:
            sys.exit(1)
    else:
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
            sys.exit(1)

        click.echo(f"Replay from save '{result.from_save}'")
        click.echo(f"  Branch: {result.branch}")
        click.echo(f"  Target event: {result.target_event}")
        click.echo(f"  Events total: {result.events_total}")
        click.echo(f"  Events replayed: {result.events_replayed}")
        if result.events_skipped:
            click.echo(f"  Events skipped (non-replayable): {result.events_skipped}")

        # Report failed events
        failed_events = [e for e in result.replayed_events if not e.success]
        if failed_events:
            click.echo("\n  Failed events:")
            for e in failed_events:
                click.echo(f"    - Event {e.event_id} ({e.event_type}): {e.error}")

        if result.divergent_event:
            click.echo("\n  [FAIL] DIVERGENCE DETECTED:")
            click.echo(f"    File: {result.divergent_event['first_divergent_file']}")
            click.echo(f"    Expected hash: {result.divergent_event['expected_hash'][:20]}...")
            click.echo(f"    Actual hash: {result.divergent_event['actual_hash'][:20]}...")
            sys.exit(1)
        elif result.success:
            click.echo("\n  [OK] Replay verification passed")
        else:
            click.echo("\n  [WARN] Replay completed with errors")
            sys.exit(1)


@replay_group.command("checkout")
@click.option("--from", "from_save", required=True, help="Save ID to replay from")
@click.option("--to", "to_event", type=int, required=True, help="Target event ID to replay to")
@click.option("--to-branch", "to_branch", required=True, help="New sandbox branch name to create")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def checkout(from_save: str, to_event: int, to_branch: str, json_output: bool):
    """Replay events to a target point and create a sandbox.

    Replays from the save baseline to the target event, then creates
    a new sandbox branch with the resulting game state.

    This is useful for:
    - Time-traveling to a specific point in history
    - Creating a branch from a past state for debugging
    """
    from neonrp.core.replay import replay_to_sandbox

    root = get_project_root()

    result = replay_to_sandbox(root, from_save, to_event, to_branch)

    if json_output:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        if not result.get("success", False):
            sys.exit(1)
    else:
        if not result.get("success", False):
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        click.echo(f"[OK] Created sandbox '{result['branch']}' at event {result['head_event']}")
        click.echo(f"  Game hash: {result['game_hash'][:20]}...")
        click.echo(f"\nTo switch: neonrp sandbox switch {result['branch']}")



# ── Replay bundles for the Hub 回放馆 (TODO #2) ────────────────────────


@replay_group.command("export")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None, help="Zip path (default: ~/Downloads/<world>-replay-<stamp>.zip)")
@click.option("--lang", default="zh", show_default=True)
@click.option("--uploader", default="", help="Handle shown on the replay card")
def replay_export(run_dir: Path, out: Path | None, lang: str, uploader: str) -> None:
    """Pack a saved run (~/.worldlines/plays/<run>) as a Replay Bundle zip.

    Only timeline.json (worldlines.replay/1) / story.md / feed.jsonl / cover.png go in —
    sessions, logs, playthrough and the world's own files never do.
    """
    from neonrp.core.replay_export import ReplayExportError, build_replay_bundle, default_replay_out

    target = out or default_replay_out(run_dir)
    try:
        meta = build_replay_bundle(run_dir, target, lang=lang, uploader=uploader)
    except ReplayExportError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"✓ Replay bundle: {target} ({target.stat().st_size // 1024} KB, {meta['turns']} turns, world={meta['world']['slug']})")


@replay_group.command("upload")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--name", default=None, help="Card title (default: '<world> · replay')")
@click.option("--lang", default="zh", show_default=True)
@click.option("--token", default=None, envvar="HUB_API_TOKEN", help="WorldHub session token (env: HUB_API_TOKEN).")
@click.option("--api-url", default=None, envvar="HUB_API_URL", help="WorldHub API base URL.")
def replay_upload(run_dir: Path, name: str | None, lang: str, token: str | None, api_url: str | None) -> None:
    """Pack a saved run as a replay and upload it to the Hub as a draft.

    Submit it for review from the Hub's account page; approved replays show
    in the 回放馆 (hub.worldlines.gg/replays).
    """
    from neonrp.core.worldhub import WorldHubError, upload_replay_via_api

    try:
        entry = upload_replay_via_api(run_dir, name=name, lang=lang, api_token=token, api_url=api_url)
    except WorldHubError as exc:
        raise click.ClickException(str(exc))
    click.echo(f"✓ Uploaded replay — {entry.get('name')}  ·  {entry.get('slug')}")
    click.echo(f"  turns:  {entry.get('turns')}")
    click.echo(f"  status: {entry.get('status', 'draft')}  (submit for review from https://hub.worldlines.gg/account)")
