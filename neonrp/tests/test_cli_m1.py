"""Tests for find and context CLI commands."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli


class TestFindCLI:
    """CLI integration tests for find command."""

    def test_find_no_init(self, tmp_path: Path):
        """Should error when project not initialized."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["find", "--id", "test"])
            assert result.exit_code == 1

    def test_find_empty_index(self, tmp_path: Path):
        """Should return no results when world has no entities."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["find", "test"])
            assert result.exit_code == 0
            assert "no results found" in result.output.lower()

    def test_find_auto_refreshes_index(self, tmp_path: Path):
        """find should auto-refresh stale index and discover new world entities."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            # No manual `index build` here.
            result = runner.invoke(cli, ["find", "--id", "tokyo"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_find_by_id(self, tmp_path: Path):
        """Should find entity by exact id."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["find", "--id", "tokyo"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_find_by_tag(self, tmp_path: Path):
        """Should filter entities by tag."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "tags": ["capital"]}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["find", "--tag", "capital"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_find_by_kind(self, tmp_path: Path):
        """Should filter entities by kind."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["find", "--kind", "town"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_find_keyword(self, tmp_path: Path):
        """Should find entities by keyword."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo City"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["find", "City"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_find_json(self, tmp_path: Path):
        """Should output JSON format."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo"}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["find", "--id", "tokyo", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["count"] == 1
            assert data["results"][0]["id"] == "tokyo"


class TestContextCLI:
    """CLI integration tests for context command."""

    def test_context_no_init(self, tmp_path: Path):
        """Should error when project not initialized."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["context", "test"])
            assert result.exit_code == 1

    def test_context_empty_index(self, tmp_path: Path):
        """Should return empty context when world has no entities."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["context", "test"])
            assert result.exit_code == 0
            assert "no relevant context found" in result.output.lower()

    def test_context_auto_refreshes_index(self, tmp_path: Path):
        """context should auto-refresh stale index and rank new entities."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "tags": ["capital", "neon"]}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")

            # No manual `index build` here.
            result = runner.invoke(cli, ["context", "neon"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()

    def test_context_basic(self, tmp_path: Path):
        """Should return ranked context."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "tags": ["capital", "neon"]}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["context", "neon"])
            assert result.exit_code == 0
            assert "tokyo" in result.output.lower()
            assert "score" in result.output.lower()

    def test_context_limit(self, tmp_path: Path):
        """Should respect --limit option."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            for i in range(5):
                entity = {"id": f"city{i}", "kind": "town", "name": f"City {i}"}
                Path(f"game/town/city{i}.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["context", "city", "--limit", "2", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["count"] == 2

    def test_context_json_score_breakdown(self, tmp_path: Path):
        """Should include score breakdown in JSON output."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "tags": ["capital"]}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["context", "capital", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["results"]) > 0
            assert "score_breakdown" in data["results"][0]
            assert "tags" in data["results"][0]["score_breakdown"]

    def test_context_snippet(self, tmp_path: Path):
        """Should include snippets in results."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True)
            entity = {"id": "tokyo", "kind": "town", "name": "Tokyo", "summary": "A neon city."}
            Path("game/town/tokyo.json").write_text(json.dumps(entity), encoding="utf-8")
            runner.invoke(cli, ["index", "build"])

            result = runner.invoke(cli, ["context", "neon", "--json"])
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data["results"]) > 0
            assert data["results"][0]["snippet"] == "A neon city."
