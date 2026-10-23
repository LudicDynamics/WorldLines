"""Import commands for external content."""

import json
import sys

import click

from neonrp.core.paths import get_data_dir_name, get_manifest_path, get_project_root, get_game_dir
from neonrp.core.importers.sillytavern import build_entity_from_card_file
from neonrp.core.proposal import UpsertTextOp
from neonrp.core.system_proposal import apply_system_proposal


@click.group("import")
def import_group():
    """Import external content into NeonRP game data."""
    pass


@import_group.command("sillytavern-card")
@click.argument("file", type=click.Path(exists=True))
@click.option("--id", "entity_id", default=None, help="Override entity ID (kebab-case)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def sillytavern_card(file: str, entity_id: str | None, json_output: bool):
    """Import a SillyTavern character card into game data.

    FILE is the path to a SillyTavern character card JSON or PNG file.
    For PNG files, the character data is extracted from the embedded
    'chara' tEXt chunk.
    """
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        _fail("Not initialized. Run 'neonrp init' first.", json_output)

    data_dir = get_game_dir(root)
    character_dir = data_dir / "character"
    # Gather existing IDs for conflict resolution
    existing_ids: set[str] = set()
    if character_dir.exists():
        for p in character_dir.glob("*.json"):
            existing_ids.add(p.stem)

    try:
        entity = build_entity_from_card_file(file, entity_id=entity_id, existing_ids=existing_ids)
    except ValueError as e:
        _fail(str(e), json_output)

    # Create system proposal and apply through pipeline
    rel_path = f"character/{entity['id']}.json"
    content = json.dumps(entity, indent=2, ensure_ascii=False)

    ops = [UpsertTextOp(path=rel_path, content=content)]
    result = apply_system_proposal(
        root,
        ops,
        rationale=f"Import SillyTavern character: {entity['name']}",
        command="import",
    )

    if not result.success:
        _fail(f"Failed to apply import: {result.error}", json_output)

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "id": entity["id"],
                    "name": entity["name"],
                    "kind": entity["kind"],
                    "path": rel_path,
                    "file": str(data_dir / rel_path),
                    "tags_count": len(entity.get("tags", [])),
                    "event_id": result.event_id,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"Imported '{entity['name']}' as {get_data_dir_name(root)}/{rel_path}")
        if entity.get("tags"):
            click.echo(f"  Tags: {', '.join(entity['tags'][:10])}")
            if len(entity["tags"]) > 10:
                click.echo(f"  ... and {len(entity['tags']) - 10} more")
        click.echo(f"  Event ID: {result.event_id}")
        click.echo("Done.")


def _fail(message: str, json_output: bool) -> None:
    """Print error and exit with code 1."""
    if json_output:
        click.echo(json.dumps({"success": False, "error": message}, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)
    sys.exit(1)

