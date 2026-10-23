"""Tests for write_file and edit_file skills (M8-T1)."""

from pathlib import Path


from neonrp.core.permissions import check_write_permission
from neonrp.core.skills import SkillRegistry
from neonrp.core.storage import atomic_write_text


class TestCheckWritePermission:
    """Tests for check_write_permission function."""

    def test_allowed_path(self):
        """Path in direct_write_globs should be allowed."""
        result = check_write_permission("lore/backstory.md", ["lore/**"], [])
        assert result.allowed is True
        assert "matches direct write pattern" in result.reason

    def test_denied_not_in_globs(self):
        """Path NOT in direct_write_globs should be denied with guidance."""
        result = check_write_permission("game/character/hero.json", ["lore/**"], [])
        assert result.allowed is False
        assert "submit_proposal" in result.reason

    def test_denied_non_game_path_not_in_globs(self):
        """Non-world path denial should not incorrectly mention submit_proposal."""
        result = check_write_permission("notes/todo.txt", ["lore/**"], [])
        assert result.allowed is False
        assert "direct_write_globs" in result.reason
        assert "submit_proposal" not in result.reason

    def test_denied_by_deny_globs(self):
        """Path in deny_globs should be denied."""
        result = check_write_permission("secrets/passwords.txt", ["**"], ["secrets/**"])
        assert result.allowed is False
        assert "deny pattern" in result.reason

    def test_required_deny_always_blocked(self):
        """Paths in REQUIRED_DENY_GLOBS should always be denied."""
        # .neonrp is protected
        result = check_write_permission(".neonrp/manifest.json", ["**"], [])
        assert result.allowed is False
        assert "protected directory" in result.reason

        # agents is protected
        result = check_write_permission("agents/narrator/system.md", ["**"], [])
        assert result.allowed is False
        assert "protected directory" in result.reason

    def test_required_deny_can_be_overridden(self):
        """Protected dirs can be enabled explicitly for Claude-Code style mode."""
        result = check_write_permission(".neonrp/manifest.json", ["**"], [], allow_protected_paths=True)
        assert result.allowed is True

    def test_path_traversal_rejected(self):
        """Path with .. should be rejected."""
        result = check_write_permission("lore/../secrets/passwords.txt", ["lore/**"], [])
        assert result.allowed is False
        assert "traversal" in result.reason.lower()


class TestAtomicWriteText:
    """Tests for atomic_write_text function."""

    def test_creates_file(self, tmp_path: Path):
        """Should create file with content."""
        target = tmp_path / "test.txt"
        atomic_write_text(target, "hello world")
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_creates_parent_dirs(self, tmp_path: Path):
        """Should create parent directories if missing."""
        target = tmp_path / "nested" / "dirs" / "test.txt"
        atomic_write_text(target, "content")
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "content"

    def test_overwrites_existing(self, tmp_path: Path):
        """Should overwrite existing file."""
        target = tmp_path / "test.txt"
        target.write_text("old content", encoding="utf-8")
        atomic_write_text(target, "new content")
        assert target.read_text(encoding="utf-8") == "new content"


