"""Retrieval module for NeonRP agents.

Provides context retrieval functionality for agents to use when preparing input.
"""

import json
import logging
from pathlib import Path
from typing import Any

from neonrp.core.config import load_config
from neonrp.core.indexing import refresh_manifest_index
from neonrp.core.manifest import EntityRecord

logger = logging.getLogger(__name__)


def _reaches_root(lgr: logging.Logger) -> bool:
    """Whether a logger can propagate to the root logger."""
    current: logging.Logger | None = lgr
    while current is not None and current.parent is not None:
        if not current.propagate:
            return False
        current = current.parent
    return True


def _warn(message: str, *args: Any) -> None:
    """Emit warning reliably even when parent loggers disable propagation."""
    logger.warning(message, *args)
    if not _reaches_root(logger):
        logging.getLogger().warning(message, *args)


# Scoring weights (same as context command)
WEIGHT_TAGS = 0.4
WEIGHT_NAME = 0.3
WEIGHT_SUMMARY = 0.15
WEIGHT_CONTENT = 0.15

# Fuzzy matching thresholds
_MAX_EDIT_DISTANCE = 2  # max Levenshtein distance for fuzzy match
_SUBSTRING_SCORE = 0.7  # score when query token is a substring of target
_MIN_TOKEN_LEN_FOR_FUZZY = 3  # skip fuzzy on very short tokens (too many false positives)


