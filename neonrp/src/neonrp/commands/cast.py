"""`neonrp cast` — cast a reusable soul into a world (mode-aware placement).

Casting projects a world-agnostic soul asset into a concrete world. WHERE
it lands depends on the world's ``execution_mode`` (see
``neonrp.core.placement``):

* orchestrator → ``game/npc/<id>.json`` (world-baked NPC, one world-agent voices it)
* multi-agent  → ``souls/<sid>-<iid>/`` + a ``SoulRef`` in ``playthrough.json``
* fast         → rejected (fast has no characters)

``--as player`` casts the soul as the human player's avatar (分身) instead.
"""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.core.placement import (
    PlacementError,
    cast_receipt,
    project_avatar_multiagent,
    project_avatar_orchestrator,
    project_soul_as_npc,
    project_soul_multiagent,
    resolve_soul_dir,
)
from neonrp.core.runtime_contract import get_router_execution_mode


def _resolve_game_dir(into: str | None) -> Path:
    game_dir = Path(into).expanduser() if into else Path.cwd()
    if not (game_dir / ".neonrp").exists() and not (game_dir / "game").exists():
        raise click.ClickException(
            f"{game_dir} is not a NeonRP world folder (no .neonrp/ or game/)."
        )
    return game_dir


@click.command("cast")
@click.argument("soul")
@click.option(
    "--into",
    default=None,
    help="World folder to cast into (default: current directory).",
)
@click.option(
    "--as",
    "as_role",
    type=click.Choice(["npc", "player"]),
    default="npc",
    show_default=True,
    help="Cast as an NPC, or as the human player's avatar (分身).",
)
@click.option(
    "--location",
    default="",
    help="Starting location for an orchestrator NPC (game/npc only).",
)
@click.option("--id", "npc_id", default=None, help="Override the NPC id (orchestrator).")
@click.option("--force", is_flag=True, default=False, help="Overwrite an existing NPC.")
@click.option(
    "--adapt",
    is_flag=True,
    default=False,
    help="After placing, run the casting skill (agent) to adapt the NPC to "
    "this world — fills role/why-here/relationships/known-lore (orchestrator NPC).",
)
def cast(
    soul: str,
    into: str | None,
    as_role: str,
    location: str,
    npc_id: str | None,
    force: bool,
    adapt: bool,
) -> None:
    """Cast SOUL (a sid or soul-folder path) into a world."""
    try:
        game_dir = _resolve_game_dir(into)
        soul_dir = resolve_soul_dir(soul)
        mode = get_router_execution_mode(game_dir)

        if as_role == "player":
            if mode == "orchestrator":
                target = project_avatar_orchestrator(game_dir, soul_dir)
            else:  # multi-agent
                ref = project_avatar_multiagent(game_dir, soul_dir)
                target = f"playthrough player '{ref.pid}' ({ref.name})"
        else:  # npc
            if mode == "orchestrator":
                target = project_soul_as_npc(
                    game_dir, soul_dir, location=location, npc_id=npc_id, overwrite=force
                )
            else:  # multi-agent
                ref = project_soul_multiagent(
                    game_dir, soul_dir, role="npc", force=force
                )
                target = f"souls/{ref.sid}-{ref.instance_id} (+playthrough)"

        click.echo(cast_receipt(mode, str(target), as_role))

        # Opt-in agentic adaptation (orchestrator NPC only): run the casting
        # skill to author the placement overlay. Best-effort — the faithful
        # fast-path NPC stays put if it fails.
        if adapt and as_role == "npc" and mode == "orchestrator":
            from neonrp.core.cast_agent import adapt_npc_with_agent

            resolved_id = npc_id or Path(str(target)).stem
            click.echo(f"adapting '{resolved_id}' to the world (casting skill)…")
            if adapt_npc_with_agent(game_dir, resolved_id):
                click.echo("  ✓ placement authored (adapted=true)")
            else:
                click.echo("  · adaptation skipped/failed — fast-path NPC kept")
    except PlacementError as exc:
        raise click.ClickException(str(exc)) from exc
