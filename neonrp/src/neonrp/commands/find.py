"""Find command for NeonRP CLI."""

import json
import sys
from typing import List, Optional

import click

from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.manifest import EntityRecord
from neonrp.core.paths import get_manifest_path, get_project_root


def _match_keyword(record: EntityRecord, keyword: str) -> bool:
    """Check if entity matches keyword (case-insensitive)."""
    keyword = keyword.lower()

    # Check name
    if keyword in record.name.lower():
        return True

    # Check tags
    if record.tags:
        for tag in record.tags:
            if keyword in tag.lower():
                return True

    # Check summary
    if record.summary and keyword in record.summary.lower():
        return True

    # Check id
    if keyword in record.id.lower():
        return True

    return False


def _find_entities(
    entities: dict[str, EntityRecord],
    entity_id: Optional[str] = None,
    tag: Optional[str] = None,
    kind: Optional[str] = None,
    keyword: Optional[str] = None,
) -> List[EntityRecord]:
    """Filter entities based on search criteria."""
    results: List[EntityRecord] = []

    for key, record in entities.items():
        # Exact id match
        if entity_id:
            if record.id == entity_id:
                return [record]  # Exact match, return immediately
            continue

        # Tag filter
        if tag and (not record.tags or tag not in record.tags):
            continue

        # Kind filter
        if kind and record.kind != kind:
            continue

        # Keyword search
        if keyword and not _match_keyword(record, keyword):
            continue

        results.append(record)

    return results


def _format_record_human(record: EntityRecord) -> str:
    """Format entity record for human-readable output."""
    lines = [
        f"  {record.kind}:{record.id}",
        f"    Name: {record.name}",
        f"    Path: {record.path}",
    ]
    if record.tags:
        lines.append(f"    Tags: {', '.join(record.tags)}")
    if record.summary:
        lines.append(f"    Summary: {record.summary}")
    return "\n".join(lines)


def _record_to_dict(record: EntityRecord) -> dict:
    """Convert record to dictionary for JSON output."""
    return {
        "entity_key": f"{record.kind}:{record.id}",
        "id": record.id,
        "kind": record.kind,
        "name": record.name,
        "path": record.path,
        "tags": record.tags,
        "summary": record.summary,
    }


@click.command()
@click.argument("query", required=False)
@click.option("--id", "entity_id", help="Exact id match")
@click.option("--tag", help="Filter by tag")
@click.option("--kind", help="Filter by kind")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def find(
    query: Optional[str], entity_id: Optional[str], tag: Optional[str], kind: Optional[str], as_json: bool
) -> None:
    """Find entities by id, tag, kind, or keyword.

    QUERY is an optional keyword to search for in entity names, tags, and summaries.
    """
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        if as_json:
            click.echo(json.dumps({"error": "Not initialized", "code": "not_initialized"}, ensure_ascii=False))
        else:
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
        sys.exit(1)

    try:
        manifest, _, warnings = refresh_manifest_index(root, full_rebuild=False)
    except Exception as exc:
        if as_json:
            click.echo(
                json.dumps({"error": f"Failed to refresh index: {exc}", "code": "index_refresh_failed"}, ensure_ascii=False)
            )
        else:
            click.echo(f"Error: Failed to refresh index: {exc}", err=True)
        sys.exit(2)

    # Find entities
    results = _find_entities(
        manifest.entities,
        entity_id=entity_id,
        tag=tag,
        kind=kind,
        keyword=query,
    )

    # Output
    if as_json:
        output = {
            "count": len(results),
            "warnings": len(warnings),
            "results": [_record_to_dict(r) for r in results],
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if results:
            click.echo(f"Found {len(results)} result(s):\n")
            for record in results:
                click.echo(_format_record_human(record))
                click.echo()
        else:
            click.echo("No results found.")
