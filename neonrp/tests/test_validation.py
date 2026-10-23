"""Tests for validation core and CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.validation import load_schema, validate_game_data


class TestValidationCore:
    """Unit tests for validation core module."""

    def test_load_schema_builtin(self, tmp_path: Path):
        """Should load built-in schema when project schema doesn't exist."""
        schema = load_schema(tmp_path)
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert "id" in schema["required"]
        assert "kind" in schema["required"]
        assert "name" in schema["required"]

    def test_load_schema_rules_dir_override(self, tmp_path: Path):
        """Should prefer rules/ schema override over built-in."""
        schema_dir = tmp_path / "rules"
        schema_dir.mkdir(parents=True)
        custom_schema = {"$schema": "http://json-schema.org/draft-07/schema#", "custom": True}
        (schema_dir / "game_entity.schema.json").write_text(json.dumps(custom_schema), encoding="utf-8")

        schema = load_schema(tmp_path)
        assert schema.get("custom") is True

    def test_load_schema_rules_dir_override_with_different_content(self, tmp_path: Path):
        """Should load schema content from rules/ directory."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True)
        custom_schema = {"$schema": "http://json-schema.org/draft-07/schema#", "from_rules_dir": True}
        (rules_dir / "game_entity.schema.json").write_text(json.dumps(custom_schema), encoding="utf-8")

        schema = load_schema(tmp_path)
        assert schema.get("from_rules_dir") is True

    def test_validate_game_data_pass(self, tmp_path: Path):
        """Should pass validation for valid entity."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
        (game_dir / "tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

        schema = load_schema(tmp_path)
        issues, entities = validate_game_data(tmp_path, schema)

        assert len(issues) == 0
        assert len(entities) == 1
        assert entities[0]["data"]["id"] == "tokyo"

    def test_validate_game_data_schema_fail(self, tmp_path: Path):
        """Should fail on missing required field."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        entity = {"id": "tokyo", "kind": "town"}  # missing 'name'
        (game_dir / "tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

        schema = load_schema(tmp_path)
        issues, entities = validate_game_data(tmp_path, schema)

        assert len(issues) > 0
        assert any(i.code == "schema" for i in issues)

    def test_validate_game_data_constraint_id_mismatch(self, tmp_path: Path):
        """Should fail on id-filename mismatch."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        entity = {"id": "osaka", "kind": "town", "name": "Tokyo"}
        (game_dir / "tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

        schema = load_schema(tmp_path)
        issues, entities = validate_game_data(tmp_path, schema)

        assert any(i.code == "id-mismatch" for i in issues)

    def test_validate_game_data_constraint_kind_mismatch(self, tmp_path: Path):
        """Should fail on kind-path mismatch."""
        game_dir = tmp_path / "game" / "town"
        game_dir.mkdir(parents=True)
        entity = {"id": "tokyo", "kind": "city", "name": "Tokyo"}
        (game_dir / "tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

        schema = load_schema(tmp_path)
        issues, entities = validate_game_data(tmp_path, schema)

        assert any(i.code == "kind-mismatch" for i in issues)

    def test_validate_game_data_duplicate_id(self, tmp_path: Path):
        """Should fail on duplicate id across files."""
        (tmp_path / "game" / "town").mkdir(parents=True)
        (tmp_path / "game" / "city").mkdir(parents=True)

        entity1 = {"id": "tokyo", "kind": "town", "name": "Tokyo Town"}
        entity2 = {"id": "tokyo", "kind": "city", "name": "Tokyo City"}
        (tmp_path / "game" / "town" / "tokyo.json").write_text(json.dumps(entity1), encoding="utf-8")
        (tmp_path / "game" / "city" / "tokyo.json").write_text(json.dumps(entity2), encoding="utf-8")

        schema = load_schema(tmp_path)
        issues, entities = validate_game_data(tmp_path, schema)

        assert any(i.code == "id-duplicate" for i in issues)


class TestValidateCLI:
    """CLI integration tests for validate command."""

    def test_validate_no_init(self, tmp_path: Path):
        """Should still work on uninitialized project (just no world dir)."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["validate"])
            # No world dir = no files = pass
            assert result.exit_code == 0

    def test_validate_pass_human(self, tmp_path: Path):
        """Should output the playability summary on success."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            result = runner.invoke(cli, ["validate"])
            assert result.exit_code == 0
            assert "✓ playable" in result.output

    def test_validate_pass_json(self, tmp_path: Path):
        """Should output the WorldHealth JSON on success with --json flag."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            result = runner.invoke(cli, ["validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ok"] is True
            assert data["playable"] is True
            assert data["stats"]["entities"] == 1
            assert data["blockers"] == []

    def test_validate_schema_drift_warns_but_passes_json(self, tmp_path: Path):
        """Schema drift (missing name) is a warning now — the world still
        plays; only blockers (broken JSON, dup ids, dangling cast) fail."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town"}  # missing name
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            result = runner.invoke(cli, ["validate", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["ok"] is True
            assert len(data["warnings"]) > 0

    def test_validate_fail_json(self, tmp_path: Path):
        """A real blocker (unparseable JSON) fails with exit code 1."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("game/town").mkdir(parents=True)
            Path("game/town/tokyo.json").write_text('{"id": "tokyo", broken', encoding="utf-8")

            result = runner.invoke(cli, ["validate", "--json"])
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert data["ok"] is False
            assert len(data["blockers"]) > 0
            assert data["blockers"][0]["code"] == "json-parse"


