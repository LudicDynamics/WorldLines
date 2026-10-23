"""Embedding infrastructure for vector search in NeonRP.

Provides embedding adapters and a vector index for semantic similarity search
in read_context retrieval. Vector search is opt-in and requires embedding
configuration in config.json.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Embedding adapter protocol
# ---------------------------------------------------------------------------


class EmbeddingAdapter(Protocol):
    """Protocol for embedding providers."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (one per input text).
        """
        ...


# ---------------------------------------------------------------------------
# Stub adapter (for testing)
# ---------------------------------------------------------------------------


class StubEmbeddingAdapter:
    """Returns deterministic zero vectors for testing."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors of the configured dimension."""
        return [[0.0] * self.dimensions for _ in texts]


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter
# ---------------------------------------------------------------------------


class OpenAIEmbeddingAdapter:
    """Embedding adapter using the OpenAI embeddings API.

    Works with any OpenAI-compatible endpoint (e.g., local Ollama, Azure,
    vLLM, etc.) by setting base_url.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 256,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model
        self.dimensions = dimensions
        self.api_key = api_key
        self.base_url = base_url

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Call the OpenAI embeddings API."""
        try:
            from openai import OpenAI  # lazy import
        except ImportError:
            raise RuntimeError("openai package is required for embedding. Install with: pip install openai")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.embeddings.create(
            input=texts,
            model=self.model,
            dimensions=self.dimensions,
        )
        return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def _resolve_api_key(api_key: str | None, api_key_env: str | None) -> str | None:
    """Resolve API key from direct value or environment variable."""
    if api_key:
        return api_key
    if api_key_env:
        return os.environ.get(api_key_env)
    # Fallback to standard env vars
    return os.environ.get("OPENAI_API_KEY")


def get_embedding_adapter(config: Any) -> EmbeddingAdapter:
    """Factory function to create the appropriate embedding adapter.

    Args:
        config: EmbeddingConfig from config.py

    Returns:
        EmbeddingAdapter instance
    """
    provider = config.provider or "openai"

    if provider == "stub":
        return StubEmbeddingAdapter(dimensions=config.dimensions)

    if provider in ("openai", "glm", "gemini"):
        api_key = _resolve_api_key(config.api_key, config.api_key_env)
        return OpenAIEmbeddingAdapter(
            model=config.model,
            dimensions=config.dimensions,
            api_key=api_key,
            base_url=config.base_url,
        )

    raise ValueError(f"Unsupported embedding provider: {provider}")


# ---------------------------------------------------------------------------
# Vector index
# ---------------------------------------------------------------------------


@dataclass
class VectorEntry:
    """A single entity's embedding with its content hash for staleness detection."""

    hash: str
    vector: list[float]


@dataclass
class VectorIndex:
    """In-memory vector index backed by a JSON file.

    Stores entity embeddings and provides cosine similarity search.
    The index is persisted to .neonrp/embeddings.json and only
    re-embeds entities whose content hash has changed.
    """

    entries: dict[str, VectorEntry] = field(default_factory=dict)

    # -- Persistence ---

    @classmethod
    def load(cls, path: Path) -> VectorIndex:
        """Load index from a JSON file, returning empty index on failure."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = {}
            for key, val in data.items():
                if isinstance(val, dict) and "hash" in val and "vector" in val:
                    entries[key] = VectorEntry(hash=val["hash"], vector=val["vector"])
            return cls(entries=entries)
        except Exception as exc:
            logger.warning("Failed to load embedding index: %s", exc)
            return cls()

    def save(self, path: Path) -> None:
        """Save index to a JSON file."""
        data = {key: {"hash": entry.hash, "vector": entry.vector} for key, entry in self.entries.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    # -- Refresh ---

    def _entity_text(self, entity_data: dict[str, Any]) -> str:
        """Build a single text string from entity data for embedding."""
        parts = []
        if entity_data.get("name"):
            parts.append(entity_data["name"])
        if entity_data.get("summary"):
            parts.append(entity_data["summary"])
        tags = entity_data.get("tags")
        if tags:
            parts.append("Tags: " + ", ".join(tags))
        return ". ".join(parts) if parts else ""

    def refresh(
        self,
        entities: dict[str, Any],
        root: Path,
        adapter: EmbeddingAdapter,
    ) -> int:
        """Re-embed entities whose content hash has changed.

        Args:
            entities: Dict of entity_key → EntityRecord.
            root: Project root path.
            adapter: Embedding adapter to use.

        Returns:
            Number of entities re-embedded.
        """
        # Determine which entities need (re-)embedding
        to_embed: list[tuple[str, str]] = []  # (entity_key, text)
        for key, record in entities.items():
            existing = self.entries.get(key)
            if existing and existing.hash == record.hash:
                continue  # up-to-date

            # Load entity data for text extraction
            try:
                file_path = root / record.path
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"name": record.name, "summary": record.summary, "tags": record.tags}

            text = self._entity_text(data)
            if text:
                to_embed.append((key, text))

        if not to_embed:
            return 0

        # Batch embed
        keys = [k for k, _ in to_embed]
        texts = [t for _, t in to_embed]

        try:
            vectors = adapter.embed(texts)
        except Exception as exc:
            logger.warning("Embedding API call failed: %s", exc)
            return 0

        # Update index
        for key, vector, record_key in zip(keys, vectors, keys):
            record = entities[record_key]
            self.entries[key] = VectorEntry(hash=record.hash, vector=vector)

        # Remove entries for entities that no longer exist
        stale_keys = set(self.entries.keys()) - set(entities.keys())
        for key in stale_keys:
            del self.entries[key]

        return len(keys)

    # -- Query ---

    def query(self, query_vector: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """Find the top-k most similar entities by cosine similarity.

        Args:
            query_vector: The embedding of the query text.
            top_k: Maximum number of results.

        Returns:
            List of (entity_key, similarity_score) sorted by descending score.
        """
        results: list[tuple[str, float]] = []

        for key, entry in self.entries.items():
            sim = _cosine_similarity(query_vector, entry.vector)
            if sim > 0.0:
                results.append((key, sim))

        results.sort(key=lambda x: -x[1])
        return results[:top_k]


# ---------------------------------------------------------------------------
# Math utilities
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns 0.0 if either vector has zero magnitude.
    """
    if len(a) != len(b):
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    return dot / (mag_a * mag_b)
