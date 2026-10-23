"""Tests for core/state.py - UI state persistence (M6.5-T3)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.state import (
    get_state_path,
    load_ui_state,
    save_ui_state,
    get_auto_apply,
    set_auto_apply,
    DEFAULT_UI_STATE,
)


class TestStateModule:
    """Tests for state.py functions."""

    @pytest.fixture
    def initialized_project(self, tmp_path: Path):
        """Create an initialized project."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            yield Path.cwd()

    def test_get_state_path(self, initialized_project: Path):
        """get_state_path should return path to state.json."""
        path = get_state_path(initialized_project)
        assert path.name == "state.json"
        assert ".neonrp" in str(path)

    def test_load_ui_state_default(self, initialized_project: Path):
        """load_ui_state should return defaults when file doesn't exist."""
        state = load_ui_state(initialized_project)
        assert state == DEFAULT_UI_STATE
        assert state.get("auto_apply") is False

    def test_save_and_load_ui_state(self, initialized_project: Path):
        """save_ui_state -> load_ui_state roundtrip."""
        state = {"auto_apply": True, "custom_key": "value"}
        save_ui_state(initialized_project, state)

        loaded = load_ui_state(initialized_project)
        assert loaded.get("auto_apply") is True
        assert loaded.get("custom_key") == "value"

    def test_load_ui_state_corrupted(self, initialized_project: Path):
        """load_ui_state should return defaults for corrupted file."""
        state_path = get_state_path(initialized_project)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("not valid json", encoding="utf-8")

        state = load_ui_state(initialized_project)
        assert state == DEFAULT_UI_STATE

    def test_get_auto_apply_default(self, initialized_project: Path):
        """get_auto_apply should return False by default."""
        assert get_auto_apply(initialized_project) is False

    def test_set_auto_apply(self, initialized_project: Path):
        """set_auto_apply should persist the value."""
        set_auto_apply(initialized_project, True)
        assert get_auto_apply(initialized_project) is True

        set_auto_apply(initialized_project, False)
        assert get_auto_apply(initialized_project) is False
