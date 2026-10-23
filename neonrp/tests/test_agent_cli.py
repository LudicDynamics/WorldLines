"""Tests for agent CLI commands."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli


class TestAgentNew:
    """Tests for agent new command."""

    def test_agent_new_creates_directory(self, tmp_path: Path):
        """Should create agent directory with template files."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["agent", "new", "test-agent"])

            assert result.exit_code == 0
            assert "Created agent 'test-agent'" in result.output

            # Check files exist
            agent_dir = Path("agents/test-agent")
            assert agent_dir.exists()
            assert (agent_dir / "agent.json").exists()
            assert (agent_dir / "system.md").exists()

    def test_agent_new_creates_valid_json(self, tmp_path: Path):
        """Should create valid agent.json with expected fields."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "my-agent"])

            agent_json_path = Path("agents/my-agent/agent.json")
            with open(agent_json_path) as f:
                data = json.load(f)

            assert data["id"] == "my-agent"
            assert data["version"] == "0.1"
            assert data["delegation_mode"] == "one-shot"
            assert "permissions" in data
            assert data["permissions"]["read_globs"] == ["game/**", ".neonrp/manifest.json"]
            assert "write_globs" in data["permissions"]
            # deny_globs is optional in template; required denies are enforced at apply time

    def test_agent_new_always_uses_game_glob_even_if_game_exists(self, tmp_path: Path):
        """Agent template should always target game/ as canonical data root."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True, exist_ok=True)
            Path("game/town/tokyo.json").write_text(
                json.dumps({"id": "tokyo", "kind": "town", "name": "Tokyo"}), encoding="utf-8"
            )

            runner.invoke(cli, ["agent", "new", "legacy-agent"])
            data = json.loads(Path("agents/legacy-agent/agent.json").read_text(encoding="utf-8"))
            assert data["permissions"]["read_globs"] == ["game/**", ".neonrp/manifest.json"]

    def test_agent_new_template_uses_current_task_and_skill_signatures(self, tmp_path: Path):
        """Generated system.md should document current Skill/task tool signatures."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "my-agent"])

            system_md = Path("agents/my-agent/system.md").read_text(encoding="utf-8")
            assert "Skill(skill)" in system_md
            assert "task(agent_id, prompt, resume_run_id?)" in system_md

    def test_agent_new_invalid_id(self, tmp_path: Path):
        """Should reject invalid agent IDs."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Starts with number
            result = runner.invoke(cli, ["agent", "new", "123agent"])
            assert result.exit_code == 1
            assert "Invalid agent ID" in result.output

            # Contains special characters
            result = runner.invoke(cli, ["agent", "new", "agent@test"])
            assert result.exit_code == 1

    def test_agent_new_already_exists(self, tmp_path: Path):
        """Should error if agent already exists."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])

            result = runner.invoke(cli, ["agent", "new", "test-agent"])
            assert result.exit_code == 1
            assert "already exists" in result.output


class TestAgentList:
    """Tests for agent list command."""

    def test_agent_list_empty(self, tmp_path: Path):
        """Should handle empty agents directory."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["agent", "list"])
            assert result.exit_code == 0
            assert "No agents" in result.output

    def test_agent_list_shows_agents(self, tmp_path: Path):
        """Should list created agents."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "agent-a"])
            runner.invoke(cli, ["agent", "new", "agent-b"])

            result = runner.invoke(cli, ["agent", "list"])
            assert result.exit_code == 0
            assert "agent-a" in result.output
            assert "agent-b" in result.output
            assert "2 agent(s)" in result.output

    def test_agent_list_json(self, tmp_path: Path):
        """Should output JSON format."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])

            result = runner.invoke(cli, ["agent", "list", "--json"])
            assert result.exit_code == 0

            data = json.loads(result.output)
            assert data["count"] == 1
            assert data["agents"][0]["id"] == "test-agent"


