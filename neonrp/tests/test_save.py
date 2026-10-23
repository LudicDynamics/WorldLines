"""Tests for save/load snapshots."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.commands.save import create_save_snapshot, get_save_session_path, list_loadable_save_snapshots, load_save_snapshot
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path
from neonrp.core.session import append_user_query, get_session_path, read_session


def _init_project(tmp_path: Path) -> Path:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        return Path.cwd()


class TestSaveSnapshotSession:
    def test_create_save_snapshot_includes_current_branch_session(self, tmp_path: Path):
        root = _init_project(tmp_path)
        (root / "game" / "notes.txt").write_text("before", encoding="utf-8")
        append_user_query(root, "main", "hello from session")

        result = create_save_snapshot(root, "slot-1")

        session_snapshot = get_save_session_path(root, "slot-1")
        assert result["save_id"] == "slot-1"
        assert session_snapshot.exists()
        assert session_snapshot.read_text(encoding="utf-8") == get_session_path(root, "main").read_text(encoding="utf-8")

        meta = json.loads((root / ".neonrp" / "saves" / "slot-1" / "meta.json").read_text(encoding="utf-8"))
        assert meta["session_file"] == "session.jsonl"

    def test_load_save_snapshot_restores_branch_session(self, tmp_path: Path):
        root = _init_project(tmp_path)
        game_file = root / "game" / "notes.txt"
        game_file.write_text("before", encoding="utf-8")
        append_user_query(root, "main", "hello from session")

        create_save_snapshot(root, "slot-1")
        expected_session = get_save_session_path(root, "slot-1").read_text(encoding="utf-8")

        game_file.write_text("after", encoding="utf-8")
        append_user_query(root, "main", "this should disappear after load")
        assert len(read_session(root, "main")) == 2

        load_save_snapshot(root, "slot-1")

        assert game_file.read_text(encoding="utf-8") == "before"
        assert get_session_path(root, "main").read_text(encoding="utf-8") == expected_session
        entries = read_session(root, "main")
        assert len(entries) == 1
        assert entries[0].content == "hello from session"

    def test_load_old_snapshot_without_session_clears_branch_session(self, tmp_path: Path):
        root = _init_project(tmp_path)
        append_user_query(root, "main", "hello from session")
        create_save_snapshot(root, "slot-1")

        session_snapshot = get_save_session_path(root, "slot-1")
        session_snapshot.unlink()

        append_user_query(root, "main", "stale session that should be cleared")
        assert get_session_path(root, "main").exists()

        load_save_snapshot(root, "slot-1")

        assert get_session_path(root, "main").exists() is False

    def test_conversation_resume_refreshes_branch_before_reading_session(self, tmp_path: Path):
        from neonrp.core.conversation import ConversationSession
        from neonrp.core.manifest import BranchMetadata

        root = _init_project(tmp_path)
        append_user_query(root, "main", "main-session")

        manifest_path = get_manifest_path(root)
        manifest = Manifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
        manifest.branches["side"] = BranchMetadata()
        manifest.current_branch = "side"
        manifest_path.write_text(json.dumps(manifest.model_dump(), ensure_ascii=False), encoding="utf-8")

        append_user_query(root, "side", "side-session")

        session = ConversationSession(root=root, agent_id="test-agent", mode="build")
        session.branch = "main"

        loaded = session.resume()

        assert loaded == 1
        assert session.branch == "side"
        assert session.messages[0].content == "side-session"


class TestLoadSnapshotListing:
    def test_list_loadable_save_snapshots_returns_only_valid_saves(self, tmp_path: Path):
        root = _init_project(tmp_path)
        (root / "game" / "notes.txt").write_text("before", encoding="utf-8")

        create_save_snapshot(root, "slot-a")
        invalid_dir = root / ".neonrp" / "saves" / "broken-save"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "meta.json").write_text("{not-json", encoding="utf-8")

        snapshots = list_loadable_save_snapshots(root)

        assert [snapshot["save_id"] for snapshot in snapshots] == ["slot-a"]

    def test_cli_load_without_snapshot_lists_available_saves(self, tmp_path: Path, monkeypatch):
        root = _init_project(tmp_path)
        (root / "game" / "notes.txt").write_text("before", encoding="utf-8")
        create_save_snapshot(root, "slot-a")
        create_save_snapshot(root, "slot-b")

        runner = CliRunner()
        monkeypatch.chdir(root)
        result = runner.invoke(cli, ["load"])

        assert result.exit_code == 0
        assert "Loadable snapshots: 2" in result.output
        assert "slot-a" in result.output
        assert "slot-b" in result.output
        assert "Use: neonrp load <snapshot_id>" in result.output
