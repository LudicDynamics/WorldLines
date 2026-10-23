"""Tests for world directory hashing."""

from pathlib import Path

from neonrp.core.character_agent import _hash_soul_folder
from neonrp.core.hashing import compute_game_hash, compute_file_hash


class TestComputeWorldHash:
    def test_empty_directory(self, tmp_path: Path):
        game_dir = tmp_path / "game"
        game_dir.mkdir()

        result = compute_game_hash(game_dir)
        assert result == "sha256:empty"

    def test_nonexistent_directory(self, tmp_path: Path):
        game_dir = tmp_path / "missing"

        result = compute_game_hash(game_dir)
        assert result == "sha256:empty"

    def test_single_file(self, tmp_path: Path):
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        result = compute_game_hash(game_dir)
        assert result.startswith("sha256:")
        assert result != "sha256:empty"

    def test_deterministic(self, tmp_path: Path):
        """Same content should produce same hash."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        hash1 = compute_game_hash(game_dir)
        hash2 = compute_game_hash(game_dir)

        assert hash1 == hash2

    def test_content_change_changes_hash(self, tmp_path: Path):
        """Different content should produce different hash."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "test.json").write_text('{"id": "test1"}', encoding="utf-8")

        hash1 = compute_game_hash(game_dir)

        (game_dir / "test.json").write_text('{"id": "test2"}', encoding="utf-8")

        hash2 = compute_game_hash(game_dir)

        assert hash1 != hash2

    def test_new_file_changes_hash(self, tmp_path: Path):
        """Adding a file should change hash."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        hash1 = compute_game_hash(game_dir)

        (game_dir / "new.json").write_text('{"id": "new"}', encoding="utf-8")

        hash2 = compute_game_hash(game_dir)

        assert hash1 != hash2

    def test_nested_directories(self, tmp_path: Path):
        """Should include files from nested directories."""
        game_dir = tmp_path / "game"
        game_dir.mkdir()
        (game_dir / "root.json").write_text('{"id": "root"}', encoding="utf-8")

        subdir = game_dir / "character"
        subdir.mkdir()
        (subdir / "hero.json").write_text('{"id": "hero"}', encoding="utf-8")

        result = compute_game_hash(game_dir)
        assert result.startswith("sha256:")
        assert result != "sha256:empty"

    def test_path_ordering_stable(self, tmp_path: Path):
        """Hash should be stable regardless of file creation order."""
        # Create world 1 with files in order a, b
        world1 = tmp_path / "world1"
        world1.mkdir()
        (world1 / "a.json").write_text('{"id": "a"}', encoding="utf-8")
        (world1 / "b.json").write_text('{"id": "b"}', encoding="utf-8")

        # Create world 2 with files in order b, a
        world2 = tmp_path / "world2"
        world2.mkdir()
        (world2 / "b.json").write_text('{"id": "b"}', encoding="utf-8")
        (world2 / "a.json").write_text('{"id": "a"}', encoding="utf-8")

        hash1 = compute_game_hash(world1)
        hash2 = compute_game_hash(world2)

        assert hash1 == hash2

    def test_soul_folder_hash_uses_canonical_tree_hash(self, tmp_path: Path):
        soul_dir = tmp_path / "souls" / "elena-si-elena0001"
        (soul_dir / "persona").mkdir(parents=True)
        (soul_dir / "soul.md").write_text("# Elena\n", encoding="utf-8")
        (soul_dir / "persona" / "identity.json").write_text(
            '{"name":"Elena"}',
            encoding="utf-8",
        )

        assert _hash_soul_folder(soul_dir) == compute_game_hash(soul_dir)


class TestComputeFileHash:
    def test_simple_file(self, tmp_path: Path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")

        result = compute_file_hash(file_path)

        # Known sha256 of "hello world"
        assert len(result) == 64
        assert result == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

    def test_deterministic(self, tmp_path: Path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content", encoding="utf-8")

        hash1 = compute_file_hash(file_path)
        hash2 = compute_file_hash(file_path)

        assert hash1 == hash2

    def test_binary_file(self, tmp_path: Path):
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"\x00\x01\x02\xff")

        result = compute_file_hash(file_path)

        assert len(result) == 64