class TestAgentShow:
    """Tests for agent show command."""

    def test_agent_show_displays_details(self, tmp_path: Path):
        """Should display agent details."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])

            result = runner.invoke(cli, ["agent", "show", "test-agent"])
            assert result.exit_code == 0
            assert "test-agent" in result.output
            assert "Permissions" in result.output

    def test_agent_show_json(self, tmp_path: Path):
        """Should output JSON format."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])

            result = runner.invoke(cli, ["agent", "show", "test-agent", "--json"])
            assert result.exit_code == 0

            data = json.loads(result.output)
            assert data["id"] == "test-agent"
            assert "permissions" in data

    def test_agent_show_not_found(self, tmp_path: Path):
        """Should error if agent not found."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["agent", "show", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.output


class TestAgentPath:
    """Tests for agent path command."""

    def test_agent_path_prints_path(self, tmp_path: Path):
        """Should print agent directory path."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["agent", "new", "test-agent"])

            result = runner.invoke(cli, ["agent", "path", "test-agent"])
            assert result.exit_code == 0
            assert "agents" in result.output
            assert "test-agent" in result.output

    def test_agent_path_not_found(self, tmp_path: Path):
        """Should error if agent not found."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["agent", "path", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.output


def _setup_project_with_agent(runner, agent_id="test-agent"):
    """Helper: init project, create agent, return agent dir path."""
    runner.invoke(cli, ["init"])
    runner.invoke(cli, ["agent", "new", agent_id])
    return Path(f"agents/{agent_id}")


class TestAgentRun:
    """Tests for agent run command (M3-T4)."""

    def test_agent_run_stub_produces_proposal(self, tmp_path: Path):
        """agent run --provider stub should produce proposal + diff logs."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "do nothing",
                    "--provider",
                    "stub",
                ],
            )

            assert result.exit_code == 0, result.output
            assert "Agent Run:" in result.output
            assert "Provider: stub" in result.output
            assert "Logs saved to:" in result.output

    def test_agent_run_stub_json_output(self, tmp_path: Path):
        """agent run --provider stub --json should output structured JSON."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "do nothing",
                    "--provider",
                    "stub",
                    "--json",
                ],
            )

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["agent_id"] == "test-agent"
            assert data["provider"] == "stub"
            assert "run_id" in data
            assert "proposal_path" in data
            assert "diff_path" in data
            assert "summary" in data
            assert data["applied"] is False

    def test_agent_run_stub_logs_saved(self, tmp_path: Path):
        """agent run should save input.json, llm_raw.txt, proposal.json, diff.patch, validation.json."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "test logs",
                    "--provider",
                    "stub",
                    "--json",
                ],
            )

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            logs_dir = Path(data["logs_dir"])

            assert (logs_dir / "input.json").exists()
            assert (logs_dir / "llm_raw.txt").exists()
            assert (logs_dir / "proposal.json").exists()
            assert (logs_dir / "diff.patch").exists()
            assert (logs_dir / "validation.json").exists()

            # Verify input.json contents
            with open(logs_dir / "input.json") as f:
                input_log = json.load(f)
            assert input_log["agent_id"] == "test-agent"
            assert input_log["query"] == "test logs"
            assert input_log["provider"] == "stub"

            # Verify validation.json exists and has expected structure
            with open(logs_dir / "validation.json") as f:
                validation_log = json.load(f)
            assert "success" in validation_log

    def test_agent_run_stub_fixture(self, tmp_path: Path):
        """agent run --provider stub --fixture should use provided proposal."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            # Create a fixture proposal with an actual operation
            fixture = {
                "proposal_version": "0.1",
                "run_id": "fixture-run",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "add entity",
                "rationale": "Test fixture",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "character/hero.json",
                        "content": json.dumps({"id": "hero", "kind": "character", "name": "Hero"}, indent=2),
                    }
                ],
            }
            fixture_path = Path("fixture_proposal.json")
            with open(fixture_path, "w") as f:
                json.dump(fixture, f)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "add entity",
                    "--provider",
                    "stub",
                    "--fixture",
                    str(fixture_path),
                    "--json",
                ],
            )

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["success"] is True
            assert data["summary"]["total"] > 0

    def test_agent_run_not_found(self, tmp_path: Path):
        """agent run should fail with exit code 1 if agent not found."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "nonexistent",
                    "--query",
                    "test",
                    "--provider",
                    "stub",
                ],
            )

            assert result.exit_code == 1

    def test_agent_run_not_found_json(self, tmp_path: Path):
        """agent run --json should output error JSON if agent not found."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "nonexistent",
                    "--query",
                    "test",
                    "--provider",
                    "stub",
                    "--json",
                ],
            )

            assert result.exit_code == 1
            data = json.loads(result.output)
            assert data["success"] is False
            assert "not found" in data["error"]

    def test_agent_run_invalid_fixture_proposal(self, tmp_path: Path):
        """agent run should fail with exit code 1 on invalid proposal from LLM."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            # Create a fixture with invalid proposal (missing required fields)
            fixture_path = Path("bad_fixture.json")
            with open(fixture_path, "w") as f:
                json.dump({"invalid": "proposal"}, f)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "bad proposal",
                    "--provider",
                    "stub",
                    "--fixture",
                    str(fixture_path),
                ],
            )

            assert result.exit_code == 1

    def test_agent_run_unsupported_provider(self, tmp_path: Path):
        """agent run should exit code 2 on unsupported provider."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "test",
                    "--provider",
                    "unknown_provider",
                ],
            )

            assert result.exit_code == 2


class TestAgentRunApply:
    """Tests for agent run --apply (M3-T5 preview)."""

    def test_agent_run_apply_with_fixture(self, tmp_path: Path):
        """agent run --apply should apply proposal and create event."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)

            # Create game directory for upsert target
            Path("game/character").mkdir(parents=True, exist_ok=True)

            # Create fixture with a valid upsert operation
            fixture = {
                "proposal_version": "0.1",
                "run_id": "apply-test",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "add character",
                "rationale": "Testing apply",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "character/npc.json",
                        "content": json.dumps(
                            {
                                "id": "npc",
                                "kind": "character",
                                "name": "Test NPC",
                                "tags": ["test"],
                                "summary": "A test NPC",
                            },
                            indent=2,
                        ),
                    }
                ],
            }
            fixture_path = Path("apply_fixture.json")
            with open(fixture_path, "w") as f:
                json.dump(fixture, f)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "add character",
                    "--provider",
                    "stub",
                    "--fixture",
                    str(fixture_path),
                    "--apply",
                ],
            )

            assert result.exit_code == 0, result.output
            assert "Applied successfully" in result.output

            # Verify the file was created
            assert Path("game/character/npc.json").exists()

    def test_agent_run_apply_json_output(self, tmp_path: Path):
        """agent run --apply --json should include event_id."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            _setup_project_with_agent(runner)
            Path("game/character").mkdir(parents=True, exist_ok=True)

            fixture = {
                "proposal_version": "0.1",
                "run_id": "apply-json-test",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "add char",
                "rationale": "Testing",
                "ops": [
                    {
                        "op": "upsert_text",
                        "path": "character/warrior.json",
                        "content": json.dumps(
                            {
                                "id": "warrior",
                                "kind": "character",
                                "name": "Warrior",
                                "tags": [],
                                "summary": "A warrior",
                            },
                            indent=2,
                        ),
                    }
                ],
            }
            fixture_path = Path("apply_fixture.json")
            with open(fixture_path, "w") as f:
                json.dump(fixture, f)

            result = runner.invoke(
                cli,
                [
                    "agent",
                    "run",
                    "test-agent",
                    "--query",
                    "add char",
                    "--provider",
                    "stub",
                    "--fixture",
                    str(fixture_path),
                    "--apply",
                    "--json",
                ],
            )

            assert result.exit_code == 0, result.output
            data = json.loads(result.output)
            assert data["applied"] is True
            assert data["event_id"] is not None
