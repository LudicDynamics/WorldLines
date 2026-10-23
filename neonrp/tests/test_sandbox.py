"""Tests for sandbox commands."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli


class TestSandboxNew:
    def test_sandbox_new_requires_from(self, tmp_path: Path, monkeypatch):
        """--from is required."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["sandbox", "new", "test"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_sandbox_new_from_missing_save(self, tmp_path: Path, monkeypatch):
        """Should fail if save doesn't exist."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["sandbox", "new", "test", "--from", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_sandbox_new_from_old_save(self, tmp_path: Path, monkeypatch):
        """Should fail for saves without meta.json."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        # Create game content
        result = runner.invoke(cli, ["game", "new"])
        assert result.exit_code == 0

        # Create an old-format save (no meta.json)
        save_dir = tmp_path / ".neonrp" / "saves" / "old-save"
        save_dir.mkdir(parents=True)
        (save_dir / "game").mkdir()
        (save_dir / "game" / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        result = runner.invoke(cli, ["sandbox", "new", "test", "--from", "old-save"])
        assert result.exit_code == 1
        assert "meta.json" in result.output

    def test_sandbox_new_success(self, tmp_path: Path, monkeypatch):
        """Successfully create a sandbox from a save."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["game", "new"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["save", "my-save"])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["sandbox", "new", "test-sandbox", "--from", "my-save"])
        assert result.exit_code == 0
        assert "Created sandbox" in result.output
        assert "test-sandbox" in result.output

    def test_sandbox_new_json_output(self, tmp_path: Path, monkeypatch):
        """--json output format."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])

        result = runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["sandbox"] == "test-sb"

    def test_sandbox_new_cannot_name_main(self, tmp_path: Path, monkeypatch):
        """Cannot create sandbox named 'main'."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])

        result = runner.invoke(cli, ["sandbox", "new", "main", "--from", "my-save"])
        assert result.exit_code == 1
        assert "main" in result.output


class TestSandboxList:
    def test_list_initial(self, tmp_path: Path, monkeypatch):
        """List shows only main initially."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])

        result = runner.invoke(cli, ["sandbox", "list"])
        assert result.exit_code == 0
        assert "main" in result.output

    def test_list_with_sandbox(self, tmp_path: Path, monkeypatch):
        """List shows main and sandbox."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "list"])
        assert result.exit_code == 0
        assert "main" in result.output
        assert "test-sb" in result.output
        assert "sandbox" in result.output.lower()

    def test_list_json(self, tmp_path: Path, monkeypatch):
        """--json output format."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["current_branch"] == "main"
        assert len(data["branches"]) == 2


class TestSandboxSwitch:
    def test_switch_to_sandbox(self, tmp_path: Path, monkeypatch):
        """Switch to a sandbox."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "switch", "test-sb"])
        assert result.exit_code == 0
        assert "Switched to" in result.output
        assert "test-sb" in result.output
        assert "index" in result.output.lower()  # Should mention index invalidation

    def test_switch_invalidates_index(self, tmp_path: Path, monkeypatch):
        """Switching invalidates entity index."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["index", "build"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        # Verify index is populated
        manifest_path = tmp_path / ".neonrp" / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert len(manifest["entities"]) > 0

        # Switch
        runner.invoke(cli, ["sandbox", "switch", "test-sb"])

        # Index should be empty
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert len(manifest["entities"]) == 0

    def test_switch_nonexistent(self, tmp_path: Path, monkeypatch):
        """Switch to nonexistent branch fails."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])

        result = runner.invoke(cli, ["sandbox", "switch", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_switch_json(self, tmp_path: Path, monkeypatch):
        """--json output format."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "switch", "test-sb", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["branch"] == "test-sb"
        assert data["index_invalidated"] is True


class TestSandboxPathTraversal:
    """Path traversal attacks should be rejected with no filesystem changes."""

    def _setup(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        return runner

    def test_sandbox_new_path_traversal(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "new", "../x", "--from", "my-save"])
        assert result.exit_code == 1
        # No directory should be created outside .neonrp/branches
        assert not (tmp_path / "x").exists()

    def test_sandbox_new_dotdot_embedded(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "new", "a..b", "--from", "my-save"])
        assert result.exit_code == 1

    def test_sandbox_new_backslash(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "new", "a\\b", "--from", "my-save"])
        assert result.exit_code == 1

    def test_sandbox_new_slash(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "new", "a/b", "--from", "my-save"])
        assert result.exit_code == 1

    def test_sandbox_new_drive_letter(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "new", "C:foo", "--from", "my-save"])
        assert result.exit_code == 1

    def test_sandbox_switch_path_traversal(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "switch", "../x"])
        assert result.exit_code == 1

    def test_sandbox_drop_path_traversal(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "drop", "../x"])
        assert result.exit_code == 1

    def test_sandbox_drop_path_traversal_json(self, tmp_path: Path, monkeypatch):
        runner = self._setup(tmp_path, monkeypatch)
        result = runner.invoke(cli, ["sandbox", "drop", "../x", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False


class TestSandboxDrop:
    def test_drop_sandbox(self, tmp_path: Path, monkeypatch):
        """Drop a sandbox."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "drop", "test-sb"])
        assert result.exit_code == 0
        assert "Dropped" in result.output

        # Verify sandbox is gone
        result = runner.invoke(cli, ["sandbox", "list", "--json"])
        data = json.loads(result.output)
        assert len(data["branches"]) == 1
        assert data["branches"][0]["name"] == "main"

    def test_drop_main_fails(self, tmp_path: Path, monkeypatch):
        """Cannot drop main."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])

        result = runner.invoke(cli, ["sandbox", "drop", "main"])
        assert result.exit_code == 1
        assert "main" in result.output

    def test_drop_current_without_force(self, tmp_path: Path, monkeypatch):
        """Cannot drop current branch without --force."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save", "--switch"])

        result = runner.invoke(cli, ["sandbox", "drop", "test-sb"])
        assert result.exit_code == 1
        assert "force" in result.output.lower()

    def test_drop_current_with_force(self, tmp_path: Path, monkeypatch):
        """Can drop current branch with --force."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save", "--switch"])

        result = runner.invoke(cli, ["sandbox", "drop", "test-sb", "--force"])
        assert result.exit_code == 0
        assert "Dropped" in result.output

        # Should now be on main
        result = runner.invoke(cli, ["sandbox", "list", "--json"])
        data = json.loads(result.output)
        assert data["current_branch"] == "main"

    def test_drop_json(self, tmp_path: Path, monkeypatch):
        """--json output format."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "my-save"])
        runner.invoke(cli, ["sandbox", "new", "test-sb", "--from", "my-save"])

        result = runner.invoke(cli, ["sandbox", "drop", "test-sb", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["dropped"] == "test-sb"
