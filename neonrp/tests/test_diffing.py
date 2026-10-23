"""Tests for diffing module."""

from pathlib import Path


from neonrp.core.diffing import render_diff, render_diff_summary
from neonrp.core.proposal import Proposal, UpsertTextOp, DeleteOp


class TestRenderDiff:
    """Tests for render_diff function."""

    def test_diff_new_file(self, tmp_path: Path):
        """Should render diff for new file creation."""
        game_root = tmp_path / "game"
        game_root.mkdir()

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[UpsertTextOp(op="upsert_text", path="town/new.json", content='{"id": "new"}')],
        )

        diff = render_diff(proposal, game_root)
        assert "/dev/null" in diff
        assert "town/new.json" in diff
        assert '{"id": "new"}' in diff

    def test_diff_modify_file(self, tmp_path: Path):
        """Should render diff for file modification."""
        game_root = tmp_path / "game"
        game_root.mkdir()
        (game_root / "town").mkdir()
        (game_root / "town" / "existing.json").write_text('{"id": "old"}', encoding="utf-8")

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[UpsertTextOp(op="upsert_text", path="town/existing.json", content='{"id": "new"}')],
        )

        diff = render_diff(proposal, game_root)
        assert "town/existing.json" in diff
        assert "-" in diff  # Has deletion line
        assert "+" in diff  # Has addition line

    def test_diff_delete_file(self, tmp_path: Path):
        """Should render diff for file deletion."""
        game_root = tmp_path / "game"
        game_root.mkdir()
        (game_root / "town").mkdir()
        (game_root / "town" / "old.json").write_text('{"id": "old"}', encoding="utf-8")

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[DeleteOp(op="delete", path="town/old.json")],
        )

        diff = render_diff(proposal, game_root)
        assert "town/old.json" in diff
        assert "/dev/null" in diff
        assert "@@ -1,1 +0,0 @@" in diff  # Standard unified diff hunk header

    def test_diff_stable_order(self, tmp_path: Path):
        """Should produce stable output sorted by path."""
        game_root = tmp_path / "game"
        game_root.mkdir()

        # Create proposal with ops in non-sorted order
        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[
                UpsertTextOp(op="upsert_text", path="z/file.json", content="{}"),
                UpsertTextOp(op="upsert_text", path="a/file.json", content="{}"),
                UpsertTextOp(op="upsert_text", path="m/file.json", content="{}"),
            ],
        )

        diff = render_diff(proposal, game_root)

        # Check order in diff
        a_pos = diff.find("a/file.json")
        m_pos = diff.find("m/file.json")
        z_pos = diff.find("z/file.json")

        assert a_pos < m_pos < z_pos, "Diff should be sorted by path"

    def test_diff_empty_ops(self, tmp_path: Path):
        """Should handle empty ops list."""
        game_root = tmp_path / "game"
        game_root.mkdir()

        proposal = Proposal(agent_id="test", run_id="test_run", branch="main", base_head_event=0, query="test", ops=[])

        diff = render_diff(proposal, game_root)
        assert diff == ""


class TestRenderDiffSummary:
    """Tests for render_diff_summary function."""

    def test_summary_added_files(self, tmp_path: Path):
        """Should categorize new files as added."""
        game_root = tmp_path / "game"
        game_root.mkdir()

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[UpsertTextOp(op="upsert_text", path="new.json", content="{}")],
        )

        summary = render_diff_summary(proposal, game_root)
        assert "new.json" in summary["added"]
        assert len(summary["modified"]) == 0
        assert len(summary["deleted"]) == 0

    def test_summary_modified_files(self, tmp_path: Path):
        """Should categorize existing files as modified."""
        game_root = tmp_path / "game"
        game_root.mkdir()
        (game_root / "existing.json").write_text("{}", encoding="utf-8")

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[UpsertTextOp(op="upsert_text", path="existing.json", content='{"new": true}')],
        )

        summary = render_diff_summary(proposal, game_root)
        assert "existing.json" in summary["modified"]
        assert len(summary["added"]) == 0

    def test_summary_deleted_files(self, tmp_path: Path):
        """Should categorize delete ops as deleted."""
        game_root = tmp_path / "game"
        game_root.mkdir()

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[DeleteOp(op="delete", path="old.json")],
        )

        summary = render_diff_summary(proposal, game_root)
        assert "old.json" in summary["deleted"]

    def test_summary_total_count(self, tmp_path: Path):
        """Should count total changes."""
        game_root = tmp_path / "game"
        game_root.mkdir()
        (game_root / "existing.json").write_text("{}", encoding="utf-8")

        proposal = Proposal(
            agent_id="test",
            run_id="test_run",
            branch="main",
            base_head_event=0,
            query="test",
            ops=[
                UpsertTextOp(op="upsert_text", path="new.json", content="{}"),
                UpsertTextOp(op="upsert_text", path="existing.json", content='{"new": true}'),
                DeleteOp(op="delete", path="old.json"),
            ],
        )

        summary = render_diff_summary(proposal, game_root)
        assert summary["total"] == 3

