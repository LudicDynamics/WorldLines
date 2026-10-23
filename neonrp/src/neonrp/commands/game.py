"""Game scaffolding commands."""

from __future__ import annotations

import json
import sys
from importlib import resources
from pathlib import Path

import click

from neonrp.core.paths import (
    DEFAULT_SCHEMA_FILENAME,
    get_data_dir_name,
    get_game_dir,
    get_manifest_path,
    get_project_root,
    get_rules_dir,
)
from neonrp.core.proposal import DeleteOp, UpsertTextOp
from neonrp.core.rules import DEFAULT_RULES_PROFILE
from neonrp.core.system_proposal import apply_system_proposal
from neonrp.core.template_assets import (
    DEFAULT_TEMPLATE_NAME,
    copy_agent_from_template,
    copy_game_support_files_from_template,
    copy_runtime_contract_from_template,
    copy_souls_and_playthrough_from_template,
    list_available_templates,
    list_template_agent_ids,
    load_game_template,
)

_ENTITY_AUTHORING_SKILL_TEMPLATE = """\
---
name: entity-authoring
description: Schema- and rules-aware workflow for creating or updating NeonRP entities. Use when adding/editing files under game/<kind>/<id>.json, fixing validation errors, or introducing new kinds/fields.
---

# Entity Authoring Workflow

Use this workflow whenever game entities are created or updated.

1. Read rules first.
2. Edit entities.
3. Re-check consistency before finishing.

# 1) Read Rules First

- Read `rules/game_entity.schema.json` if it exists.
- Read `.neonrp/config.json` and check `rules.profile_path`.
- If `rules.profile_path` is set, read that profile file too (for domain validation and `resolve_action` behavior).

# 2) Author Entities Safely

- Store entities at `game/<kind>/<id>.json`.
- Keep these aligned:
  - Path kind segment (`<kind>`)
  - Filename (`<id>.json`)
  - Entity fields: `id`, `kind`
- Always include required fields:
  - `id`
  - `kind`
  - `name`
- Keep IDs stable; avoid renaming unless required by the task.
- For references (for example `location`, `connections`, `npcs`, `items_available`), prefer existing IDs and avoid dangling links.

# 3) Consistency Checklist Before Finish

- `id` matches filename.
- `kind` matches parent folder.
- Required fields are present.
- Field types/ranges match schema definitions.
- Cross-entity references point to real entities.
- New kinds/fields are reflected in schema/rules files when needed.

# Mode Notes

- `build` / `play`: use direct file tools (`read_file`, `write_file`, `edit_file`, `glob`, `grep`) as available.
- `sandbox`: bundle game-state changes into one `submit_proposal(...)`.
- If `resolve_action` is enabled, use it for deterministic mechanics; it is read-only and does not write files.
"""


