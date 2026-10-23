"""Index command for NeonRP CLI."""

import json
import sys

import click

from neonrp.core.config import load_config
from neonrp.core.embedding import VectorIndex, get_embedding_adapter
from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.paths import get_manifest_path, get_neonrp_dir, get_project_root


@click.group()
def index():
    """Manage entity index in manifest."""
    pass


@index.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def build(as_json: bool) -> None:
    """Full rebuild of entity index from game/ directory."""
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        if as_json:
            click.echo(json.dumps({"error": "Not initialized", "code": "not_initialized"}, ensure_ascii=False))
        else:
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
        sys.exit(1)

    manifest, stats, warnings = refresh_manifest_index(root, full_rebuild=True)

    embedding_result = {"enabled": False, "indexed": 0, "error": None}
    config = load_config(root)
    if config.embedding.enabled:
        embedding_result["enabled"] = True
        try:
            adapter = get_embedding_adapter(config.embedding)
            index_path = get_neonrp_dir(root) / "embeddings.json"
            vector_index = VectorIndex.load(index_path)
            indexed = vector_index.refresh(manifest.entities, root, adapter)
            # Persist both new embeddings and stale-key pruning.
            vector_index.save(index_path)
            embedding_result["indexed"] = indexed
        except Exception as exc:
            embedding_result["error"] = str(exc)

    # Output
    stats["warnings"] = len(warnings)

    if as_json:
        output = {
            "ok": True,
            "stats": stats,
            "warnings": [w.to_dict() for w in warnings],
            "embeddings": embedding_result,
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        click.echo(f"Index built: {stats['total']} entities indexed.")
        if embedding_result["enabled"]:
            if embedding_result["error"]:
                click.echo(f"Embeddings: failed ({embedding_result['error']})")
            else:
                click.echo(f"Embeddings: indexed {embedding_result['indexed']} entity vector(s).")
        if warnings:
            click.echo(f"Warnings ({len(warnings)}):")
            for w in warnings:
                click.echo(f"  [{w.layer}] {w.file}: {w.message}")


@index.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update(as_json: bool) -> None:
    """Incremental update of entity index (only changed files)."""
    root = get_project_root()
    manifest_path = get_manifest_path(root)

    if not manifest_path.exists():
        if as_json:
            click.echo(json.dumps({"error": "Not initialized", "code": "not_initialized"}, ensure_ascii=False))
        else:
            click.echo("Error: Not initialized. Run 'neonrp init' first.", err=True)
        sys.exit(1)

    _, stats, warnings = refresh_manifest_index(root, full_rebuild=False)

    # Output
    if as_json:
        output = {
            "ok": True,
            "stats": stats,
            "warnings": [w.to_dict() for w in warnings],
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        click.echo(
            f"Index updated: +{stats['added']} -{stats['removed']} ~{stats['updated']} "
            f"={stats['unchanged']} (total: {stats['total']})"
        )
        if warnings:
            click.echo(f"Warnings ({len(warnings)}):")
            for w in warnings:
                click.echo(f"  [{w.layer}] {w.file}: {w.message}")
