"""Tests for core/checkpoint.py - Checkpoint system for undo/redo."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.checkpoint import (
    create_checkpoint,
    restore_checkpoint,
    list_checkpoints,
    find_checkpoint_for_undo,
    find_checkpoint_for_redo,
    rotate_checkpoints,
    delete_checkpoint,
    delete_branch_checkpoints,
    get_checkpoint_path,
)


class TestCheckpointCreation:
    """Tests for checkpoint creation."""

    def test_create_checkpoint_success(self, tmp_path: Path):
        """Should create checkpoint of world directory."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Create world content
            (root / "game" / "character").mkdir(parents=True)
            (root / "game" / "character" / "hero.json").write_text('{"id": "hero"}', encoding="utf-8")

            # Create checkpoint
            checkpoint = create_checkpoint(root, "main", 0)

            assert checkpoint is not None
            assert checkpoint.branch == "main"
            assert checkpoint.event_id == 0
            assert checkpoint.path.exists()
            assert (checkpoint.path / "character" / "hero.json").exists()

    def test_create_checkpoint_no_game(self, tmp_path: Path):
        """Should return None if world doesn't exist."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Remove world
            import shutil

            shutil.rmtree(root / "game")

            checkpoint = create_checkpoint(root, "main", 0)
            assert checkpoint is None


class TestCheckpointRestoration:
    """Tests for checkpoint restoration."""

    def test_restore_checkpoint_success(self, tmp_path: Path):
        """Should restore world from checkpoint."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Create initial world content
            (root / "game" / "character").mkdir(parents=True)
            (root / "game" / "character" / "hero.json").write_text('{"id": "hero"}', encoding="utf-8")

            # Create checkpoint
            create_checkpoint(root, "main", 0)

            # Modify world
            (root / "game" / "character" / "hero.json").write_text('{"id": "modified"}', encoding="utf-8")
            (root / "game" / "character" / "villain.json").write_text('{"id": "villain"}', encoding="utf-8")

            # Restore checkpoint
            result = restore_checkpoint(root, "main", 0)

            assert result is True
            assert (root / "game" / "character" / "hero.json").read_text(encoding="utf-8") == '{"id": "hero"}'
            assert not (root / "game" / "character" / "villain.json").exists()

    def test_restore_nonexistent_checkpoint(self, tmp_path: Path):
        """Should return False for nonexistent checkpoint."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            result = restore_checkpoint(root, "main", 999)
            assert result is False


class TestCheckpointListing:
    """Tests for listing checkpoints."""

    def test_list_checkpoints_sorted(self, tmp_path: Path):
        """Should list checkpoints sorted by event_id."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            # Create checkpoints in non-sequential order
            create_checkpoint(root, "main", 2)
            create_checkpoint(root, "main", 0)
            create_checkpoint(root, "main", 1)

            checkpoints = list_checkpoints(root, "main")

            assert len(checkpoints) == 3
            assert [c.event_id for c in checkpoints] == [0, 1, 2]

    def test_list_checkpoints_empty(self, tmp_path: Path):
        """Should return empty list for no checkpoints."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            checkpoints = list_checkpoints(root, "main")
            assert checkpoints == []


class TestUndoRedoFinding:
    """Tests for finding undo/redo targets."""

    def test_find_checkpoint_for_undo(self, tmp_path: Path):
        """Should find previous checkpoint for undo."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            create_checkpoint(root, "main", 0)
            create_checkpoint(root, "main", 1)
            create_checkpoint(root, "main", 2)

            # At event 2, undo should go to 1
            target = find_checkpoint_for_undo(root, "main", 2)
            assert target == 1

            # At event 1, undo should go to 0
            target = find_checkpoint_for_undo(root, "main", 1)
            assert target == 0

            # At event 0, undo should return None
            target = find_checkpoint_for_undo(root, "main", 0)
            assert target is None

    def test_find_checkpoint_for_redo(self, tmp_path: Path):
        """Should find next checkpoint for redo."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            create_checkpoint(root, "main", 0)
            create_checkpoint(root, "main", 1)
            create_checkpoint(root, "main", 2)

            # At event 0, max 2, redo should go to 1
            target = find_checkpoint_for_redo(root, "main", 0, 2)
            assert target == 1

            # At event 1, max 2, redo should go to 2
            target = find_checkpoint_for_redo(root, "main", 1, 2)
            assert target == 2

            # At event 2, max 2, redo should return None
            target = find_checkpoint_for_redo(root, "main", 2, 2)
            assert target is None


class TestCheckpointRotation:
    """Tests for checkpoint rotation."""

    def test_rotate_checkpoints(self, tmp_path: Path):
        """Should remove oldest checkpoints when over limit."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            # Create 5 checkpoints
            for i in range(5):
                path = get_checkpoint_path(root, "main", i)
                path.mkdir(parents=True, exist_ok=True)

            # Rotate to keep only 3
            removed = rotate_checkpoints(root, "main", max_count=3)

            assert removed == 2
            checkpoints = list_checkpoints(root, "main")
            assert len(checkpoints) == 3
            assert [c.event_id for c in checkpoints] == [2, 3, 4]


