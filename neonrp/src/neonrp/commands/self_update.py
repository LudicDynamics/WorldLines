"""`neonrp self-update` command group (L14 Phase 1)."""

from __future__ import annotations

import click

from neonrp.core import updater


@click.group(name="self-update")
def self_update() -> None:
    """Check for and apply updates to neonrp / worldlines."""


@self_update.command("check")
@click.option("--channel", default=None, help="stable | preview | nightly")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON")
def check_cmd(channel: str | None, as_json: bool) -> None:
    """Check whether a newer release is available."""
    result = updater.check_for_update(channel=channel)
    if as_json:
        import json as _json

        click.echo(_json.dumps(result.to_json(), indent=2, ensure_ascii=False))
        return
    click.echo(updater.format_result_for_human(result))


@self_update.command("status")
def status_cmd() -> None:
    """Show current version and install mode without hitting the network."""
    install_mode = updater.detect_install_mode()
    click.echo(f"  current: {updater.get_current_version()}")
    click.echo(f"  install: {install_mode.kind} ({install_mode.detail})")
    click.echo(f"  auto-apply allowed: {install_mode.allow_auto_apply}")
    settings = updater.get_update_settings()
    click.echo(f"  channel: {settings.get('channel')}")
    click.echo(f"  mode:    {settings.get('mode')}")
    click.echo(f"  check_on_launch: {settings.get('check_on_launch')}")


@self_update.command("apply")
@click.option("--package", default="neonrp", type=click.Choice(["neonrp", "worldlines"]))
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def apply_cmd(package: str, yes: bool) -> None:
    """Delegate the upgrade to uv/pipx/pip."""
    install_mode = updater.detect_install_mode()
    if not install_mode.allow_auto_apply:
        click.echo(
            "  Auto-apply is disabled for this install mode "
            f"({install_mode.kind}). Please upgrade manually."
        )
        raise SystemExit(2)

    cmd = updater.build_upgrade_command(package)
    if cmd is None:
        click.echo("  No supported package manager (uv / pipx / pip) found on PATH.")
        raise SystemExit(2)

    printable = " ".join(cmd)
    if not yes:
        click.echo(f"  About to run: {printable}")
        if not click.confirm("  Continue?", default=True):
            click.echo("  Cancelled.")
            return

    ok, output = updater.apply_update_in_background(package)
    if output:
        click.echo(output)
    if not ok:
        raise SystemExit(1)


@self_update.command("channel")
@click.argument("channel", type=click.Choice(["stable", "preview", "nightly"]))
def channel_cmd(channel: str) -> None:
    """Change the update channel."""
    settings = updater.set_update_settings(channel=channel)
    click.echo(f"  update channel set to: {settings['channel']}")


@self_update.command("skip")
@click.argument("version")
def skip_cmd(version: str) -> None:
    """Remember that the user does not want to be prompted about `version` again."""
    updater.mark_version_skipped(version)
    click.echo(f"  skipped: {version}")
