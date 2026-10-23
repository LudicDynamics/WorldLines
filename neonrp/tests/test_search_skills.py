"""Tests for glob and grep skills (M8-T2)."""

from pathlib import Path


from neonrp.core.skills import SkillRegistry


class TestGlobSkill:
    """Tests for glob skill."""

    def test_basic_glob(self, tmp_path: Path):
        """Should find files matching pattern."""
        # Setup files
        (tmp_path / "game").mkdir()
        (tmp_path / "game" / "char1.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "char2.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "item.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "game/*.json"})

        assert result.success is True
        assert result.data["count"] == 3
        paths = [f["path"] for f in result.data["files"]]
        assert "game/char1.json" in paths
        assert "game/char2.json" in paths

    def test_glob_with_path(self, tmp_path: Path):
        """Should search from specified base path."""
        (tmp_path / "game" / "characters").mkdir(parents=True)
        (tmp_path / "game" / "characters" / "hero.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "items").mkdir()
        (tmp_path / "game" / "items" / "sword.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "*.json", "path": "game/characters"})

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["files"][0]["path"] == "game/characters/hero.json"

    def test_glob_recursive_double_star(self, tmp_path: Path):
        """Should find files in nested subdirectories with ** pattern."""
        # Create nested directory structure
        (tmp_path / "game" / "characters").mkdir(parents=True)
        (tmp_path / "game" / "items" / "weapons").mkdir(parents=True)
        (tmp_path / "game" / "characters" / "hero.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "items" / "sword.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "items" / "weapons" / "bow.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "map.json").write_text("{}", encoding="utf-8")
        (tmp_path / "readme.txt").write_text("not json", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "game/**/*.json"})

        assert result.success is True
        paths = sorted(f["path"] for f in result.data["files"])
        assert "game/characters/hero.json" in paths
        assert "game/items/sword.json" in paths
        assert "game/items/weapons/bow.json" in paths
        assert "game/map.json" in paths
        assert result.data["count"] == 4

    def test_glob_bare_double_star(self, tmp_path: Path):
        """Should find all json files recursively with **/*.json pattern."""
        (tmp_path / "root.json").write_text("{}", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "**/*.json"})

        assert result.success is True
        paths = [f["path"] for f in result.data["files"]]
        assert "sub/nested.json" in paths
        assert result.data["count"] >= 1

    def test_glob_permission_filtering(self, tmp_path: Path):
        """Should filter out denied paths."""
        (tmp_path / "game").mkdir()
        (tmp_path / "game" / "public.json").write_text("{}", encoding="utf-8")
        (tmp_path / "game" / "secret.json").write_text("{}", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["game/public.*"],
            deny_globs=["game/secret.*"],
        )

        result = registry.invoke("glob", {"pattern": "game/*.json"})

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["files"][0]["path"] == "game/public.json"
        assert "game/secret.json" in result.denied_paths

    def test_glob_traversal_rejected(self, tmp_path: Path):
        """Should reject path traversal."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        # Pattern traversal
        result = registry.invoke("glob", {"pattern": "../*.json"})
        assert result.success is False
        assert "traversal" in result.error.lower()

        # Path traversal
        result = registry.invoke("glob", {"pattern": "*.json", "path": "../"})
        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_glob_result_cap(self, tmp_path: Path):
        """Should cap results at 200."""
        # Create many files
        (tmp_path / "files").mkdir()
        for i in range(250):
            (tmp_path / "files" / f"file{i:03d}.txt").write_text("content", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "files/*.txt"})

        assert result.success is True
        assert result.data["count"] == 200
        assert result.data["capped"] is True

    def test_glob_nonexistent_path(self, tmp_path: Path):
        """Should error on nonexistent base path."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("glob", {"pattern": "*.json", "path": "nonexistent"})
        assert result.success is False
        assert "not found" in result.error.lower()


class TestGrepSkill:
    """Tests for grep skill."""

    def test_basic_grep(self, tmp_path: Path):
        """Should find matching lines."""
        (tmp_path / "doc.md").write_text("Hello world\nGoodbye world\nHello again", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "Hello"})

        assert result.success is True
        assert result.data["count"] == 2
        matches = result.data["matches"]
        assert matches[0]["file"] == "doc.md"
        assert matches[0]["line_number"] == 1
        assert "Hello world" in matches[0]["line_content"]

    def test_grep_with_glob_filter(self, tmp_path: Path):
        """Should filter files by glob pattern."""
        (tmp_path / "file.md").write_text("Hello", encoding="utf-8")
        (tmp_path / "file.txt").write_text("Hello", encoding="utf-8")
        (tmp_path / "file.json").write_text('{"message": "Hello"}', encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "Hello", "glob": "*.md"})

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["matches"][0]["file"] == "file.md"

    def test_grep_regex(self, tmp_path: Path):
        """Should support regex patterns."""
        (tmp_path / "log.txt").write_text("error: something failed\nwarning: be careful\nerror: another issue", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": r"^error:"})

        assert result.success is True
        assert result.data["count"] == 2

    def test_grep_invalid_regex(self, tmp_path: Path):
        """Should return friendly error for invalid regex."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "[invalid"})

        assert result.success is False
        assert "Invalid regex" in result.error

    def test_grep_permission_filtering(self, tmp_path: Path):
        """Should filter out denied paths."""
        (tmp_path / "public.txt").write_text("Hello", encoding="utf-8")
        (tmp_path / "secret.txt").write_text("Hello", encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["public.*"],
            deny_globs=["secret.*"],
        )

        result = registry.invoke("grep", {"pattern": "Hello"})

        assert result.success is True
        assert result.data["count"] == 1
        assert result.data["matches"][0]["file"] == "public.txt"
        assert "secret.txt" in result.denied_paths

    def test_grep_result_cap(self, tmp_path: Path):
        """Should cap results at max_results."""
        # Create file with many matching lines
        lines = "\n".join([f"match line {i}" for i in range(100)])
        (tmp_path / "many.txt").write_text(lines, encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "match", "max_results": 25})

        assert result.success is True
        assert result.data["count"] == 25
        assert result.data["capped"] is True

    def test_grep_line_truncation(self, tmp_path: Path):
        """Should truncate long lines to 500 chars."""
        long_line = "x" * 600
        (tmp_path / "long.txt").write_text(long_line, encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "xxx"})

        assert result.success is True
        assert result.data["count"] == 1
        assert len(result.data["matches"][0]["line_content"]) <= 503  # 500 + "..."

    def test_grep_traversal_rejected(self, tmp_path: Path):
        """Should reject path traversal."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "test", "glob": "../*.txt"})
        assert result.success is False
        assert "traversal" in result.error.lower()

    def test_grep_subdirectory(self, tmp_path: Path):
        """Should search in subdirectories."""
        (tmp_path / "game" / "chars").mkdir(parents=True)
        (tmp_path / "game" / "chars" / "hero.json").write_text('{"name": "Hero"}', encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        result = registry.invoke("grep", {"pattern": "Hero", "path": "game"})

        assert result.success is True
        assert result.data["count"] == 1
        assert "hero.json" in result.data["matches"][0]["file"]