class TestCheckpointDeletion:
    """Tests for checkpoint deletion."""

    def test_delete_checkpoint(self, tmp_path: Path):
        """Should delete specific checkpoint."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            create_checkpoint(root, "main", 0)
            create_checkpoint(root, "main", 1)

            result = delete_checkpoint(root, "main", 0)

            assert result is True
            checkpoints = list_checkpoints(root, "main")
            assert len(checkpoints) == 1
            assert checkpoints[0].event_id == 1

    def test_delete_branch_checkpoints(self, tmp_path: Path):
        """Should delete all checkpoints for a branch."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()
            world = root / "game"
            world.mkdir(exist_ok=True)

            create_checkpoint(root, "main", 0)
            create_checkpoint(root, "main", 1)

            count = delete_branch_checkpoints(root, "main")

            assert count == 2
            checkpoints = list_checkpoints(root, "main")
            assert checkpoints == []


class TestUndoRedoCLI:
    """Tests for undo/redo CLI commands."""

    def test_undo_restores_game(self, tmp_path: Path):
        """undo should restore world state from checkpoint."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Create initial world content
            (root / "game" / "character").mkdir(parents=True)
            hero_path = root / "game" / "character" / "hero.json"
            hero_path.write_text('{"id": "hero", "name": "Original"}', encoding="utf-8")

            # Create checkpoint at event 0
            create_checkpoint(root, "main", 0)

            # Modify world and create checkpoint at event 1
            hero_path.write_text('{"id": "hero", "name": "Modified"}', encoding="utf-8")
            create_checkpoint(root, "main", 1)

            # Update manifest to head_event=1
            manifest_path = root / ".neonrp" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["branches"]["main"]["head_event"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            # Run undo
            result = runner.invoke(cli, ["undo"])

            assert result.exit_code == 0
            assert "Undid change" in result.output or "Undid event" in result.output

            # Verify world restored
            content = hero_path.read_text(encoding="utf-8")
            assert "Original" in content

    def test_redo_nothing_to_redo(self, tmp_path: Path):
        """redo should report nothing to redo when at max event."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["redo"])

            assert result.exit_code == 0
            assert "Nothing to redo" in result.output


class TestSystemProposalCheckpoint:
    """Tests for checkpoint creation via system proposals (M6.5-T1)."""

    def test_game_new_creates_checkpoint(self, tmp_path: Path):
        """game new should create checkpoint before modifying world."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Run game new to create initial world
            result = runner.invoke(cli, ["game", "new"])
            assert result.exit_code == 0

            # Verify checkpoint was created at event 0
            checkpoints = list_checkpoints(root, "main")
            assert len(checkpoints) >= 1

    def test_game_new_force_undo_restores_game(self, tmp_path: Path):
        """game new --force → undo should restore overwritten file content."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            # Create a file that will be overwritten by game new template
            # The template creates player/player.json
            (root / "game" / "player").mkdir(parents=True)
            player_file = root / "game" / "player" / "player.json"
            player_file.write_text('{"id": "player", "kind": "player", "name": "CUSTOM_PLAYER"}', encoding="utf-8")

            # Run game new --force (overwrites player.json)
            result = runner.invoke(cli, ["game", "new", "--force"])
            assert result.exit_code == 0

            # Player file should now have template content (not CUSTOM_PLAYER)
            content_after_game_new = player_file.read_text(encoding="utf-8")
            assert "CUSTOM_PLAYER" not in content_after_game_new
            assert "Player" in content_after_game_new  # Template uses "Player"

            # Run undo
            result = runner.invoke(cli, ["undo"])
            assert result.exit_code == 0

            # Now player.json should be restored to custom content
            content_after_undo = player_file.read_text(encoding="utf-8")
            assert "CUSTOM_PLAYER" in content_after_undo

