"""Tests for core/dispatcher.py - agent routing."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.dispatcher import (
    AgentSpec,
    dispatch,
    load_agent_specs,
    match_tags,
    match_triggers,
    select_agent,
)


class TestAgentSpec:
    """Tests for AgentSpec dataclass."""

    def test_from_json_minimal(self):
        """Should create AgentSpec from minimal JSON."""
        data = {"id": "test-agent"}
        spec = AgentSpec.from_json(data)
        assert spec.id == "test-agent"
        assert spec.priority == 0
        assert spec.tags == []
        assert spec.triggers == []

    def test_from_json_full(self):
        """Should create AgentSpec from full JSON."""
        data = {
            "id": "narrator",
            "name": "Narrator Agent",
            "description": "Handles story narration",
            "priority": 10,
            "tags": ["story", "narrative"],
            "triggers": ["^tell me", "^narrate"],
        }
        spec = AgentSpec.from_json(data)
        assert spec.id == "narrator"
        assert spec.name == "Narrator Agent"
        assert spec.priority == 10
        assert spec.tags == ["story", "narrative"]
        assert spec.triggers == ["^tell me", "^narrate"]


class TestMatchTriggers:
    """Tests for match_triggers function."""

    def test_exact_match(self):
        """Should match exact trigger pattern."""
        result = match_triggers("create a character", ["create.*character"])
        assert result == "create.*character"

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        result = match_triggers("CREATE a character", ["create"])
        assert result == "create"

    def test_no_match(self):
        """Should return None for no match."""
        result = match_triggers("update an item", ["create", "delete"])
        assert result is None

    def test_invalid_regex_skipped(self):
        """Should skip invalid regex patterns."""
        result = match_triggers("test", ["[invalid regex", "test"])
        assert result == "test"


class TestMatchTags:
    """Tests for match_tags function."""

    def test_single_tag(self):
        """Should match single tag."""
        result = match_tags("I need to create a character", ["character"])
        assert result == ["character"]

    def test_multiple_tags(self):
        """Should match multiple tags."""
        result = match_tags("Create a story about an item", ["story", "item", "quest"])
        assert "story" in result
        assert "item" in result
        assert "quest" not in result

    def test_case_insensitive(self):
        """Should match case-insensitively."""
        result = match_tags("Create a CHARACTER", ["character"])
        assert result == ["character"]


class TestSelectAgent:
    """Tests for select_agent function."""

    def test_explicit_agent_id(self):
        """Should return explicit agent ID if specified."""
        specs = {
            "agent1": AgentSpec(id="agent1"),
            "agent2": AgentSpec(id="agent2"),
        }
        selected, trigger, tags, candidates = select_agent("any query", specs, "agent2")
        assert selected == "agent2"
        assert trigger is None
        assert tags == []

    def test_trigger_match(self):
        """Should select agent by trigger pattern."""
        specs = {
            "narrator": AgentSpec(id="narrator", triggers=["^tell me"]),
            "creator": AgentSpec(id="creator", triggers=["^create"]),
        }
        selected, trigger, tags, candidates = select_agent("tell me a story", specs)
        assert selected == "narrator"
        assert trigger == "^tell me"

    def test_tag_match(self):
        """Should select agent by tag match."""
        specs = {
            "story": AgentSpec(id="story", tags=["story", "narrative"]),
            "item": AgentSpec(id="item", tags=["item", "inventory"]),
        }
        selected, trigger, tags, candidates = select_agent("I want a story", specs)
        assert selected == "story"
        assert "story" in tags

    def test_priority_fallback(self):
        """Should fall back to highest priority."""
        specs = {
            "low": AgentSpec(id="low", priority=1),
            "high": AgentSpec(id="high", priority=10),
        }
        selected, trigger, tags, candidates = select_agent("random query", specs)
        assert selected == "high"

    def test_nonexistent_agent(self):
        """Should return None for nonexistent agent ID."""
        specs = {"agent1": AgentSpec(id="agent1")}
        selected, trigger, tags, candidates = select_agent("any", specs, "nonexistent")
        assert selected is None


class TestLoadAgentSpecs:
    """Tests for load_agent_specs function."""

    def test_load_from_project(self, tmp_path: Path):
        """Should load agent specs from agents directory."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            specs = load_agent_specs(root)
            assert "test-agent" in specs
            assert specs["test-agent"].id == "test-agent"

    def test_empty_project(self, tmp_path: Path):
        """Should return empty dict for missing agents dir."""
        specs = load_agent_specs(tmp_path)
        assert specs == {}


class TestDispatch:
    """Tests for dispatch function."""

    def test_dispatch_explicit_agent(self, tmp_path: Path):
        """Should dispatch to explicit agent."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = dispatch(
                root=root,
                query="test query",
                agent_id="test-agent",
                provider="stub",
            )

            assert result.success is True
            assert result.agent_id == "test-agent"
            assert result.run_result is not None

    def test_dispatch_no_agents(self, tmp_path: Path):
        """Should return error when no agents exist."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            result = dispatch(root=root, query="test")

            assert result.success is False
            assert "No agents found" in result.error

    def test_dispatch_agent_not_found(self, tmp_path: Path):
        """Should return error for nonexistent agent."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = dispatch(
                root=root,
                query="test",
                agent_id="nonexistent",
            )

            assert result.success is False
            assert "not found" in result.error

    def test_dispatch_with_apply(self, tmp_path: Path):
        """Should apply proposal when requested."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            fixture = root / "fixture.json"
            fixture_content = {
                "proposal_version": "0.1",
                "run_id": "apply_run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "test",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "test/item.json",
                        "content": '{"id": "item", "kind": "test", "name": "Test"}',
                    }
                ],
            }
            fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

            result = dispatch(
                root=root,
                query="test",
                agent_id="test-agent",
                provider="stub",
                fixture_path=str(fixture),
                do_apply=True,
            )

            assert result.success is True
            assert result.run_result.apply_result is not None
            assert result.run_result.apply_result.success is True

    def test_dispatch_agentic_mode(self, tmp_path: Path):
        """Should use agentic loop when requested."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = dispatch(
                root=root,
                query="test",
                agent_id="test-agent",
                provider="stub",
                agentic=True,
            )

            assert result.success is True
            assert result.run_result.turns >= 1
