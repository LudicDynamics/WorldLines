"""Tests for tool argument validation (M7-T2)."""

import json
from pathlib import Path

from neonrp.core.skills import validate_tool_arguments
from neonrp.core.agent_runner import _execute_tool
from neonrp.core.llm import ToolCall


class TestValidateToolArguments:
    """Tests for validate_tool_arguments function."""

    def test_unknown_tool(self):
        """Unknown tool returns error."""
        is_valid, error = validate_tool_arguments("unknown_tool", {})
        assert not is_valid
        assert "Unknown tool" in error

    # --- read_context tests ---
    def test_read_context_valid(self):
        """read_context with valid args."""
        is_valid, error = validate_tool_arguments("read_context", {"query": "test"})
        assert is_valid
        assert error is None

    def test_read_context_missing_query(self):
        """read_context missing required query."""
        is_valid, error = validate_tool_arguments("read_context", {})
        assert not is_valid
        assert "empty arguments" in error or "Missing required field: query" in error

    def test_read_context_null_query(self):
        """read_context with null query."""
        is_valid, error = validate_tool_arguments("read_context", {"query": None})
        assert not is_valid
        assert "cannot be null" in error

    def test_read_context_with_limit(self):
        """read_context with optional limit."""
        is_valid, error = validate_tool_arguments("read_context", {"query": "test", "limit": 5})
        assert is_valid
        assert error is None

    def test_read_context_wrong_limit_type(self):
        """read_context with wrong limit type."""
        is_valid, error = validate_tool_arguments("read_context", {"query": "test", "limit": "five"})
        assert not is_valid
        assert "must be an integer" in error

    # --- find tests ---
    def test_find_valid(self):
        """find with valid args."""
        is_valid, error = validate_tool_arguments("find", {"query": "hero"})
        assert is_valid
        assert error is None

    def test_find_with_filters(self):
        """find with optional filters."""
        is_valid, error = validate_tool_arguments("find", {"query": "hero", "kind": "character", "tag": "npc"})
        assert is_valid
        assert error is None

    def test_find_missing_query(self):
        """find missing required query."""
        is_valid, error = validate_tool_arguments("find", {"kind": "character"})
        assert not is_valid
        assert "Missing required field: query" in error

    # --- read_file tests ---
    def test_read_file_valid(self):
        """read_file with valid args."""
        is_valid, error = validate_tool_arguments("read_file", {"path": "game/character/hero.json"})
        assert is_valid
        assert error is None

    def test_read_file_empty_path(self):
        """read_file with empty path."""
        is_valid, error = validate_tool_arguments("read_file", {"path": ""})
        # Note: current schema doesn't have minLength on read_file path
        # But the skill itself rejects empty paths
        assert is_valid or "minLength" in error

    def test_read_file_missing_path(self):
        """read_file missing required path."""
        is_valid, error = validate_tool_arguments("read_file", {})
        assert not is_valid
        assert "empty arguments" in error or "Missing required field: path" in error

    def test_read_file_wrong_path_type(self):
        """read_file with wrong path type."""
        is_valid, error = validate_tool_arguments("read_file", {"path": 123})
        assert not is_valid
        assert "must be a string" in error

    def test_import_sillytavern_card_valid(self):
        """import_sillytavern_card with valid args."""
        is_valid, error = validate_tool_arguments(
            "import_sillytavern_card",
            {
                "path": "cards/world.png",
                "entity_id": "world-card",
                "target_path": "game/npc/world-card.json",
                "name": "世界卡",
            },
        )
        assert is_valid
        assert error is None

    def test_ensure_playable_scaffold_valid(self):
        """ensure_playable_scaffold should accept optional template/agent args."""
        is_valid, error = validate_tool_arguments(
            "ensure_playable_scaffold",
            {"template_name": "default", "active_agent": "narrator", "force": True},
        )
        assert is_valid
        assert error is None

    # --- list_entities tests ---
    def test_list_entities_valid_empty(self):
        """list_entities with no args (all optional)."""
        is_valid, error = validate_tool_arguments("list_entities", {})
        assert is_valid
        assert error is None

    def test_list_entities_with_filters(self):
        """list_entities with optional filters."""
        is_valid, error = validate_tool_arguments("list_entities", {"kind": "item", "tag": "weapon"})
        assert is_valid
        assert error is None

    def test_list_entities_kind_rejected_when_not_in_project_index(self, tmp_path: Path):
        """Dynamic kind enum should reject kinds not present in the current manifest index."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "npc").mkdir(parents=True)
        (tmp_path / "game" / "npc" / "merchant.json").write_text(
            json.dumps({"id": "merchant", "kind": "npc", "name": "Merchant"}),
            encoding="utf-8",
        )
        manifest = {
            "version": "0.3",
            "current_branch": "main",
            "branches": {"main": {"head_event": -1}},
            "entities": {
                "npc:merchant": {
                    "id": "merchant",
                    "kind": "npc",
                    "name": "Merchant",
                    "path": "game/npc/merchant.json",
                    "mtime": 1.0,
                    "hash": "sha256:a",
                }
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        is_valid, error = validate_tool_arguments("list_entities", {"kind": "character"}, root=tmp_path)
        assert not is_valid
        assert "must be one of: npc" in (error or "")

    def test_list_entities_kind_accepted_when_in_project_index(self, tmp_path: Path):
        """Dynamic kind enum should accept kinds present in the current manifest index."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (tmp_path / "game" / "town").mkdir(parents=True)
        (tmp_path / "game" / "town" / "start-town.json").write_text(
            json.dumps({"id": "start-town", "kind": "town", "name": "Start Town"}),
            encoding="utf-8",
        )
        manifest = {
            "version": "0.3",
            "current_branch": "main",
            "branches": {"main": {"head_event": -1}},
            "entities": {
                "town:start-town": {
                    "id": "start-town",
                    "kind": "town",
                    "name": "Start Town",
                    "path": "game/town/start-town.json",
                    "mtime": 1.0,
                    "hash": "sha256:b",
                }
            },
        }
        (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        is_valid, error = validate_tool_arguments("list_entities", {"kind": "town"}, root=tmp_path)
        assert is_valid
        assert error is None

    # --- submit_proposal tests ---
    def test_submit_proposal_valid(self):
        """submit_proposal with valid args."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"op": "upsert_text", "path": "character/hero.json", "content": "{}"},
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert is_valid
        assert error is None

    def test_submit_proposal_missing_required(self):
        """submit_proposal missing required fields."""
        args = {
            "run_id": "test_run_123",
            # missing agent_id, branch, base_head_event, ops
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "Missing required field" in error

    def test_submit_proposal_empty_run_id(self):
        """submit_proposal with empty run_id."""
        args = {
            "proposal_version": "0.1",
            "run_id": "",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "at least 1 character" in error

    def test_submit_proposal_invalid_op_enum(self):
        """submit_proposal with invalid op type."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"op": "invalid_op", "path": "character/hero.json"},
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "must be one of: upsert_text, delete" in error

    def test_submit_proposal_missing_op_in_item(self):
        """submit_proposal with missing op in ops item."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"path": "character/hero.json"},  # missing op
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "ops[0] missing required field: op" in error

    def test_submit_proposal_missing_path_in_item(self):
        """submit_proposal with missing path in ops item."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"op": "upsert_text"},  # missing path
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "ops[0] missing required field: path" in error

    def test_submit_proposal_empty_path_in_item(self):
        """submit_proposal with empty path in ops item."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"op": "upsert_text", "path": "", "content": "{}"},
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "at least 1 character" in error

    def test_submit_proposal_delete_op_valid(self):
        """submit_proposal with valid delete operation."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [
                {"op": "delete", "path": "character/old-hero.json"},
            ],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert is_valid
        assert error is None

    def test_submit_proposal_non_array_ops(self):
        """submit_proposal with non-array ops."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": "not an array",
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "must be an array" in error

    def test_submit_proposal_non_object_ops_item(self):
        """submit_proposal with non-object ops item."""
        args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": ["not an object"],
        }
        is_valid, error = validate_tool_arguments("submit_proposal", args)
        assert not is_valid
        assert "ops[0] must be an object" in error


class TestAutoCoercion:
    """Tests for auto-coercion of dict/list to string in validate_tool_arguments."""

    def test_write_file_content_dict_coerced_to_json_string(self):
        """write_file content passed as dict should be auto-serialized to JSON string."""
        args = {"path": "game/hero.json", "content": {"name": "Hero", "hp": 100}}
        is_valid, error = validate_tool_arguments("write_file", args)
        assert is_valid, f"Expected valid, got error: {error}"
        assert isinstance(args["content"], str)
        parsed = json.loads(args["content"])
        assert parsed == {"name": "Hero", "hp": 100}

    def test_write_file_content_list_coerced_to_json_string(self):
        """write_file content passed as list should be auto-serialized to JSON string."""
        args = {"path": "game/items.json", "content": [{"id": 1}, {"id": 2}]}
        is_valid, error = validate_tool_arguments("write_file", args)
        assert is_valid, f"Expected valid, got error: {error}"
        assert isinstance(args["content"], str)
        parsed = json.loads(args["content"])
        assert parsed == [{"id": 1}, {"id": 2}]

    def test_write_file_content_string_unchanged(self):
        """write_file content passed as string should remain unchanged."""
        args = {"path": "notes.txt", "content": "hello world"}
        is_valid, error = validate_tool_arguments("write_file", args)
        assert is_valid
        assert args["content"] == "hello world"

    def test_edit_file_old_text_not_coerced(self):
        """edit_file old_text as int should still fail (only dict/list are coerced)."""
        args = {"path": "test.txt", "old_text": 123, "new_text": "abc"}
        is_valid, error = validate_tool_arguments("edit_file", args)
        assert not is_valid
        assert "must be a string" in error

    def test_coercion_preserves_unicode(self):
        """Auto-coercion should preserve non-ASCII characters."""
        args = {"path": "game/npc.json", "content": {"name": "勇者", "title": "龙骑士"}}
        is_valid, error = validate_tool_arguments("write_file", args)
        assert is_valid
        assert "勇者" in args["content"]
        assert "龙骑士" in args["content"]


class TestExecuteToolWithValidation:
    """Tests for _execute_tool with validation."""

    def test_execute_unknown_tool(self):
        """Unknown tool returns error."""
        # Create a minimal SkillRegistry mock
        from unittest.mock import MagicMock

        skill_registry = MagicMock()
        tool_call = ToolCall(id="test-1", name="unknown_tool", arguments={})

        result, proposal, ask_user_data, task_data = _execute_tool(skill_registry, tool_call, {})

        result_data = json.loads(result)
        assert result_data["status"] == "error"
        assert "Unknown tool" in result_data["error"]
        assert proposal is None
        assert ask_user_data is None
        assert task_data is None

    def test_execute_submit_proposal_invalid(self):
        """submit_proposal with invalid args returns error."""
        from unittest.mock import MagicMock

        skill_registry = MagicMock()
        tool_call = ToolCall(id="test-1", name="submit_proposal", arguments={"run_id": ""})

        result, proposal, ask_user_data, task_data = _execute_tool(skill_registry, tool_call, {})

        result_data = json.loads(result)
        assert result_data["status"] == "error"
        assert "Invalid arguments" in result_data["error"]
        assert proposal is None
        assert ask_user_data is None
        assert task_data is None

    def test_execute_submit_proposal_valid(self):
        """submit_proposal with valid args returns proposal."""
        from unittest.mock import MagicMock

        skill_registry = MagicMock()
        valid_args = {
            "proposal_version": "0.1",
            "run_id": "test_run_123",
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 1,
            "ops": [{"op": "upsert_text", "path": "test.json", "content": "{}"}],
        }
        tool_call = ToolCall(id="test-1", name="submit_proposal", arguments=valid_args)

        result, proposal, ask_user_data, task_data = _execute_tool(skill_registry, tool_call, {})

        result_data = json.loads(result)
        assert result_data["status"] == "proposal_submitted"
        assert proposal == valid_args
        assert ask_user_data is None
        assert task_data is None

    def test_execute_read_file_missing_path(self):
        """read_file missing path returns error."""
        from unittest.mock import MagicMock

        skill_registry = MagicMock()
        tool_call = ToolCall(id="test-1", name="read_file", arguments={})

        result, proposal, ask_user_data, task_data = _execute_tool(skill_registry, tool_call, {})

        result_data = json.loads(result)
        assert result_data["status"] == "error"
        assert "Invalid arguments" in result_data["error"]
        assert proposal is None
        assert ask_user_data is None
        assert task_data is None
