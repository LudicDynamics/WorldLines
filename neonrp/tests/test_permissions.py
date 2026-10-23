"""Tests for permissions module."""

import pytest

from neonrp.core.permissions import (
    normalize_path,
    match_glob,
    check_permission,
    check_ops_permissions,
    format_permission_error,
    PermissionResult,
)
from neonrp.core.proposal import UpsertTextOp, DeleteOp


class TestNormalizePath:
    """Tests for path normalization."""

    def test_normalize_forward_slashes(self):
        """Should keep forward slashes as is."""
        assert normalize_path("game/town/tokyo.json") == "game/town/tokyo.json"

    def test_normalize_backslashes(self):
        """Should convert backslashes to forward slashes."""
        assert normalize_path("world\\town\\tokyo.json") == "world/town/tokyo.json"

    def test_normalize_strips_trailing_slashes(self):
        """Should strip trailing slashes."""
        assert normalize_path("game/town/") == "game/town"

    def test_normalize_accepts_unix_absolute_path(self):
        """Should accept Unix-style absolute paths and normalize separators."""
        assert normalize_path("/game/town/") == "game/town"

    def test_normalize_accepts_windows_absolute_path(self):
        """Should accept Windows-style absolute paths."""
        assert normalize_path("C:\\Users\\data.json") == "C:/Users/data.json"
        assert normalize_path("D:/Project/file.txt") == "D:/Project/file.txt"

    def test_normalize_rejects_path_traversal(self):
        """Should raise ValueError for path traversal."""
        with pytest.raises(ValueError, match="not allowed"):
            normalize_path("game/../secret")

    def test_normalize_rejects_path_traversal_at_start(self):
        """Should reject path traversal at start."""
        with pytest.raises(ValueError, match="not allowed"):
            normalize_path("../secret/file.json")


class TestMatchGlob:
    """Tests for glob matching."""

    def test_match_exact(self):
        """Should match exact path."""
        assert match_glob("game/town/tokyo.json", "game/town/tokyo.json")

    def test_match_star_wildcard(self):
        """Should match single * wildcard."""
        assert match_glob("game/town/tokyo.json", "game/town/*.json")
        assert not match_glob("game/town/sub/tokyo.json", "game/town/*.json")

    def test_match_double_star(self):
        """Should match ** for recursive paths."""
        assert match_glob("game/town/tokyo.json", "game/**")
        assert match_glob("game/town/sub/tokyo.json", "game/**")
        assert match_glob("game/a.json", "game/**")

    def test_match_double_star_with_suffix(self):
        """Should match ** with suffix pattern."""
        assert match_glob("game/town/tokyo.json", "game/**/*.json")
        assert match_glob("game/deep/nested/file.json", "game/**/*.json")

    def test_no_match(self):
        """Should not match non-matching paths."""
        assert not match_glob("agents/test/agent.json", "game/**")


class TestCheckPermission:
    """Tests for permission checking."""

    def test_allow_matching_write_glob(self):
        """Should allow path matching write_glob."""
        result = check_permission("game/town/tokyo.json", write_globs=["game/**"], deny_globs=[])
        assert result.allowed
        assert result.matched_glob == "game/**"

    def test_deny_takes_priority(self):
        """Should deny even if write_glob matches when deny_glob matches."""
        result = check_permission(
            ".neonrp/manifest.json",
            write_globs=["**"],  # Would match everything
            deny_globs=[".neonrp/**"],
        )
        assert not result.allowed
        assert result.matched_glob == ".neonrp/**"

    def test_deny_no_write_match(self):
        """Should deny when no write_glob matches."""
        result = check_permission("secret/data.json", write_globs=["game/**", "agents/**"], deny_globs=[])
        assert not result.allowed
        assert "does not match" in result.reason

    def test_deny_path_traversal(self):
        """Should deny path with traversal."""
        result = check_permission("game/../secret/data.json", write_globs=["game/**"], deny_globs=[])
        assert not result.allowed
        assert "traversal" in result.reason.lower()

    def test_default_deny_globs(self):
        """Should deny .neonrp and agents by default pattern."""
        # Test typical default deny patterns
        deny_globs = [".neonrp/**", "agents/**"]

        # Should deny .neonrp
        result = check_permission(".neonrp/events/main.jsonl", write_globs=["**"], deny_globs=deny_globs)
        assert not result.allowed

        # Should deny agents
        result = check_permission("agents/test/agent.json", write_globs=["**"], deny_globs=deny_globs)
        assert not result.allowed


class TestCheckOpsPermissions:
    """Tests for checking permissions on operations."""

    def test_all_ops_allowed(self):
        """Should return empty list when all ops are allowed."""
        ops = [
            UpsertTextOp(op="upsert_text", path="game/a.json", content="{}"),
            DeleteOp(op="delete", path="game/b.json"),
        ]
        failures = check_ops_permissions(ops, write_globs=["game/**"], deny_globs=[])
        assert failures == []

    def test_some_ops_denied(self):
        """Should return failures for denied ops."""
        ops = [
            UpsertTextOp(op="upsert_text", path="game/a.json", content="{}"),
            UpsertTextOp(op="upsert_text", path="agents/test.json", content="{}"),
        ]
        failures = check_ops_permissions(ops, write_globs=["game/**"], deny_globs=["agents/**"])
        assert len(failures) == 1
        assert failures[0][0] == 1  # Second op failed
        assert not failures[0][1].allowed


class TestFormatPermissionError:
    """Tests for error formatting."""

    def test_format_deny_error(self):
        """Should format deny error with suggestions."""
        result = PermissionResult(
            allowed=False, reason="Path 'agents/test.json' matches deny pattern", matched_glob="agents/**"
        )
        error = format_permission_error(
            agent_id="test-agent",
            path="agents/test.json",
            result=result,
            write_globs=["game/**"],
            deny_globs=["agents/**"],
        )

        assert "test-agent" in error
        assert "agents/test.json" in error
        assert "Suggestions" in error

    def test_format_no_match_error(self):
        """Should format no-match error with suggestions."""
        result = PermissionResult(
            allowed=False, reason="Path 'secret/data.json' does not match any write pattern", matched_glob=None
        )
        error = format_permission_error(
            agent_id="test-agent", path="secret/data.json", result=result, write_globs=["game/**"], deny_globs=[]
        )

        assert "test-agent" in error
        assert "write_globs" in error
