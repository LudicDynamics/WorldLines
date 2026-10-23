"""Tests for indexing core and CLI."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.indexing import (
    compute_file_hash,
    entity_key,
    refresh_manifest_index,
    records_to_map,
    scan_entities,
    update_entities,
)
from neonrp.core.manifest import EntityRecord, Manifest
from neonrp.core.paths import get_manifest_path


class TestIndexingCore:
    """Unit tests for indexing core module."""

    def test_entity_key(self):
        """Should generate correct entity key."""
        assert entity_key("town", "tokyo") == "town:tokyo"
        assert entity_key("character", "hero") == "character:hero"

    def test_compute_file_hash(self, tmp_path: Path):
        """Should compute SHA256 hash of file."""
        f = tmp_path / "test.json"
        f.write_text('{"id": "test"}', encoding="utf-8")
        h = compute_file_hash(f)
        assert h.startswith("sha256:")
        assert len(h) == 71  # sha256: + 64 hex chars

    def test_scan_entities_empty(self, tmp_path: Path):
        """Should return empty list for empty world."""
        records, warnings = scan_entities(tmp_path)
        assert len(records) == 0
        assert len(warnings) == 0

    def test_scan_entities_valid(self, tmp_path: Path):
        """Should index valid entity."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "tags": ["capital"]}
        (game_dir / "tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

        records, warnings = scan_entities(tmp_path)

        assert len(records) == 1
        assert len(warnings) == 0
        assert records[0].id == "tokyo"
        assert records[0].kind == "town"
        assert records[0].tags == ["capital"]

    def test_scan_entities_nested_subfolder(self, tmp_path: Path):
        """Should index an entity nested in sub-folders under its kind.

        game/items/weapons/sword.json -> kind from first folder (items), id from
        filename (sword). Sub-folders between <kind> and the file are pure
        organization and must NOT block indexing (was rejected by len(parts)==3).
        """
        nested_dir = tmp_path / "game" / "items" / "weapons"
        nested_dir.mkdir(parents=True)
        entity = {"id": "sword", "kind": "items", "name": "Sword", "tags": ["weapon"]}
        (nested_dir / "sword.json").write_text(json.dumps(entity), encoding="utf-8")

        records, warnings = scan_entities(tmp_path)

        assert len(warnings) == 0, [w.message for w in warnings]
        assert len(records) == 1
        rec = records[0]
        assert rec.id == "sword"
        assert rec.kind == "items"
        # The record keeps the real nested path so retrieval/embedding read the
        # right file downstream.
        assert rec.path == "game/items/weapons/sword.json"

    def test_scan_entities_deeply_nested(self, tmp_path: Path):
        """Arbitrary depth is allowed, not just one sub-level."""
        deep_dir = tmp_path / "game" / "items" / "weapons" / "rare" / "legendary"
        deep_dir.mkdir(parents=True)
        entity = {"id": "excalibur", "kind": "items", "name": "Excalibur"}
        (deep_dir / "excalibur.json").write_text(json.dumps(entity), encoding="utf-8")

        records, warnings = scan_entities(tmp_path)

        assert len(warnings) == 0, [w.message for w in warnings]
        assert len(records) == 1
        assert records[0].id == "excalibur"
        assert records[0].path == "game/items/weapons/rare/legendary/excalibur.json"

    def test_scan_entities_partial_failure(self, tmp_path: Path):
        """Should index valid entities while returning warnings for invalid."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)

        # Valid entity
        valid = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
        (game_dir / "tokyo.json").write_text(json.dumps(valid), encoding="utf-8")

        # Invalid entity (missing name)
        invalid = {"id": "osaka", "kind": "town"}
        (game_dir / "osaka.json").write_text(json.dumps(invalid), encoding="utf-8")

        records, warnings = scan_entities(tmp_path)

        assert len(records) == 1
        assert records[0].id == "tokyo"
        assert len(warnings) > 0
        assert any(w.file == "game/town/osaka.json" for w in warnings)

    def test_scan_entities_invalid_json(self, tmp_path: Path):
        """Should skip files with invalid JSON and return warning."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        (game_dir / "bad.json").write_text("{invalid json", encoding="utf-8")

        records, warnings = scan_entities(tmp_path)

        assert len(records) == 0
        assert len(warnings) == 1
        assert warnings[0].code == "json"

    def test_records_to_map(self):
        """Should convert records list to map."""
        records = [
            EntityRecord(
                id="tokyo", kind="town", name="Tokyo", path="game/town/tokyo.json", mtime=0.0, hash="sha256:abc"
            ),
            EntityRecord(
                id="hero", kind="character", name="Hero", path="game/character/hero.json", mtime=0.0, hash="sha256:def"
            ),
        ]
        m = records_to_map(records)

        assert "town:tokyo" in m
        assert "character:hero" in m
        assert m["town:tokyo"].name == "Tokyo"

    def test_update_entities_add(self):
        """Should add new entities."""
        existing = {}
        records = [
            EntityRecord(
                id="tokyo", kind="town", name="Tokyo", path="game/town/tokyo.json", mtime=1.0, hash="sha256:abc"
            )
        ]

        updated, stats = update_entities(existing, records)

        assert "town:tokyo" in updated
        assert stats["added"] == 1
        assert stats["updated"] == 0
        assert stats["removed"] == 0

    def test_update_entities_remove(self):
        """Should remove deleted entities."""
        existing = {
            "town:tokyo": EntityRecord(
                id="tokyo", kind="town", name="Tokyo", path="game/town/tokyo.json", mtime=1.0, hash="sha256:abc"
            )
        }
        records = []  # Entity was deleted

        updated, stats = update_entities(existing, records)

        assert "town:tokyo" not in updated
        assert stats["removed"] == 1

    def test_update_entities_unchanged(self):
        """Should keep unchanged entities."""
        record = EntityRecord(
            id="tokyo", kind="town", name="Tokyo", path="game/town/tokyo.json", mtime=1.0, hash="sha256:abc"
        )
        existing = {"town:tokyo": record}
        records = [record]

        updated, stats = update_entities(existing, records)

        assert "town:tokyo" in updated
        assert stats["unchanged"] == 1

    def test_refresh_manifest_index_auto_updates_stale_entities(self, tmp_path: Path):
        """refresh_manifest_index should repopulate manifest.entities from world files."""
        manifest = Manifest()
        manifest_path = get_manifest_path(tmp_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest.model_dump(), default=str), encoding="utf-8")

        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        (game_dir / "tokyo.json").write_text(
            json.dumps({"id": "tokyo", "kind": "town", "name": "Tokyo"}),
            encoding="utf-8",
        )

        refreshed, stats, warnings = refresh_manifest_index(tmp_path)
        assert "town:tokyo" in refreshed.entities
        assert stats["added"] == 1
        assert not warnings

    def test_refresh_manifest_index_requires_manifest(self, tmp_path: Path):
        """refresh_manifest_index should fail on uninitialized project."""
        with pytest.raises(FileNotFoundError):
            refresh_manifest_index(tmp_path)


class TestIndexCLI:
    """CLI integration tests for index command."""

    def test_index_build_no_init(self, tmp_path: Path):
        """Should error when project not initialized."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["index", "build"])
            assert result.exit_code == 1

    def test_index_build_success(self, tmp_path: Path):
        """Should build index successfully."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize project
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Create entity
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            # Build index
            result = runner.invoke(cli, ["index", "build"])
            assert result.exit_code == 0
            assert "1 entities indexed" in result.output

            # Verify manifest updated
            manifest = json.loads(Path(".neonrp/manifest.json").read_text(encoding="utf-8"))
            assert "town:tokyo" in manifest["entities"]

    def test_index_build_json(self, tmp_path: Path):
        """Should output JSON format."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            result = runner.invoke(cli, ["index", "build", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ok"] is True
            assert data["stats"]["total"] == 1

    def test_index_build_precomputes_embeddings_when_enabled(self, tmp_path: Path):
        """index build should precompute embeddings by default when embedding.enabled=true."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "summary": "Neon city"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            # Enable embeddings using stub adapter in project config.
            Path(".neonrp/config.json").write_text(
                json.dumps({"embedding": {"enabled": True, "provider": "stub", "dimensions": 8}}),
                encoding="utf-8",
            )

            result = runner.invoke(cli, ["index", "build", "--json"])
            assert result.exit_code == 0, result.output

            data = json.loads(result.output)
            assert data["embeddings"]["enabled"] is True
            assert data["embeddings"]["error"] is None

            embeddings_path = Path(".neonrp/embeddings.json")
            assert embeddings_path.exists()
            payload = json.loads(embeddings_path.read_text(encoding="utf-8"))
            assert "town:tokyo" in payload
            assert len(payload["town:tokyo"]["vector"]) == 8

    def test_index_update_incremental(self, tmp_path: Path):
        """Should update only changed entities."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)

            # Create initial entity
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            # Add new entity
            entity2 = {"id": "osaka", "kind": "town", "name": "Osaka"}
            Path("game/town/osaka.json").write_text(json.dumps(entity2), encoding="utf-8")

            # Update index
            result = runner.invoke(cli, ["index", "update", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["stats"]["added"] == 1
            assert data["stats"]["unchanged"] == 1

