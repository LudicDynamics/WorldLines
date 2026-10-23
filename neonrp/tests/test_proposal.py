"""Tests for proposal parsing and validation."""

import pytest

from neonrp.core.proposal import (
    Proposal,
    UpsertTextOp,
    DeleteOp,
    parse_proposal,
    parse_ops,
)


class TestOpValidation:
    """Tests for operation validation."""

    def test_upsert_text_valid(self):
        """Should accept valid upsert_text operation."""
        op = UpsertTextOp(op="upsert_text", path="game/town/tokyo.json", content='{"id": "tokyo"}')
        assert op.op == "upsert_text"
        assert op.path == "game/town/tokyo.json"

    def test_upsert_text_normalizes_path(self):
        """Should normalize backslashes to forward slashes."""
        op = UpsertTextOp(op="upsert_text", path="world\\town\\tokyo.json", content='{"id": "tokyo"}')
        assert op.path == "world/town/tokyo.json"

    def test_upsert_text_rejects_absolute_path(self):
        """Should reject absolute paths."""
        with pytest.raises(ValueError, match="must be relative"):
            UpsertTextOp(op="upsert_text", path="/game/town/tokyo.json", content='{"id": "tokyo"}')

    def test_upsert_text_rejects_path_traversal(self):
        """Should reject paths with '..'."""
        with pytest.raises(ValueError, match="cannot contain"):
            UpsertTextOp(op="upsert_text", path="game/../secret/data.json", content='{"id": "test"}')

    def test_upsert_text_rejects_empty_path(self):
        """Should reject empty path."""
        with pytest.raises(ValueError, match="cannot be empty"):
            UpsertTextOp(op="upsert_text", path="", content='{"id": "test"}')

    def test_delete_valid(self):
        """Should accept valid delete operation."""
        op = DeleteOp(op="delete", path="game/town/old.json")
        assert op.op == "delete"
        assert op.path == "game/town/old.json"


class TestProposalValidation:
    """Tests for proposal validation."""

    def test_proposal_valid_minimal(self):
        """Should accept minimal valid proposal."""
        proposal = Proposal(
            agent_id="test-agent",
            run_id="20260129T120000Z_abc123",
            branch="main",
            base_head_event=0,
            query="Add a test entity",
        )
        assert proposal.agent_id == "test-agent"
        assert proposal.proposal_version == "0.1"

    def test_proposal_with_ops(self):
        """Should accept proposal with operations."""
        proposal = Proposal(
            agent_id="test-agent",
            run_id="20260129T120000Z_abc123",
            branch="main",
            base_head_event=0,
            query="Add a test entity",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="game/town/test.json",
                    content='{"id": "test", "kind": "town", "name": "Test"}',
                )
            ],
        )
        assert len(proposal.ops) == 1

    def test_proposal_rejects_empty_agent_id(self):
        """Should reject empty agent_id."""
        with pytest.raises(ValueError, match="cannot be empty"):
            Proposal(agent_id="", run_id="20260129T120000Z_abc123", branch="main", base_head_event=0, query="test")

    def test_proposal_rejects_negative_base_head_event(self):
        """Should reject base_head_event < -1."""
        with pytest.raises(ValueError, match="must be >= -1"):
            Proposal(
                agent_id="test-agent", run_id="20260129T120000Z_abc123", branch="main", base_head_event=-2, query="test"
            )

    def test_proposal_allows_minus_one_base_head_event(self):
        """Should allow base_head_event = -1 (initial state)."""
        proposal = Proposal(
            agent_id="test-agent", run_id="20260129T120000Z_abc123", branch="main", base_head_event=-1, query="test"
        )
        assert proposal.base_head_event == -1


class TestParseProposal:
    """Tests for parse_proposal function."""

    def test_parse_valid_proposal(self):
        """Should parse a valid proposal dictionary."""
        data = {
            "proposal_version": "0.1",
            "agent_id": "town-master",
            "run_id": "20260129T235900Z_a1b2c3",
            "branch": "main",
            "base_head_event": 12,
            "query": "Add a new shop in Tokyo.",
            "context": {"items": [{"entity_key": "town:tokyo", "path": "game/town/tokyo.json"}]},
            "plan": [{"step": 1, "title": "Update town inventory", "rationale": "Add shop metadata"}],
            "ops": [
                {
                    "op": "upsert_text",
                    "path": "game/town/tokyo.json",
                    "content": '{"id": "tokyo", "kind": "town", "name": "Tokyo"}',
                }
            ],
        }
        proposal = parse_proposal(data)
        assert proposal.agent_id == "town-master"
        assert len(proposal.ops) == 1
        assert proposal.context.items[0].entity_key == "town:tokyo"

    def test_parse_proposal_missing_required_field(self):
        """Should raise ValueError for missing required fields."""
        data = {
            "proposal_version": "0.1",
            # Missing agent_id
            "run_id": "20260129T235900Z_a1b2c3",
            "branch": "main",
            "base_head_event": 12,
            "query": "test",
        }
        with pytest.raises(ValueError):
            parse_proposal(data)


class TestParseOps:
    """Tests for parse_ops function."""

    def test_parse_ops_mixed(self):
        """Should parse mixed operation types."""
        ops_data = [
            {"op": "upsert_text", "path": "game/a.json", "content": "{}"},
            {"op": "delete", "path": "game/b.json"},
        ]
        ops = parse_ops(ops_data)
        assert len(ops) == 2
        assert isinstance(ops[0], UpsertTextOp)
        assert isinstance(ops[1], DeleteOp)

    def test_parse_ops_unknown_type(self):
        """Should raise ValueError for unknown operation type."""
        ops_data = [{"op": "unknown_op", "path": "game/a.json"}]
        with pytest.raises(ValueError, match="unknown operation type"):
            parse_ops(ops_data)