def create_rule_samples(root: Path) -> list[str]:
    """Create starter rules files under rules/ if they don't already exist."""
    created_paths: list[str] = []
    rules_dir = get_rules_dir(root)
    rules_dir.mkdir(parents=True, exist_ok=True)

    schema_path = rules_dir / DEFAULT_SCHEMA_FILENAME
    if not schema_path.exists():
        schema_text = resources.files("neonrp.schema").joinpath(DEFAULT_SCHEMA_FILENAME).read_text(encoding="utf-8")
        schema_path.write_text(schema_text, encoding="utf-8")
        created_paths.append(f"rules/{DEFAULT_SCHEMA_FILENAME}")

    profile_path = rules_dir / "domain_rules.sample.json"
    if not profile_path.exists():
        profile_path.write_text(
            json.dumps(DEFAULT_RULES_PROFILE, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        created_paths.append("rules/domain_rules.sample.json")

    readme_path = rules_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            """# Rules Folder

This folder stores project rule files.

- `game_entity.schema.json`: active JSON Schema override for game entity validation.
- `domain_rules.sample.json`: example profile for the optional data-driven domain validation and `resolve_action` layer.

To activate a custom domain profile, set `.neonrp/config.json`:

```json
{
  "rules": {
    "profile_path": "rules/domain_rules.sample.json"
  }
}
```
""",
            encoding="utf-8",
        )
        created_paths.append("rules/README.md")

    return created_paths


def create_skill_samples(root: Path) -> list[str]:
    """Create starter skill files under skills/ if they don't already exist."""
    created_paths: list[str] = []
    skill_path = root / "skills" / "entity-authoring" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    if not skill_path.exists():
        skill_path.write_text(_ENTITY_AUTHORING_SKILL_TEMPLATE, encoding="utf-8")
        created_paths.append("skills/entity-authoring/SKILL.md")
    return created_paths


@click.group()
def game() -> None:
    """Game-related commands."""
    pass


@game.command("new")
@click.option(
    "--template",
    "template_name",
    default=DEFAULT_TEMPLATE_NAME,
    show_default=True,
    help="Template name",
)
@click.option("--force", is_flag=True, help="Overwrite existing game entities")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def game_new(template_name: str, force: bool, json_output: bool) -> None:
    """Create a starter game state from a template."""
    root = get_project_root()
    manifest_path = get_manifest_path(root)
    if not manifest_path.exists():
        _fail("Not initialized. Run 'neonrp init' first.", json_output)

    game_dir = get_game_dir(root)
    existing = _list_existing_entities(game_dir)
    if existing and not force:
        _fail("Game directory already has entities. Use --force to overwrite.", json_output)

    data_dir_name = get_data_dir_name(root)
    try:
        template = load_game_template(template_name, data_dir_name)
    except (KeyError, FileNotFoundError):
        available = ", ".join(list_available_templates())
        _fail(f"Unknown template '{template_name}'. Available: {available}", json_output)
    except ValueError as exc:
        _fail(f"Invalid template '{template_name}': {exc}", json_output, code=2)

    # Build ops from template; --force also clears existing game JSON entities first.
    ops: list[DeleteOp | UpsertTextOp] = []
    created_paths: list[str] = []
    if force:
        for existing_path in existing:
            rel_existing = existing_path.relative_to(game_dir).as_posix()
            ops.append(DeleteOp(path=rel_existing))

    for rel_path, data in template:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        ops.append(UpsertTextOp(path=rel_path, content=content))
        created_paths.append(rel_path)

    # Apply through system proposal pipeline
    result = apply_system_proposal(
        root,
        ops,
        rationale=f"Create starter game state from template: {template_name}",
        command="game_new",
    )

    if not result.success:
        _fail(f"Failed to create starter game state: {result.error}", json_output, code=2)

    template_agent_ids = list_template_agent_ids(template_name)
    narrator_created = False
    created_agent_ids: list[str] = []
    for agent_id in template_agent_ids:
        agent_json_path = root / "agents" / agent_id / "agent.json"
        system_path = root / "agents" / agent_id / "system.md"
        needs_copy = force or not agent_json_path.exists() or (agent_id == "narrator" and not system_path.exists())
        if not needs_copy:
            continue
        try:
            created = copy_agent_from_template(
                root,
                template_name=template_name,
                agent_id=agent_id,
                data_dir_name=data_dir_name,
                force=True,
            )
        except FileNotFoundError as exc:
            _fail(str(exc), json_output, code=2)
        if created:
            created_paths.extend(created)
            created_agent_ids.append(agent_id)
            if agent_id == "narrator":
                narrator_created = True

    created_paths.extend(copy_runtime_contract_from_template(root, template_name=template_name, data_dir_name=data_dir_name, force=force))
    created_paths.extend(
        copy_game_support_files_from_template(
            root,
            template_name=template_name,
            data_dir_name=data_dir_name,
            force=force,
        )
    )
    created_paths.extend(
        copy_souls_and_playthrough_from_template(
            root,
            template_name=template_name,
            force=force,
        )
    )

    # Create rules examples for customization workflow.
    created_paths.extend(create_rule_samples(root))
    # Create skill samples so Skill(entity-authoring) is available immediately.
    created_paths.extend(create_skill_samples(root))

    if json_output:
        click.echo(
            json.dumps(
                {
                    "success": True,
                    "template": template_name,
                    "files": created_paths,
                    "event_id": result.event_id,
                    "narrator_created": narrator_created,
                    "agents_created": created_agent_ids,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        click.echo(f"Created starter game state ({template_name}) with {len(created_paths)} entities.")
        for rel_path in created_paths:
            click.echo(f"  - {rel_path}")
        if narrator_created:
            click.echo("  Created default narrator agent.")
        specialist_agents = [agent_id for agent_id in created_agent_ids if agent_id != "narrator"]
        if specialist_agents:
            click.echo(f"  Created template agents ({', '.join(specialist_agents)}).")
        click.echo(f"  Event ID: {result.event_id}")
        click.echo("Done.")


def _list_existing_entities(game_dir: Path) -> list[Path]:
    if not game_dir.exists():
        return []
    return [p for p in game_dir.rglob("*.json") if p.is_file()]


def _fail(message: str, json_output: bool, code: int = 1) -> None:
    if json_output:
        click.echo(json.dumps({"success": False, "error": message}, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Error: {message}", err=True)
    sys.exit(code)
