"""Tests for core/agent_runner.py - extracted agent run orchestration."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.agent_runner import run_agent, run_agent_agentic, AgentRunResult


def _setup_project(tmp_path: Path) -> Path:
    """Helper to set up an initialized NeonRP project."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["agent", "new", "test-agent"])
        return Path(cwd)


class TestAgentRunResult:
    """Tests for AgentRunResult dataclass."""

    def test_result_default_values(self):
        """AgentRunResult should have sensible defaults."""
        result = AgentRunResult(run_id="test-123", success=True)
        assert result.run_id == "test-123"
        assert result.success is True
        assert result.agent_id == ""
        assert result.provider == ""
        assert result.proposal is None
        assert result.diff_content == ""
        assert result.summary == {}
        assert result.apply_result is None
        assert result.error is None
        assert result.logs_dir is None
        assert result.turns == 0  # M6 field


class TestRunAgent:
    """Tests for run_agent core function."""

    def test_run_agent_not_found(self, tmp_path: Path):
        """run_agent should return error for nonexistent agent."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            result = run_agent(
                root=root,
                agent_id="nonexistent",
                query="test query",
                provider="stub",
            )

            assert result.success is False
            assert "not found" in result.error

    def test_run_agent_stub_success(self, tmp_path: Path):
        """run_agent with stub provider should succeed."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = run_agent(
                root=root,
                agent_id="test-agent",
                query="create a test character",
                provider="stub",
            )

            assert result.success is True
            assert result.agent_id == "test-agent"
            assert result.provider == "stub"
            assert result.proposal is not None
            assert result.logs_dir is not None
            assert result.logs_dir.exists()

    def test_run_agent_with_fixture(self, tmp_path: Path):
        """run_agent should use fixture file when provided."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            # Create fixture with actual operations
            fixture = root / "test_fixture.json"
            fixture_content = {
                "proposal_version": "0.1",
                "run_id": "fixture_run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "test",
                "rationale": "testing fixture",
                "ops": [{"op": "upsert_text", "path": "character/hero.json", "content": '{"id": "hero"}'}],
            }
            fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

            result = run_agent(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
                fixture_path=str(fixture),
            )

            assert result.success is True
            assert result.proposal is not None
            assert len(result.proposal.ops) == 1
            assert result.diff_content != ""

    def test_run_agent_apply(self, tmp_path: Path):
        """run_agent with do_apply should apply the proposal."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            # Create fixture to apply
            fixture = root / "test_fixture.json"
            fixture_content = {
                "proposal_version": "0.1",
                "run_id": "apply_run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "create hero",
                "rationale": "testing apply",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "character/hero.json",
                        "content": '{"id": "hero", "kind": "character", "name": "Test Hero"}',
                    }
                ],
            }
            fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

            result = run_agent(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
                fixture_path=str(fixture),
                do_apply=True,
            )

            assert result.success is True
            assert result.apply_result is not None
            assert result.apply_result.success is True

            # Verify file was created
            hero_file = root / "game" / "character" / "hero.json"
            assert hero_file.exists()
            hero_data = json.loads(hero_file.read_text(encoding="utf-8"))
            assert hero_data["id"] == "hero"

    def test_run_agent_not_initialized(self, tmp_path: Path):
        """run_agent should return error if project not initialized."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create agent directory without init
            root = Path.cwd()
            (root / "agents" / "test-agent").mkdir(parents=True)
            (root / "agents" / "test-agent" / "agent.json").write_text(
                '{"id": "test-agent", "kind": "narrator", "permissions": {}}'
, encoding="utf-8")

            result = run_agent(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
            )

        assert result.success is False
        assert "not found" in result.error.lower() or "not initialized" in result.error.lower()

    def test_run_agent_invalid_provider(self, tmp_path: Path):
        """run_agent should return error for unknown provider."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = run_agent(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="unknown_provider",
            )

            assert result.success is False
            assert "adapter" in result.error.lower()


class TestRunAgentAgentic:
    """Tests for run_agent_agentic multi-turn loop (M6)."""

    def test_agentic_stub_success(self, tmp_path: Path):
        """run_agent_agentic with stub should complete in one turn."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="create a test character",
                provider="stub",
            )

            assert result.success is True
            assert result.agent_id == "test-agent"
            assert result.provider == "stub"
            assert result.proposal is not None
            assert result.turns >= 1  # At least one turn
            assert result.logs_dir is not None

    def test_agentic_with_fixture(self, tmp_path: Path):
        """run_agent_agentic should use fixture for proposal."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            fixture = root / "agentic_fixture.json"
            fixture_content = {
                "proposal_version": "0.1",
                "run_id": "agentic_run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "test",
                "rationale": "agentic test",
                "ops": [{"op": "upsert_text", "path": "item/sword.json", "content": '{"id": "sword"}'}],
            }
            fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
                fixture_path=str(fixture),
            )

            assert result.success is True
            assert len(result.proposal.ops) == 1
            assert result.proposal.ops[0].path == "item/sword.json"

    def test_agentic_apply(self, tmp_path: Path):
        """run_agent_agentic with do_apply should apply changes."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            fixture = root / "apply_fixture.json"
            fixture_content = {
                "proposal_version": "0.1",
                "run_id": "apply_run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "create quest",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "quest/main.json",
                        "content": '{"id": "main", "kind": "quest", "name": "Main Quest", "title": "Main Quest"}',
                    }
                ],
            }
            fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
                fixture_path=str(fixture),
                do_apply=True,
            )

            assert result.success is True
            assert result.apply_result is not None
            assert result.apply_result.success is True

            quest_file = root / "game" / "quest" / "main.json"
            assert quest_file.exists()

    def test_agentic_not_found(self, tmp_path: Path):
        """run_agent_agentic should return error for nonexistent agent."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            root = Path.cwd()

            result = run_agent_agentic(
                root=root,
                agent_id="nonexistent",
                query="test",
                provider="stub",
            )

            assert result.success is False
            assert "not found" in result.error

    def test_agentic_logs_conversation(self, tmp_path: Path):
        """run_agent_agentic should save conversation log."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])
            root = Path.cwd()

            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                provider="stub",
            )

            assert result.success is True
            assert result.logs_dir is not None

            # Check conversation log exists
            conv_log = result.logs_dir / "conversation.json"
            assert conv_log.exists()

            conv_data = json.loads(conv_log.read_text(encoding="utf-8"))
            assert len(conv_data) >= 1
            assert conv_data[0]["turn"] == 1
