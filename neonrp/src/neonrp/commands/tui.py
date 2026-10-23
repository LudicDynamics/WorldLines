"""TUI CLI command entry point."""

from pathlib import Path
import shlex

import click

@click.command()
@click.option("--branch", default=None, help="Branch to use (default: current branch)")
@click.option("--provider", default=None, help="LLM provider override (default: from config)")
@click.option("--continue", "continue_session", is_flag=True, help="Continue the previous session on startup")
@click.option("--new", "new_session", is_flag=True, help="Start a brand new session on startup (default)")
@click.option("--import-card", "import_card", type=click.Path(exists=True), help="Import a SillyTavern JSON/PNG card on startup")
@click.option("--import-id", "import_id", default=None, help="Override imported entity ID for --import-card")
@click.option("--verbose", is_flag=True, help="Enable verbose debug mode (extra logs and on-screen diagnostics)")
@click.option("--play", "play_mode", is_flag=True, help="Launch in play mode (run a game; enables the multi-agent soul lane). Default is build mode.")
@click.option("--connect", "connect_url", default=None, help="Play through a headless host (neonrp serve) at this URL instead of an engine in this process (10-10: the TUI is a client).")
@click.option("--token", "connect_token", default=None, help="The host's token for --connect (printed by neonrp serve).")
@click.option("--join", "join_invite", default=None, help="Take a seat at a networked table: an invite link (worldlines://join?…) or its short code (with --url).")
@click.option("--url", "join_url", default=None, help="The host's address for a short invite code (http://<host:port>).")
@click.option("--from", "from_world", type=click.Path(exists=True, file_okay=False), default=None, help="Clean play: build a FRESH run of this template package (a folder with template.json) into ~/.worldlines/plays/ and play THERE — the package is never mutated. Implies play mode.")
def tui(
    branch: str | None,
    provider: str | None,
    continue_session: bool,
    new_session: bool,
    import_card: str | None,
    import_id: str | None,
    verbose: bool,
    play_mode: bool,
    connect_url: str | None,
    connect_token: str | None,
    join_invite: str | None,
    join_url: str | None,
    from_world: str | None,
):
    """Launch the NeonRP Terminal User Interface.

    The TUI provides a Claude Code/OpenCode-style workflow for:
    - Running agents and previewing diffs
    - Browsing files and logs
    - Managing sandboxes and saves
    """
    if continue_session and new_session:
        click.echo("Error: --continue and --new cannot be used together.", err=True)
        raise SystemExit(1)
    if import_id and not import_card:
        click.echo("Error: --import-id requires --import-card.", err=True)
        raise SystemExit(1)

    startup_commands: list[str] = []
    if import_card:
        quoted_path = shlex.quote(import_card)
        command = f"/import sillytavern-card {quoted_path}"
        if import_id:
            command += f" --id {shlex.quote(import_id)}"
        startup_commands.append(command)

    # --from <x.template>: the CLEAN entry. The template package is built into a
    # fresh run in PLAYS_HOME (template.new_run, the same build the web's new
    # game does) and played THERE — the package is never mutated. Implies play
    # mode; the opening is sent below (a fresh run has no turn yet).
    root = Path.cwd()
    if from_world:
        src = Path(from_world).resolve()
        if not (src / "template.json").is_file():
            click.echo(f"Error: --from takes a template package (a folder with template.json): {src}", err=True)
            raise SystemExit(1)
        from neonrp import template as _tpl

        inst = _tpl.new_run(src)
        root = inst
        play_mode = True
        click.echo(f"  Clean play instance: {inst}")
        click.echo(f"  Template untouched:  {src}\n")

    if join_invite:  # 10-10: take a seat with an invite — wait for the host to approve, keep the credential for next time
        from urllib.parse import parse_qs, urlparse

        from neonrp.net.client import RemoteClient, credentials_file

        inv, url = join_invite.strip(), join_url
        if inv.startswith("worldlines://"):
            q = {k: v[0] for k, v in parse_qs(urlparse(inv).query).items()}
            inv, url = q.get("t", ""), url or (f"http://{q['h']}" if q.get("h") else None)
        if not url:
            click.echo("Error: a short code needs --url http://<host:port>", err=True)
            raise SystemExit(1)
        click.echo(f"  joining {url} …")
        c = RemoteClient.join(url, inv, who=Path.cwd().name, store=credentials_file(),
                              on_pending=lambda r: click.echo(f"  waiting for the host to approve (request {r}) …"))
        seat = c.call("session.whoami")
        c.close()
        click.echo(f"  seated: {seat.get('seat')}")
        connect_url, connect_token = url, c.token
        if seat.get("kind") != "player":  # a character / an agent seat speaks when the table turns to it: no opening line
            continue_session, startup_commands[:] = True, []

    if connect_url:  # a client of a host: the turns run there (step ⓪: same machine — run it inside the world folder: the panels still read it)
        import os

        os.environ["NEONRP_CONNECT_URL"] = connect_url
        os.environ["NEONRP_CONNECT_TOKEN"] = connect_token or ""
        play_mode = True

    # Playing a world nobody has played yet opens with its opening — no blank prompt waiting for 「开始游戏」.
    # A world already played continues where it was (its turn record says so).
    if play_mode and not startup_commands and not continue_session and not (_host_played(connect_url, connect_token) if connect_url else _played(root)):
        from neonrp.core.opening import start_cue

        startup_commands.append(start_cue(root))  # in the run's language (zh/en/ja/ko)

    # Use conversational TUI.
    # Intentionally allow non-initialized directories so users can run /init inside TUI.
    from neonrp.tui.app import run_tui

    run_tui(
        root=root,
        branch=branch,
        provider=provider,
        continue_session=continue_session and not new_session,
        startup_commands=startup_commands,
        verbose=verbose,
        # Play mode is what composes the game UI incl. the persistent
        # multi-agent soul-status lane; bare `neonrp tui` stays build (the
        # authoring default). --from forces play (you're playing a game instance).
        mode="play" if play_mode else "build",
    )


def _host_played(url: str, token: str | None) -> bool:
    """Has the host's world had a turn? (10-21: a client read its own folder, found nothing, and sent the opening
    again into a run three turns in.) Unknown → played: no opening is sent into someone's table."""
    try:
        from neonrp.net.client import RemoteClient

        c = RemoteClient(url, token or "")
        try:
            return int(c.total_turns or 0) > 0 or bool(c.get_messages())
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return True


def _played(root: Path) -> bool:
    """Has this world had a turn? (any turn record on any branch)"""
    d = root / ".neonrp" / "orchestration"
    try:
        return any(f.stat().st_size > 0 for f in d.glob("*.jsonl"))
    except OSError:
        return False
