"""Tests for embedding infrastructure and hybrid vector search."""

import json
import math
from pathlib import Path

import pytest

from neonrp.core.embedding import (
    StubEmbeddingAdapter,
    VectorEntry,
    VectorIndex,
    _cosine_similarity,
    get_embedding_adapter,
)
from neonrp.core.manifest import EntityRecord
from neonrp.core.retrieval import retrieve_context


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_different_lengths(self):
        a = [1.0, 2.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0


# ---------------------------------------------------------------------------
# StubEmbeddingAdapter
# ---------------------------------------------------------------------------

class TestStubAdapter:
    def test_returns_correct_shape(self):
        adapter = StubEmbeddingAdapter(dimensions=128)
        results = adapter.embed(["hello", "world"])
        assert len(results) == 2
        assert all(len(v) == 128 for v in results)

    def test_returns_zero_vectors(self):
        adapter = StubEmbeddingAdapter(dimensions=4)
        results = adapter.embed(["test"])
        assert results == [[0.0, 0.0, 0.0, 0.0]]


# ---------------------------------------------------------------------------
# get_embedding_adapter factory
# ---------------------------------------------------------------------------

class TestGetEmbeddingAdapter:
    def test_stub_provider(self):
        from dataclasses import dataclass

        @dataclass
        class FakeConfig:
            provider: str = "stub"
            model: str = ""
            dimensions: int = 32
            base_url: str | None = None
            api_key_env: str | None = None
            api_key: str | None = None

        adapter = get_embedding_adapter(FakeConfig())
        assert isinstance(adapter, StubEmbeddingAdapter)

    def test_unsupported_provider(self):
        from dataclasses import dataclass

        @dataclass
        class FakeConfig:
            provider: str = "nonexistent"
            model: str = ""
            dimensions: int = 32
            base_url: str | None = None
            api_key_env: str | None = None
            api_key: str | None = None

        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            get_embedding_adapter(FakeConfig())


# ---------------------------------------------------------------------------
# VectorIndex persistence
# ---------------------------------------------------------------------------

class TestVectorIndexPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        index = VectorIndex()
        index.entries["char:hero"] = VectorEntry(hash="abc", vector=[1.0, 2.0, 3.0])
        index.entries["loc:tavern"] = VectorEntry(hash="def", vector=[4.0, 5.0, 6.0])

        path = tmp_path / "embeddings.json"
        index.save(path)

        loaded = VectorIndex.load(path)
        assert len(loaded.entries) == 2
        assert loaded.entries["char:hero"].hash == "abc"
        assert loaded.entries["char:hero"].vector == [1.0, 2.0, 3.0]
        assert loaded.entries["loc:tavern"].hash == "def"

    def test_load_missing_file(self, tmp_path):
        index = VectorIndex.load(tmp_path / "nonexistent.json")
        assert len(index.entries) == 0

    def test_load_corrupt_file(self, tmp_path):
        path = tmp_path / "embeddings.json"
        path.write_text("not json", encoding="utf-8")
        index = VectorIndex.load(path)
        assert len(index.entries) == 0


# ---------------------------------------------------------------------------
# VectorIndex refresh
# ---------------------------------------------------------------------------

class _DeterministicAdapter:
    """Test adapter that returns deterministic non-zero vectors based on text hash."""

    def __init__(self, dimensions: int = 4):
        self.dimensions = dimensions
        self.call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += len(texts)
        vectors = []
        for text in texts:
            # Create a simple deterministic vector from the text
            h = hash(text.lower())
            vec = []
            for i in range(self.dimensions):
                val = ((h >> (i * 8)) & 0xFF) / 255.0
                vec.append(val)
            # Normalize so cosine sim is meaningful
            mag = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / mag for x in vec])
        return vectors


