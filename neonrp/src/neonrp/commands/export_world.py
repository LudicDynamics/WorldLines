"""`neonrp export-world` and `neonrp load-world` CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from neonrp.core.world_export import (
    default_export_path,
    export_world as core_export,
    load_world_zip,
    summarize_archive,
)


@click.command("export-world")
@click.option(
    "--root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="World folder to export (default: current working directory)",
)
@click.option(
    "--world",
    "world_id",
    type=str,
    default=None,
    help="Export an OWNED library world by id (reads its WORLDS_HOME source)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Destination zip path (default: ~/Downloads/worldlines-<name>-<ts>.zip)",
)
@click.option("--no-logs", is_flag=True, help="Skip .neonrp/logs/ to keep the archive small")
def export_world(root: Path | None, world_id: str | None, output: Path | None, no_logs: bool) -> None:
    """Zip a worldlines world to a single .zip archive.

    Sharing a world reads from the world SOURCE (the library under
    ``~/.worldlines/worlds/``). Pass ``--world <id>`` to export an owned
    library world by id, ``--root <dir>`` for an explicit folder, or neither
    to export the current working directory.
    """
    if world_id is not None:
        from neonrp.worlds import get_owned_world_dir

        source = get_owned_world_dir(world_id)
        if source is None:
            raise click.ClickException(
                f"no owned world with id {world_id!r} in the library "
                "(~/.worldlines/worlds/)."
            )
        world_path = source.resolve()
    else:
        world_path = (root or Path.cwd()).resolve()
    target = output or default_export_path(world_path)
    try:
        final = core_export(world_path, target, include_logs=not no_logs)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc))
    info = summarize_archive(final)
    click.echo(f"✓ Exported {info['file_count']} files  —  {info['size_mb']} MB")
    click.echo(f"  {final}")


@click.command("load-world")
@click.argument("zip_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--overwrite", is_flag=True, help="Replace an existing folder with the same name")
def load_world(zip_path: Path, overwrite: bool) -> None:
    """Restore a worldlines world from an exported .zip archive.

    The extracted world lands under ~/.worldlines/worlds/ as a library
    source and will appear in the WorldLines launcher's world picker.
    """
    try:
        target = load_world_zip(zip_path, overwrite=overwrite)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc))
    click.echo(f"✓ Loaded into: {target}")