def _tokenize(text: str) -> set[str]:
    """Simple tokenization for keyword matching."""
    return set(text.lower().split())


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein (edit) distance between two strings.

    Uses standard DP approach. O(len(a) * len(b)) time and O(min(len(a), len(b))) space.
    """
    if len(a) < len(b):
        a, b = b, a  # ensure a is the longer string for space optimization
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    curr = [0] * (len(b) + 1)

    for i in range(1, len(a) + 1):
        curr[0] = i
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,      # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev

    return prev[len(b)]


def _fuzzy_token_score(query_token: str, target_tokens: set[str]) -> float:
    """Score a single query token against a set of target tokens.

    Returns a float in [0.0, 1.0]:
    - 1.0  for exact match
    - 0.7  for substring containment (query in target or target in query)
    - edit-distance-based score for near-misses (Levenshtein ≤ 2)
    - 0.0  for no match
    """
    if not target_tokens:
        return 0.0

    # Exact match — fast path
    if query_token in target_tokens:
        return 1.0

    best = 0.0
    for target in target_tokens:
        # Substring match
        if query_token in target or target in query_token:
            best = max(best, _SUBSTRING_SCORE)
            continue  # substring is already a strong signal

        # Levenshtein fuzzy match (skip very short tokens to avoid noise)
        if len(query_token) >= _MIN_TOKEN_LEN_FOR_FUZZY and len(target) >= _MIN_TOKEN_LEN_FOR_FUZZY:
            dist = _levenshtein(query_token, target)
            if dist <= _MAX_EDIT_DISTANCE:
                max_len = max(len(query_token), len(target))
                score = 1.0 - dist / max_len
                best = max(best, score)

    return best


def _fuzzy_field_score(query_tokens: set[str], field_tokens: set[str]) -> float:
    """Compute average fuzzy score of query tokens against field tokens.

    Returns the mean of per-query-token best scores against the field.
    """
    if not query_tokens or not field_tokens:
        return 0.0

    total = sum(_fuzzy_token_score(qt, field_tokens) for qt in query_tokens)
    return total / len(query_tokens)


def _compute_score(record: EntityRecord, query_tokens: set[str], root: Path) -> float:
    """Compute relevance score for an entity against query tokens.

    Uses graduated fuzzy matching instead of binary set intersection.
    Each field score is the weighted average fuzzy token score.
    """
    scores = {"tags": 0.0, "name": 0.0, "summary": 0.0, "content": 0.0}

    # Tags scoring
    if record.tags:
        tag_tokens = set(tag.lower() for tag in record.tags)
        scores["tags"] = _fuzzy_field_score(query_tokens, tag_tokens) * WEIGHT_TAGS

    # Name scoring
    name_tokens = _tokenize(record.name)
    scores["name"] = _fuzzy_field_score(query_tokens, name_tokens) * WEIGHT_NAME

    # Summary scoring
    if record.summary:
        summary_tokens = _tokenize(record.summary)
        scores["summary"] = _fuzzy_field_score(query_tokens, summary_tokens) * WEIGHT_SUMMARY

    # Content scoring (limited to avoid full file scan)
    try:
        file_path = root / record.path
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")[:1000]
            content_tokens = _tokenize(content)
            scores["content"] = _fuzzy_field_score(query_tokens, content_tokens) * WEIGHT_CONTENT
    except Exception:
        pass  # Skip content scoring on error

    return sum(scores.values())


def retrieve_context(
    root: Path,
    query: str,
    max_results: int = 10,
    embedding_config: Any | None = None,
) -> list[dict[str, Any]]:
    """Retrieve context entities for a query.

    This is the main entry point for agents to retrieve relevant entities.

    Args:
        root: Project root path
        query: Query string for context matching
        max_results: Maximum number of results to return
        embedding_config: Optional EmbeddingConfig for hybrid vector search.
            When provided and enabled, combines fuzzy and vector similarity scores.

    Returns:
        List of dicts with entity info:
        - id: entity ID
        - kind: entity kind
        - path: relative path to entity file
        - name: entity name
        - data: full entity data (loaded from JSON file)
        - score: relevance score
    """
    try:
        manifest, _, _ = refresh_manifest_index(root, full_rebuild=False)
    except FileNotFoundError:
        _warn("Entity index is empty.")
        return []
    except Exception as exc:
        _warn("Failed to refresh entity index: %s", exc)
        return []

    if not manifest.entities:
        _warn("Entity index is empty after auto-refresh.")
        return []

    # Tokenize query
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Auto-enable vector search from project config when caller does not
    # explicitly pass embedding_config.
    if embedding_config is None:
        try:
            embedding_config = load_config(root).embedding
        except Exception:
            embedding_config = None

    # --- Fuzzy scoring ---
    fuzzy_scores: dict[str, float] = {}
    entity_key_to_record: dict[str, Any] = {}

    for key, record in manifest.entities.items():
        score = _compute_score(record, query_tokens, root)
        fuzzy_scores[key] = score
        entity_key_to_record[key] = record

    # --- Vector scoring (opt-in) ---
    vector_scores: dict[str, float] = {}
    vector_weight = 0.0

    if embedding_config and getattr(embedding_config, "enabled", False):
        try:
            from neonrp.core.embedding import VectorIndex, get_embedding_adapter
            from neonrp.core.paths import get_neonrp_dir

            vector_weight = getattr(embedding_config, "vector_weight", 0.4)
            adapter = get_embedding_adapter(embedding_config)

            index_path = get_neonrp_dir(root) / "embeddings.json"
            index = VectorIndex.load(index_path)

            # Refresh only stale/new entities
            refreshed = index.refresh(manifest.entities, root, adapter)
            if refreshed > 0:
                index.save(index_path)

            # Embed the query
            query_vectors = adapter.embed([query])
            if query_vectors:
                results_vec = index.query(query_vectors[0], top_k=max_results * 2)
                for key, sim in results_vec:
                    vector_scores[key] = sim

        except Exception as exc:
            _warn("Vector search failed, falling back to fuzzy-only: %s", exc)
            vector_weight = 0.0  # disable blending

    # --- Hybrid scoring ---
    all_keys = set(fuzzy_scores.keys()) | set(vector_scores.keys())
    scored_entities: list[tuple[Any, float]] = []

    for key in all_keys:
        fuzzy = fuzzy_scores.get(key, 0.0)
        vector = vector_scores.get(key, 0.0)

        if vector_weight > 0.0:
            final_score = (1.0 - vector_weight) * fuzzy + vector_weight * vector
        else:
            final_score = fuzzy

        if final_score > 0:
            record = entity_key_to_record.get(key)
            if record:
                scored_entities.append((record, final_score))

    # Sort by score (descending), then by key for stability
    scored_entities.sort(key=lambda x: (-x[1], f"{x[0].kind}:{x[0].id}"))

    # Build result list
    results = []
    for record, score in scored_entities[:max_results]:
        # Load full entity data
        file_path = root / record.path
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        results.append(
            {
                "id": record.id,
                "kind": record.kind,
                "path": record.path,
                "name": record.name,
                "data": data,
                "score": round(score, 4),
            }
        )

    return results