class TestVectorIndexRefresh:
    def _make_entities(self, root: Path) -> dict[str, EntityRecord]:
        """Create test entity files and records."""
        entities = {}

        for kind, eid, name, tags, summary in [
            ("character", "hero", "The Hero", ["brave", "warrior"], "A brave warrior."),
            ("location", "tavern", "The Tavern", ["pub", "social"], "A cozy tavern."),
        ]:
            kind_dir = root / "game" / kind
            kind_dir.mkdir(parents=True, exist_ok=True)
            file_path = kind_dir / f"{eid}.json"
            data = {"id": eid, "kind": kind, "name": name, "tags": tags, "summary": summary}
            file_path.write_text(json.dumps(data), encoding="utf-8")

            key = f"{kind}:{eid}"
            entities[key] = EntityRecord(
                id=eid, kind=kind, name=name, tags=tags, summary=summary,
                path=f"game/{kind}/{eid}.json", mtime=0.0, hash=f"hash_{eid}",
            )

        return entities

    def test_embeds_new_entities(self, tmp_path):
        entities = self._make_entities(tmp_path)
        adapter = _DeterministicAdapter()
        index = VectorIndex()

        count = index.refresh(entities, tmp_path, adapter)
        assert count == 2
        assert len(index.entries) == 2
        assert adapter.call_count == 2

    def test_skips_unchanged_entities(self, tmp_path):
        entities = self._make_entities(tmp_path)
        adapter = _DeterministicAdapter()

        index = VectorIndex()
        index.refresh(entities, tmp_path, adapter)
        initial_count = adapter.call_count

        # Refresh again — nothing changed
        count = index.refresh(entities, tmp_path, adapter)
        assert count == 0
        assert adapter.call_count == initial_count  # no new API calls

    def test_re_embeds_changed_entity(self, tmp_path):
        entities = self._make_entities(tmp_path)
        adapter = _DeterministicAdapter()

        index = VectorIndex()
        index.refresh(entities, tmp_path, adapter)

        # Change the hero's hash (simulating content change)
        entities["character:hero"] = EntityRecord(
            id="hero", kind="character", name="The Hero V2",
            tags=["brave"], summary="Updated hero.",
            path="game/character/hero.json", mtime=1.0, hash="hash_hero_v2",
        )

        count = index.refresh(entities, tmp_path, adapter)
        assert count == 1  # only hero re-embedded


# ---------------------------------------------------------------------------
# VectorIndex query
# ---------------------------------------------------------------------------

class TestVectorIndexQuery:
    def test_returns_sorted_results(self):
        index = VectorIndex()
        # Create entries with known vectors
        index.entries["a"] = VectorEntry(hash="h1", vector=[1.0, 0.0, 0.0])
        index.entries["b"] = VectorEntry(hash="h2", vector=[0.7, 0.7, 0.0])
        index.entries["c"] = VectorEntry(hash="h3", vector=[0.0, 0.0, 1.0])

        # Query with [1, 0, 0] — "a" should be most similar
        results = index.query([1.0, 0.0, 0.0], top_k=3)
        assert len(results) >= 1
        assert results[0][0] == "a"
        assert results[0][1] == pytest.approx(1.0)

    def test_top_k_limits_results(self):
        index = VectorIndex()
        for i in range(10):
            index.entries[f"e{i}"] = VectorEntry(hash=f"h{i}", vector=[float(i), 1.0])
        results = index.query([5.0, 1.0], top_k=3)
        assert len(results) <= 3

    def test_empty_index(self):
        index = VectorIndex()
        results = index.query([1.0, 0.0], top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# Hybrid scoring integration (using stub adapter)
# ---------------------------------------------------------------------------

class TestHybridRetrieval:
    """Integration tests for retrieve_context with hybrid scoring."""

    @pytest.fixture
    def project_with_entities(self, tmp_path):
        """Set up a minimal NeonRP project with entities."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()

        manifest = {
            "version": "0.3",
            "created": "2025-01-01T00:00:00+00:00",
            "current_branch": "main",
            "branches": {"main": {"head_event": -1, "created": "2025-01-01T00:00:00+00:00", "kind": "main"}},
            "entities": {},
        }

        game_dir = tmp_path / "game"
        for entity in [
            {"id": "hero", "kind": "character", "name": "Hero", "tags": ["brave"], "summary": "A brave warrior."},
            {"id": "villain", "kind": "character", "name": "Villain", "tags": ["evil"], "summary": "An evil mage."},
        ]:
            kind_dir = game_dir / entity["kind"]
            kind_dir.mkdir(parents=True, exist_ok=True)
            (kind_dir / f"{entity['id']}.json").write_text(json.dumps(entity), encoding="utf-8")

        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return tmp_path

    def test_without_embedding_config(self, project_with_entities):
        """No embedding config → fuzzy-only, should still work."""
        results = retrieve_context(project_with_entities, "brave")
        assert any(r["id"] == "hero" for r in results)

    def test_with_stub_embedding_config(self, project_with_entities):
        """Stub embeddings produce zero vectors, so vector scores are 0.
        Fuzzy matching should still produce results."""
        from neonrp.core.config import EmbeddingConfig

        config = EmbeddingConfig(enabled=True, provider="stub", dimensions=32, vector_weight=0.3)
        results = retrieve_context(project_with_entities, "brave", embedding_config=config)
        # Stub gives zero vectors so vector score = 0, but fuzzy score should still work
        assert any(r["id"] == "hero" for r in results)

