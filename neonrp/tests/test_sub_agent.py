"""Tests for sub-agent orchestration (M8-T4)."""

from pathlib import Path


from neonrp.core.agent_runner import _build_task_tool_schema, _execute_tool
from neonrp.core.llm import ToolCall
from neonrp.core.skills import get_skill_schemas, SkillRegistry


class TestTaskSchema:
    """Tests for dynamically built task schema."""

    def test_schema_has_required_fields(self, tmp_path: Path):
        """Schema should require agent_id and prompt."""
        schema = _build_task_tool_schema(tmp_path)
        required = schema["parameters"]["required"]
        assert "agent_id" in required
        assert "prompt" in required

    def test_schema_has_resume_run_id(self, tmp_path: Path):
        """Schema should have optional resume_run_id."""
        schema = _build_task_tool_schema(tmp_path)
        props = schema["parameters"]["properties"]
        assert "resume_run_id" in props

    def test_schema_lists_no_agents_when_empty(self, tmp_path: Path):
        """When no agents exist, description says so."""
        schema = _build_task_tool_schema(tmp_path)
        assert "No sub-agents configured" in schema["description"]

    def test_schema_lists_available_agents(self, tmp_path: Path):
        """When agents exist, they appear in the description."""
        import json

        agent_dir = tmp_path / "agents" / "writer"
        agent_dir.mkdir(parents=True)
        (agent_dir / "agent.json").write_text(
            json.dumps({"name": "Story Writer", "description": "Writes stories"}),
            encoding="utf-8",
        )
        schema = _build_task_tool_schema(tmp_path)
        assert "writer (Story Writer)" in schema["description"]
        assert "Writes stories" in schema["description"]
        assert schema["parameters"]["properties"]["agent_id"]["enum"] == ["writer"]

    def test_schema_agent_id_has_no_enum_when_empty(self, tmp_path: Path):
        """No enum should be emitted when there are no discovered agents."""
        schema = _build_task_tool_schema(tmp_path)
        assert "enum" not in schema["parameters"]["properties"]["agent_id"]


class TestTaskSentinel:
    """Tests for task sentinel detection."""

    def test_returns_task_data(self, tmp_path: Path):
        """task tool should return task_data sentinel."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="task",
            arguments={"agent_id": "writer", "prompt": "Write a story"},
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert result is None  # Sentinel indicator
        assert proposal is None
        assert ask_user_data is None
        assert task_data is not None
        assert task_data["agent_id"] == "writer"
        assert task_data["prompt"] == "Write a story"
        assert task_data["resume_run_id"] is None

    def test_task_with_resume_run_id(self, tmp_path: Path):
        """task tool includes resume_run_id when provided."""
        registry = SkillRegistry(
            root=tmp_path,
            run_id="test-run",
            agent_id="test-agent",
            read_globs=["**"],
            deny_globs=[],
        )

        tool_call = ToolCall(
            id="call_123",
            name="task",
            arguments={
                "agent_id": "writer",
                "prompt": "Continue the story",
                "resume_run_id": "prev-run-123",
            },
        )

        result, proposal, ask_user_data, task_data = _execute_tool(registry, tool_call, {})

        assert task_data["resume_run_id"] == "prev-run-123"


class TestDepthFiltering:
    """Tests for task tool filtering at depth."""

    def test_task_in_schemas_at_depth_0(self, tmp_path: Path):
        """task should be in tool_schemas at depth 0."""
        schemas = get_skill_schemas()
        schemas.append(_build_task_tool_schema(tmp_path))
        names = [s["name"] for s in schemas]
        assert "task" in names

    def test_task_filtering_at_max_depth(self, tmp_path: Path):
        """task should be filtered at depth >= max_depth - 1."""
        tool_schemas = get_skill_schemas()
        tool_schemas.append(_build_task_tool_schema(tmp_path))
        current_depth = 1
        max_depth = 2

        if current_depth >= max_depth - 1:
            tool_schemas = [s for s in tool_schemas if s.get("name") != "task"]

        names = [s["name"] for s in tool_schemas]
        assert "task" not in names
