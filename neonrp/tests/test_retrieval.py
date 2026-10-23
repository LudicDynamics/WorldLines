"""Tests for core/retrieval.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neonrp.core.manifest import EntityRecord, Manifest
from neonrp.core.paths import get_manifest_path
from neonrp.core.retrieval import _compute_score, _tokenize, retrieve_context


def _write_manifest(root: Path, manifest: Manifest) -> None:
    manifest_path = get_manifest_path(root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.model_dump(), default=str), encoding="utf-8")


def _record(
    *,
    entity_id: str,
    kind: str,
    name: str,
    path: str,
    tags: list[str] | None = None,
    summary: str | None = None,
) -> EntityRecord:
    return EntityRecord(
        id=entity_id,
        kind=kind,
        name=name,
        tags=tags,
        summary=summary,
        path=path,
        mtime=1.0,
        hash="h",
    )


class TestTokenizeAndScore:
    def test_tokenize_lowercases_and_splits(self):
        assert _tokenize("Hello WORLD hello") == {"hello", "world"}

    def test_compute_score_combines_tags_name_summary_and_content(self, tmp_path: Path):
        game_file = tmp_path / "game" / "character" / "night-blade.json"
        game_file.parent.mkdir(parents=True, exist_ok=True)
        game_file.write_text("shadow", encoding="utf-8")

        record = _record(
            entity_id="night-blade",
            kind="character",
            name="Night Blade",
            tags=["Stealth", "Night"],
            summary="Silent assassin",
            path="game/character/night-blade.json",
        )

        score = _compute_score(record, {"night", "assassin", "shadow"}, tmp_path)
        # With fuzzy scoring: each field averages per-token matches
        # night matches tags["Night"] + name["Night"] (1/3 tokens each field)
        # assassin matches summary["assassin"] (1/3)
        # shadow matches content["shadow"] (1/3)
        # Score should be > 0 and reflect multi-field matching
        assert score > 0.3
        assert score < 1.0  # graduated scoring, not binary

    def test_compute_score_ignores_missing_content_file(self, tmp_path: Path):
        record = _record(
            entity_id="hero",
            kind="character",
            name="Brave Hero",
            summary="A hero",
            path="game/character/missing.json",
        )
        score = _compute_score(record, {"hero"}, tmp_path)
        assert score == pytest.approx(0.45)  # name (0.3) + summary (0.15) — exact match on single token


class TestRetrieveContext:
    def test_returns_empty_when_manifest_missing(self, tmp_path: Path):
        assert retrieve_context(tmp_path, "hero") == []

    def test_returns_empty_for_blank_query(self, tmp_path: Path):
        manifest = Manifest()
        _write_manifest(tmp_path, manifest)
        assert retrieve_context(tmp_path, "   ") == []

    def test_returns_empty_and_warns_when_manifest_has_no_entities(self, tmp_path: Path, caplog):
        manifest = Manifest()
        _write_manifest(tmp_path, manifest)

        caplog.set_level("WARNING")
        result = retrieve_context(tmp_path, "hero")
        assert result == []
        assert "Entity index is empty" in caplog.text

    def test_sorts_by_score_and_applies_limit(self, tmp_path: Path):
        a_path = tmp_path / "game" / "character" / "a.json"
        b_path = tmp_path / "game" / "item" / "b.json"
        c_path = tmp_path / "game" / "location" / "c.json"
        a_path.parent.mkdir(parents=True, exist_ok=True)
        b_path.parent.mkdir(parents=True, exist_ok=True)
        c_path.parent.mkdir(parents=True, exist_ok=True)
        a_path.write_text(
            '{"id":"a","kind":"character","name":"Alpha Hero","tags":["hero"],"summary":"heroic leader"}',
            encoding="utf-8",
        )
        b_path.write_text(
            '{"id":"b","kind":"item","name":"Blade","summary":"Sharp hero weapon"}',
            encoding="utf-8",
        )
        c_path.write_text(
            '{"id":"c","kind":"location","name":"Camp","summary":"Resting point"}',
            encoding="utf-8",
        )

        _write_manifest(tmp_path, Manifest())

        result = retrieve_context(tmp_path, "hero", max_results=2)
        assert len(result) == 2
        assert result[0]["id"] == "a"
        assert result[0]["score"] >= result[1]["score"]

    def test_invalid_entity_json_is_skipped_after_auto_refresh(self, tmp_path: Path):
        broken_path = tmp_path / "game" / "character" / "broken.json"
        broken_path.parent.mkdir(parents=True, exist_ok=True)
        broken_path.write_text("{ not json", encoding="utf-8")

        _write_manifest(tmp_path, Manifest())

        result = retrieve_context(tmp_path, "hero")
        assert result == []

    def test_auto_refreshes_manifest_index_when_entities_are_stale(self, tmp_path: Path):
        """retrieve_context should lazily refresh index and find newly added entities."""
        # Start with initialized manifest but empty/stale entities index.
        manifest = Manifest()
        _write_manifest(tmp_path, manifest)

        game_file = tmp_path / "game" / "character" / "hero.json"
        game_file.parent.mkdir(parents=True, exist_ok=True)
        game_file.write_text(
            json.dumps({"id": "hero", "kind": "character", "name": "Hero"}),
            encoding="utf-8",
        )

        result = retrieve_context(tmp_path, "hero")
        assert len(result) == 1
        assert result[0]["id"] == "hero"

    def test_auto_uses_project_embedding_config_when_enabled(self, tmp_path: Path):
        """When embedding.enabled=true in project config, retrieve_context should refresh embeddings automatically."""
        # Project config enables embeddings via stub adapter.
        cfg_path = tmp_path / ".neonrp" / "config.json"
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(
            json.dumps({"embedding": {"enabled": True, "provider": "stub", "dimensions": 8}}),
            encoding="utf-8",
        )

        _write_manifest(tmp_path, Manifest())

        game_file = tmp_path / "game" / "character" / "hero.json"
        game_file.parent.mkdir(parents=True, exist_ok=True)
        game_file.write_text(
            json.dumps({"id": "hero", "kind": "character", "name": "Hero", "summary": "A brave hero"}),
            encoding="utf-8",
        )

        result = retrieve_context(tmp_path, "hero")
        assert len(result) == 1
        assert result[0]["id"] == "hero"

        embeddings_path = tmp_path / ".neonrp" / "embeddings.json"
        assert embeddings_path.exists()
        payload = json.loads(embeddings_path.read_text(encoding="utf-8"))
        assert "character:hero" in payload
        assert len(payload["character:hero"]["vector"]) == 8
