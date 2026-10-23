"""`neonrp mode` — get or set a world's play mode (execution_mode).

The three modes consume the cast differently:

* fast         — world only, no characters
* orchestrator — one world-agent voices the world-baked NPCs (game/npc/)
* multi-agent  — each cast soul is its own agent (playthrough.json souls[])

With no argument, prints the current mode.
"""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.core.runtime_contract import (
    VALID_ROUTER_EXECUTION_MODES,
    get_router_execution_mode,
    is_soul_world,
    set_router_execution_mode,
    valid_execution_modes,
)


def _resolve_game_dir(into: str | None) -> Path:
    game_dir = Path(into).expanduser() if into else Path.cwd()
    if not (game_dir / ".neonrp").exists() and not (game_dir / "game").exists():
        raise click.ClickException(
            f"{game_dir} is not a NeonRP world folder (no .neonrp/ or game/)."
        )
    return game_dir


@click.command("mode")
@click.argument(
    "value",
    required=False,
    type=click.Choice(list(VALID_ROUTER_EXECUTION_MODES)),
)
@click.option("--into", default=None, help="World folder (default: current directory).")
def mode(value: str | None, into: str | None) -> None:
    """Show the current play mode, or set it to VALUE."""
    game_dir = _resolve_game_dir(into)
    if value is None:
        current = get_router_execution_mode(game_dir)
        click.echo(current)
        return
    # Mode is two axes: the world's STRUCTURE (soul world ↔ flat world) and,
    # within a flat world, the router execution (fast ↔ orchestrator). Only the
    # latter is a runtime toggle — orchestrator and multi-agent are different
    # protocols and not interchangeable. Reject cross-structure switches.
    allowed = valid_execution_modes(game_dir)
    if value not in allowed:
        reason = (
            "a multi-agent soul world — fast/orchestrator would orphan its souls"
            if is_soul_world(game_dir)
            else "a flat world with no souls — multi-agent needs souls/playthrough (a rebuild)"
        )
        raise click.ClickException(
            f"'{value}' isn't available here: this is {reason}. "
            f"Available: {', '.join(allowed)}."
        )
    try:
        applied = set_router_execution_mode(game_dir, value)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"mode → {applied}")
