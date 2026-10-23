"""Tests for game scaffolding (M3-T7)."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli


class TestGameNewCLI:
    def test_game_new_requires_init(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["game", "new", "--json"])

            assert result.exit_code == 1
            payload = json.loads(result.output)
            assert payload["success"] is False

    def test_game_new_creates_game_and_validates(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["game", "new"])

            assert result.exit_code == 0, result.output
            assert Path("game/player/player.json").exists()
            assert Path("game/town/start-town.json").exists()
            assert Path("game/npc/old-sage.json").exists()
            assert Path("game/meta/game-start.json").exists()
            assert Path("rules/game_entity.schema.json").exists()
            assert Path("rules/domain_rules.sample.json").exists()
            assert Path("rules/README.md").exists()
            assert Path("skills/entity-authoring/SKILL.md").exists()
            narrator = json.loads(Path("agents/narrator/agent.json").read_text(encoding="utf-8"))
            assert narrator["permissions"]["read_globs"] == ["game/**", ".neonrp/manifest.json"]
            assert "must_not_do" in narrator
            assert "directly handle town/dungeon operations" in narrator["must_not_do"]
            narrator_system = Path("agents/narrator/system.md").read_text(encoding="utf-8")
            assert "Hard Constraints" in narrator_system
            assert "Do NOT call `ask_user`." in narrator_system
            assert 'task(agent_id="town-agent"' in narrator_system
            town_agent = json.loads(Path("agents/town-agent/agent.json").read_text(encoding="utf-8"))
            dungeon_agent = json.loads(Path("agents/dungeon-agent/agent.json").read_text(encoding="utf-8"))
            runtime_contract = json.loads(Path(".neonrp/runtime_contract.json").read_text(encoding="utf-8"))
            assert town_agent["delegation_mode"] == "sticky"
            assert dungeon_agent["delegation_mode"] == "sticky"
            assert "location" in dungeon_agent["sticky_domain_kinds"]
            assert "game/meta/active-agent.json" in town_agent["permissions"].get("deny_globs", [])
            assert "game/meta/active-agent.json" in dungeon_agent["permissions"].get("deny_globs", [])
            assert runtime_contract["routing"]["domain_agent_map"]["location"] == "dungeon-agent"
            assert runtime_contract["router"]["execution_mode"] == "orchestrator"

            validate_result = runner.invoke(cli, ["validate"])
            assert validate_result.exit_code == 0, validate_result.output

            index_result = runner.invoke(cli, ["index", "build"])
            assert index_result.exit_code == 0, index_result.output

    def test_game_new_conflict_without_force(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["game", "new"])

            result = runner.invoke(cli, ["game", "new"])

            assert result.exit_code == 1

    def test_game_new_force_overwrites(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["game", "new"])

            Path("game/player/player.json").write_text(
                json.dumps({"id": "player", "kind": "player", "name": "Override"}),
                encoding="utf-8",
            )

            result = runner.invoke(cli, ["game", "new", "--force"])

            assert result.exit_code == 0, result.output
            data = json.loads(Path("game/player/player.json").read_text(encoding="utf-8"))
            assert data["name"] == "Player"

    def test_game_new_force_always_uses_game_root(self, tmp_path: Path):
        """Scaffolding should always write canonical game/ paths."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("game/town").mkdir(parents=True, exist_ok=True)
            Path("game/town/legacy-town.json").write_text(
                json.dumps({"id": "legacy-town", "kind": "town", "name": "Legacy Town"}),
                encoding="utf-8",
            )

            result = runner.invoke(cli, ["game", "new", "--force"])
            assert result.exit_code == 0, result.output

            start = json.loads(Path("game/meta/game-start.json").read_text(encoding="utf-8"))
            assert all(p.startswith("game/") for p in start["startup"]["read_first"])
            narrator = json.loads(Path("agents/narrator/agent.json").read_text(encoding="utf-8"))
            assert narrator["permissions"]["read_globs"] == ["game/**", ".neonrp/manifest.json"]

    def test_game_new_force_removes_invalid_stale_entities(self, tmp_path: Path):
        """--force should rebuild game even when stale invalid entities exist."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["game", "new"])

            bad_path = Path("game/misc/broken.json")
            bad_path.parent.mkdir(parents=True, exist_ok=True)
            bad_path.write_text("{}", encoding="utf-8")

            result = runner.invoke(cli, ["game", "new", "--force"])

            assert result.exit_code == 0, result.output
            assert not bad_path.exists()
            validate_result = runner.invoke(cli, ["validate"])
            assert validate_result.exit_code == 0, validate_result.output

    def test_game_new_json_output(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["game", "new", "--json"])

            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert payload["success"] is True
            assert sorted(payload["files"]) == sorted(
                [
                    ".neonrp/runtime_contract.json",
                    "meta/game-start.json",
                    "meta/active-agent.json",
                    "meta/quest-the-sage-seal.json",
                    "npc/old-sage.json",
                    "npc/forest-goblin.json",
                    "npc/cave-goblin.json",
                    "npc/goblin-chief.json",
                    "player/player.json",
                    "town/start-town.json",
                    "item/health-potion.json",
                    "item/iron-sword.json",
                    "location/forest-path.json",
                    "dungeon/dark-cave.json",
                    "agents/narrator/agent.json",
                    "agents/narrator/system.md",
                    "agents/town-agent/agent.json",
                    "agents/dungeon-agent/agent.json",
                    "rules/game_entity.schema.json",
                    "rules/domain_rules.sample.json",
                    "rules/README.md",
                    "skills/entity-authoring/SKILL.md",
                ]
            )

    def test_game_new_does_not_overwrite_existing_rules_samples(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["game", "new"])

            marker = '{"custom": true}'
            Path("rules/domain_rules.sample.json").write_text(marker, encoding="utf-8")

            result = runner.invoke(cli, ["game", "new", "--force"])
            assert result.exit_code == 0, result.output
            assert Path("rules/domain_rules.sample.json").read_text(encoding="utf-8") == marker

    def test_game_new_does_not_overwrite_existing_skill_samples(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["game", "new"])

            marker = "---\nname: entity-authoring\ndescription: custom\n---\ncustom"
            Path("skills/entity-authoring/SKILL.md").write_text(marker, encoding="utf-8")

            result = runner.invoke(cli, ["game", "new", "--force"])
            assert result.exit_code == 0, result.output
            assert Path("skills/entity-authoring/SKILL.md").read_text(encoding="utf-8") == marker

    def test_game_new_unknown_template(self, tmp_path: Path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["game", "new", "--template", "nope"])

            assert result.exit_code == 1
            assert "unknown template" in result.output.lower()

    def test_game_new_soul_template_scaffolds_playthrough_m20(self, tmp_path: Path):
        # M20: the human player is a non-soul entity. stoneford-elena has NO
        # role=player soul, so NO player_projection.json is scaffolded (the
        # dead M16-E "player IS a soul" contract). playthrough.json carries
        # players[] instead; elena/rowan are independent NPC souls.
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(
                cli,
                ["game", "new", "--template", "stoneford-elena", "--json"],
            )

            assert result.exit_code == 0, result.output
            payload = json.loads(result.output)
            assert "souls/" in payload["files"]
            assert ".neonrp/playthrough.json" in payload["files"]
            assert ".neonrp/player_projection.json" not in payload["files"]
            assert not Path(".neonrp/player_projection.json").exists()
            assert Path("souls/elena-si-elena0001/soul.md").exists()
            assert Path("game/player/controller.json").exists()
            pt = json.loads(Path(".neonrp/playthrough.json").read_text(encoding="utf-8"))
            assert [s["role"] for s in pt["souls"]] == ["npc", "npc"]
            assert pt["players"][0]["pid"] == "player"
            assert pt["players"][0]["state_path"] == "game/player"


class TestSystemProposalLogging:
    """System proposal (game new, import) should produce full log set."""

    def test_game_new_creates_standard_logs(self, tmp_path: Path):
        """game new should log input.json, proposal.json, diff.patch, validation.json, apply.json."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["game", "new"])
            assert result.exit_code == 0, result.output

            logs_root = Path(".neonrp") / "logs" / "agents"
            assert logs_root.exists()

            # Find the run directory (should be exactly one)
            run_dirs = list(logs_root.iterdir())
            assert len(run_dirs) == 1, f"Expected 1 run dir, got {len(run_dirs)}"
            run_dir = run_dirs[0]

            # All standard log files must exist
            for filename in ("input.json", "proposal.json", "diff.patch", "validation.json", "apply.json"):
                log_file = run_dir / filename
                assert log_file.exists(), f"Missing log file: {filename}"

            # input.json must contain command field
            with open(run_dir / "input.json") as f:
                input_data = json.load(f)
            assert "command" in input_data
            assert input_data["command"] == "game_new"

            # apply.json must indicate success
            with open(run_dir / "apply.json") as f:
                apply_data = json.load(f)
            assert apply_data["success"] is True