class TestWriteFileSkill:
    """Tests for write_file skill."""

    def test_write_allowed(self, tmp_path: Path):
        """Should write file when path is in direct_write_globs."""
        # Setup skill registry with direct_write_globs
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke("write_file", {"path": "notes/session1.txt", "content": "Session notes"})

        assert result.success is True
        assert (tmp_path / "notes" / "session1.txt").exists()
        assert (tmp_path / "notes" / "session1.txt").read_text(encoding="utf-8") == "Session notes"
        assert result.data["bytes_written"] == len("Session notes".encode("utf-8"))

    def test_write_denied(self, tmp_path: Path):
        """Should deny write when path not in direct_write_globs."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke("write_file", {"path": "game/character/hero.json", "content": "{}"})

        assert result.success is False
        assert "submit_proposal" in result.error
        assert not (tmp_path / "game" / "character" / "hero.json").exists()

    def test_write_required_deny(self, tmp_path: Path):
        """Should deny write to REQUIRED_DENY_GLOBS even with wildcard."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],  # Very permissive
        )

        result = registry.invoke("write_file", {"path": ".neonrp/evil.json", "content": "{}"})

        assert result.success is False
        assert "protected directory" in result.error
        assert not (tmp_path / ".neonrp" / "evil.json").exists()

    def test_write_path_traversal(self, tmp_path: Path):
        """Should reject path traversal."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke("write_file", {"path": "notes/../secrets/evil.txt", "content": "hacked"})

        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_write_workspace_placeholder_path_maps_to_project_root(self, tmp_path: Path):
        """'/workspace/project/...' should map to the active project root."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke(
            "write_file",
            {"path": "/workspace/project/snake.html", "content": "<html>ok</html>"},
        )

        assert result.success is True
        target = tmp_path / "snake.html"
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "<html>ok</html>"
        assert Path(result.data["path"]) == target.resolve()

    def test_write_project_root_placeholder_maps_to_project_root(self, tmp_path: Path):
        """'<project-root>/...' placeholder should map to the active project root."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke(
            "write_file",
            {"path": "<project-root>/index.html", "content": "<html>ok</html>"},
        )

        assert result.success is True
        target = tmp_path / "index.html"
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "<html>ok</html>"
        assert Path(result.data["path"]) == target.resolve()


class TestEditFileSkill:
    """Tests for edit_file skill."""

    def test_edit_exact_match(self, tmp_path: Path):
        """Should replace exact text when found once."""
        # Create initial file
        (tmp_path / "notes").mkdir()
        target = tmp_path / "notes" / "todo.md"
        target.write_text("- [ ] Buy milk\n- [ ] Fix bug\n", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke(
            "edit_file",
            {
                "path": "notes/todo.md",
                "old_text": "- [ ] Fix bug",
                "new_text": "- [x] Fix bug",
            },
        )

        assert result.success is True
        assert result.data["replaced"] is True
        assert target.read_text(encoding="utf-8") == "- [ ] Buy milk\n- [x] Fix bug\n"

    def test_edit_not_found(self, tmp_path: Path):
        """Should error when old_text not found."""
        (tmp_path / "notes").mkdir()
        target = tmp_path / "notes" / "test.txt"
        target.write_text("hello world", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke(
            "edit_file",
            {
                "path": "notes/test.txt",
                "old_text": "goodbye",
                "new_text": "hello",
            },
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_multiple_matches(self, tmp_path: Path):
        """Should error when old_text found multiple times."""
        (tmp_path / "notes").mkdir()
        target = tmp_path / "notes" / "test.txt"
        target.write_text("hello hello world", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke(
            "edit_file",
            {
                "path": "notes/test.txt",
                "old_text": "hello",
                "new_text": "hi",
            },
        )

        assert result.success is False
        assert "2 times" in result.error

    def test_edit_denied(self, tmp_path: Path):
        """Should deny edit when path not in direct_write_globs."""
        (tmp_path / "game" / "character").mkdir(parents=True)
        target = tmp_path / "game" / "character" / "hero.json"
        target.write_text('{"hp": 100}', encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke(
            "edit_file",
            {
                "path": "game/character/hero.json",
                "old_text": '"hp": 100',
                "new_text": '"hp": 999',
            },
        )

        assert result.success is False
        assert "submit_proposal" in result.error
        # Original file unchanged
        assert target.read_text(encoding="utf-8") == '{"hp": 100}'

    def test_edit_file_not_found(self, tmp_path: Path):
        """Should error when file does not exist."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke(
            "edit_file",
            {
                "path": "notes/nonexistent.txt",
                "old_text": "foo",
                "new_text": "bar",
            },
        )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestDeleteFileSkill:
    """Tests for delete_file skill."""

    def test_delete_allowed(self, tmp_path: Path):
        """Should delete file when path is in direct_write_globs."""
        (tmp_path / "notes").mkdir()
        (tmp_path / "notes" / "old.txt").write_text("delete me", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke("delete_file", {"path": "notes/old.txt"})

        assert result.success is True
        assert result.data["deleted"] is True
        assert not (tmp_path / "notes" / "old.txt").exists()

    def test_delete_denied(self, tmp_path: Path):
        """Should deny delete when path not in direct_write_globs."""
        (tmp_path / "game" / "character").mkdir(parents=True)
        (tmp_path / "game" / "character" / "hero.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["notes/**"],
        )

        result = registry.invoke("delete_file", {"path": "game/character/hero.json"})

        assert result.success is False
        assert (tmp_path / "game" / "character" / "hero.json").exists()

    def test_delete_protected_path(self, tmp_path: Path):
        """Should deny delete of REQUIRED_DENY_GLOBS even with wildcard."""
        (tmp_path / ".neonrp").mkdir()
        (tmp_path / ".neonrp" / "manifest.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke("delete_file", {"path": ".neonrp/manifest.json"})

        assert result.success is False
        assert "protected" in result.error.lower()
        assert (tmp_path / ".neonrp" / "manifest.json").exists()

    def test_delete_file_not_found(self, tmp_path: Path):
        """Should return error when file does not exist."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke("delete_file", {"path": "nonexistent.txt"})

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_delete_directory_rejected(self, tmp_path: Path):
        """Should refuse to delete a directory."""
        (tmp_path / "somedir").mkdir()

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke("delete_file", {"path": "somedir"})

        assert result.success is False
        assert "directory" in result.error.lower()
        assert (tmp_path / "somedir").exists()

    def test_delete_path_traversal(self, tmp_path: Path):
        """Should reject path traversal attempts."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke("delete_file", {"path": "../outside.txt"})

        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_delete_empty_path(self, tmp_path: Path):
        """Should return error for empty path."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=["**"],
        )

        result = registry.invoke("delete_file", {"path": ""})

        assert result.success is False
        assert "required" in result.error.lower()


class TestSkillRegistryDirectWriteGlobs:
    """Tests for SkillRegistry direct_write_globs parameter."""

    def test_default_empty(self, tmp_path: Path):
        """Without direct_write_globs, all writes should be denied."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            # No direct_write_globs
        )

        result = registry.invoke("write_file", {"path": "test.txt", "content": "hello"})
        assert result.success is False

    def test_accepts_optional_param(self, tmp_path: Path):
        """Should accept None as direct_write_globs."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
            direct_write_globs=None,  # Explicit None
        )
        assert registry.direct_write_globs == []
