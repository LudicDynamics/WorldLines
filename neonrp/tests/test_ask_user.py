"""Tests for ask_user skill (AskUserQuestion-style schema)."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from neonrp.core.agent_runner import _execute_tool
from neonrp.core.llm import ToolCall
from neonrp.core.skills import SkillRegistry, SKILL_SCHEMAS


class TestAskUserSchema:
    """Tests for ask_user skill schema."""

    def test_schema_exists(self):
        """ask_user schema should be in SKILL_SCHEMAS."""
        assert "ask_user" in SKILL_SCHEMAS

    def test_schema_has_questions(self):
        """Schema should require questions array."""
        schema = SKILL_SCHEMAS["ask_user"]
        assert "questions" in schema["parameters"]["properties"]
        assert "questions" in schema["parameters"]["required"]

    def test_questions_item_has_required_fields(self):
        """Each question item should require question, header, options, multiSelect."""
        schema = SKILL_SCHEMAS["ask_user"]
        item_schema = schema["parameters"]["properties"]["questions"]["items"]
        assert set(item_schema["required"]) == {"question", "header", "options", "multiSelect"}

    def test_option_has_label_and_description(self):
        """Each option should have label and description."""
        schema = SKILL_SCHEMAS["ask_user"]
        option_schema = schema["parameters"]["properties"]["questions"]["items"]["properties"]["options"]["items"]
        assert set(option_schema["required"]) == {"label", "description"}


class TestAskUserSentinel:
    """Tests for ask_user sentinel detection in _execute_tool."""

    def test_returns_sentinel_new_format(self, tmp_path: Path):
        """New structured format should return sentinel with questions list."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="ask_user",
            arguments={
                "questions": [
                    {
                        "question": "What should we do?",
                        "header": "Action",
                        "options": [
                            {"label": "Attack", "description": "Strike the enemy"},
                            {"label": "Defend", "description": "Raise your shield"},
                        ],
                        "multiSelect": False,
                    }
                ]
            },
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is None  # Sentinel indicator
        assert proposal is None
        assert ask_user_data is not None
        assert len(ask_user_data["questions"]) == 1
        q = ask_user_data["questions"][0]
        assert q["question"] == "What should we do?"
        assert q["header"] == "Action"
        assert q["multiSelect"] is False
        assert len(q["options"]) == 2
        assert q["options"][0]["label"] == "Attack"
        assert q["options"][1]["description"] == "Raise your shield"
        assert task_data is None

    def test_returns_sentinel_legacy_format(self, tmp_path: Path):
        """Legacy flat format should be converted to questions list."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="ask_user",
            arguments={"question": "What to do?", "options": ["Attack", "Defend"]},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is None
        assert ask_user_data is not None
        assert len(ask_user_data["questions"]) == 1
        q = ask_user_data["questions"][0]
        assert q["question"] == "What to do?"
        assert q["options"][0]["label"] == "Attack"
        assert q["options"][1]["label"] == "Defend"
        assert task_data is None

    def test_legacy_without_options(self, tmp_path: Path):
        """Legacy format without options should work."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="ask_user",
            arguments={"question": "What is your name?"},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is None
        assert ask_user_data["questions"][0]["question"] == "What is your name?"
        assert ask_user_data["questions"][0]["options"] == []
        assert task_data is None

    def test_empty_questions_rejected(self, tmp_path: Path):
        """Empty questions array should return error."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="ask_user",
            arguments={"questions": []},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is not None  # Error response
        assert ask_user_data is None
        assert task_data is None
        response = json.loads(result)
        assert response["status"] == "error"

    def test_missing_questions_with_empty_question_legacy(self, tmp_path: Path):
        """Empty legacy question should return error."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="ask_user",
            arguments={"question": ""},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is not None
        assert ask_user_data is None
        response = json.loads(result)
        assert response["status"] == "error"

    def test_rejects_control_chars_in_new_format(self, tmp_path: Path):
        """Control chars in ask_user question/options should be rejected."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_bad",
            name="ask_user",
            arguments={
                "questions": [
                    {
                        "question": "Pick one\x7f",
                        "header": "Action",
                        "options": [
                            {"label": "A", "description": "Option A"},
                            {"label": "B", "description": "Option B"},
                        ],
                        "multiSelect": False,
                    }
                ]
            },
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert proposal is None
        assert ask_user_data is None
        assert task_data is None
        payload = json.loads(result or "{}")
        assert payload.get("status") == "error"
        assert "invalid control characters" in str(payload.get("error", ""))


class TestExecuteToolReturnType:
    """Tests for _execute_tool 4-tuple return type."""

    def test_regular_skill_returns_none_for_ask_user(self, tmp_path: Path):
        """Regular skills should return None for ask_user_data."""
        (tmp_path / "game").mkdir()
        (tmp_path / "game" / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="read_file",
            arguments={"path": "game/test.json"},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is not None
        assert proposal is None
        assert ask_user_data is None
        assert task_data is None

    def test_submit_proposal_returns_none_for_ask_user(self, tmp_path: Path):
        """submit_proposal should return None for ask_user_data."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="submit_proposal",
            arguments={
                "proposal_version": "0.1",
                "rationale": "test",
                "ops": [],
                "run_id": "test-run",
                "agent_id": "test",
                "branch": "main",
                "base_head_event": 0,
            },
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is not None
        assert proposal is not None
        assert ask_user_data is None
        assert task_data is None


class TestAskUserCallbackIntegration:
    """Integration tests for ask_user with callback."""

    def test_callback_invoked_with_labels(self):
        """on_ask_user callback should be invoked with question and option labels."""
        callback = MagicMock(return_value="Attack")

        # Simulate what the conversation loop does with new format
        questions = [
            {
                "question": "What to do?",
                "header": "Action",
                "options": [
                    {"label": "Attack", "description": "Strike"},
                    {"label": "Defend", "description": "Block"},
                ],
                "multiSelect": False,
            }
        ]
        answers = {}
        for idx, q in enumerate(questions):
            labels = [o["label"] for o in q["options"]]
            resp = callback(q["question"], labels)
            answers[str(idx)] = str(resp)

        callback.assert_called_once_with("What to do?", ["Attack", "Defend"])
        assert answers == {"0": "Attack"}

    def test_response_as_lean_answers(self):
        """Tool result should be lean answers-only format."""
        answers = {"0": "Attack"}
        result = json.dumps({"answers": answers})

        parsed = json.loads(result)
        assert "answers" in parsed
        assert parsed["answers"]["0"] == "Attack"
        # No redundant question/options in the result
        assert "question" not in parsed
        assert "options" not in parsed
        assert "data" not in parsed

    def test_cancelled_result(self):
        """Cancelled ask_user should return lean status."""
        result = json.dumps({"status": "cancelled"})
        parsed = json.loads(result)
        assert parsed["status"] == "cancelled"
        # No question/options echoed back
        assert "data" not in parsed
