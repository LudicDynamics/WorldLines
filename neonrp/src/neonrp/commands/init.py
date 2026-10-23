import click

from neonrp.core.storage import ensure_dirs, atomic_write_json
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_project_root, get_manifest_path
from neonrp.core.config import get_config_path, create_default_config_template


@click.command()
def init():
    """Initialize a new NeonRP project in the current directory."""
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if manifest_path.exists():
        click.echo("NeonRP project already initialized.")
        return

    click.echo(f"Initializing NeonRP project in {root}")

    # 1. Create directory structure
    ensure_dirs(root)

    # 2. Create initial manifest.json
    manifest = Manifest()
    atomic_write_json(manifest_path, manifest.model_dump())

    # 3. Create config.json template (optional, for LLM settings)
    config_path = get_config_path(root)
    if not config_path.exists():
        atomic_write_json(config_path, create_default_config_template())
        click.echo("Created config.json (configure LLM settings here).")

    click.echo("Initialized .neonrp/ structure.")
    click.echo("Created manifest.json.")
