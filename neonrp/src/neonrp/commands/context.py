"""Context command for NeonRP CLI."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import click

from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.manifest import EntityRecord
from neonrp.core.paths import get_manifest_path, get_project_root

# Scoring weights (as per M1 design)
WEIGHT_TAGS = 0.4
WEIGHT_NAME = 0.3
WEIGHT_SUMMARY = 0.15
WEIGHT_CONTENT = 0.15

SNIPPET_MAX_LENGTH = 200


@dataclass
class ScoredEntity:
    """Entity with relevance score and breakdown."""

    record: EntityRecord
    score: float
    score_breakdown: dict


def _tokenize(text: str) -> set[str]:
    """Simple tokenization for keyword matching."""
    return set(text.lower().split())


def _compute_score(record: EntityRecord, query_tokens: set[str], root: Path) -> ScoredEntity:
    """Compute relevance score for an entity against query tokens."""
    scores = {"tags": 0.0, "name": 0.0, "summary": 0.0, "content": 0.0}

    # Tags scoring
    if record.tags:
        tag_tokens = set(tag.lower() for tag in record.tags)
        if query_tokens & tag_tokens:
            scores["tags"] = WEIGHT_TAGS

    # Name scoring
    name_tokens = _tokenize(record.name)
    if query_tokens & name_tokens:
        scores["name"] = WEIGHT_NAME

    # Summary scoring
    if record.summary:
        summary_tokens = _tokenize(record.summary)
        if query_tokens & summary_tokens:
            scores["summary"] = WEIGHT_SUMMARY

    # Content scoring (limited to avoid full file scan)
    try:
        file_path = root / record.path
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")[:1000]  # Limit to first 1KB
            content_tokens = _tokenize(content)
            if query_tokens & content_tokens:
                scores["content"] = WEIGHT_CONTENT
    except Exception:
        pass  # Skip content scoring on error

    total = sum(scores.values())

    return ScoredEntity(record=record, score=total, score_breakdown=scores)


def _get_snippet(record: EntityRecord, root: Path) -> str:
    """Get snippet for entity: prefer summary, fallback to file content."""
    if record.summary:
        return record.summary[:SNIPPET_MAX_LENGTH]

    try:
        file_path = root / record.path
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            if len(content) > SNIPPET_MAX_LENGTH:
                return content[: SNIPPET_MAX_LENGTH - 3] + "..."
            return content
    except Exception:
        pass

    return ""


def _rank_entities(entities: dict[str, EntityRecord], query: str, root: Path, limit: int) -> List[ScoredEntity]:
    """Rank entities by relevance to query."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: List[ScoredEntity] = []
    for record in entities.values():
        result = _compute_score(record, query_tokens, root)
        if result.score > 0:
            scored.append(result)

    # Sort by score (descending), then by entity_key (ascending) for stability
    scored.sort(key=lambda x: (-x.score, f"{x.record.kind}:{x.record.id}"))

    return scored[:limit]


def _format_result_human(se: ScoredEntity, snippet: str) -> str:
    """Format scored entity for human-readable output."""
    lines = [
        f"  {se.record.kind}:{se.record.id} (score: {se.score:.2f})",
        f"    Name: {se.record.name}",
        f"    Path: {se.record.path}",
    ]
    if se.record.tags:
        lines.append(f"    Tags: {', '.join(se.record.tags)}")
    if snippet:
        lines.append(f"    Snippet: {snippet}")
    return "\n".join(lines)


def _result_to_dict(se: ScoredEntity, snippet: str) -> dict:
    """Convert scored entity to dictionary for JSON output."""
    return {
        "entity_key": f"{se.record.kind}:{se.record.id}",
        "path": se.record.path,
        "name": se.record.name,
        "snippet": snippet,
        "score": round(se.score, 4),
        "score_breakdown": {k: round(v, 4) for k, v in se.score_breakdown.items()},
    }


@click.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Maximum number of results")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def context(query: str, limit: int, as_json: bool) -> None:
    """Find relevant context for a query.

    Returns top-N entities ranked by relevance with snippets and score breakdown.
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

    # Rank entities
    results = _rank_entities(manifest.entities, query, root, limit)

    # Output
    if as_json:
        output = {
            "query": query,
            "count": len(results),
            "warnings": len(warnings),
            "results": [_result_to_dict(se, _get_snippet(se.record, root)) for se in results],
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if results:
            click.echo(f"Context for '{query}' ({len(results)} result(s)):\n")
            for se in results:
                snippet = _get_snippet(se.record, root)
                click.echo(_format_result_human(se, snippet))
                click.echo()
        else:
            click.echo(f"No relevant context found for '{query}'.")
