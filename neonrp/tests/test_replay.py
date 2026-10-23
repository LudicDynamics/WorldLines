"""Tests for replay verify command."""

import json
from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.event_log import GameEvent, append_event


class TestReplayVerifyCommand:
    def test_replay_verify_missing_save(self, tmp_path: Path, monkeypatch):
        """Should fail if save doesn't exist."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])

        result = runner.invoke(cli, ["replay", "verify", "--from", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_replay_verify_no_events(self, tmp_path: Path, monkeypatch):
        """Should pass with no events to replay."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        # No events after save, so replay should succeed
        result = runner.invoke(cli, ["replay", "verify", "--from", "baseline"])
        assert result.exit_code == 0
        assert "passed" in result.output.lower() or "Events total: 0" in result.output

    def test_replay_verify_json_output(self, tmp_path: Path, monkeypatch):
        """--json output format."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        result = runner.invoke(cli, ["replay", "verify", "--from", "baseline", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True
        assert data["from_save"] == "baseline"
        assert data["events_total"] == 0

    def test_replay_verify_with_old_save_format(self, tmp_path: Path, monkeypatch):
        """Should fail for old format saves without meta.json."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])

        # Create old-format save without meta.json
        save_dir = tmp_path / ".neonrp" / "saves" / "old-save"
        save_dir.mkdir(parents=True)
        (save_dir / "game").mkdir()
        (save_dir / "game" / "test.json").write_text('{"id": "test"}', encoding="utf-8")

        result = runner.invoke(cli, ["replay", "verify", "--from", "old-save", "--json"])
        assert result.exit_code == 1  # JSON mode also exits 1 on failure
        data = json.loads(result.output)
        assert data["success"] is False
        assert "meta.json" in data["error"]


class TestReplayCore:
    def test_apply_ops_to_staging(self, tmp_path: Path):
        """Test applying ops to staging directory."""
        from neonrp.core.replay import apply_ops_to_staging
        from neonrp.core.proposal import Proposal, UpsertTextOp

        staging_game = tmp_path / "game"
        staging_game.mkdir()

        # Create initial file
        (staging_game / "existing.txt").write_text("old content", encoding="utf-8")

        proposal = Proposal(
            agent_id="test-agent",
            branch="main",
            base_head_event=-1,
            rationale="Test",
            ops=[
                UpsertTextOp(path="new.txt", content="new content"),
                UpsertTextOp(path="existing.txt", content="updated content"),
            ],
            run_id="test-run",
            query="test",
        )

        paths = apply_ops_to_staging(staging_game, proposal)

        assert "new.txt" in paths
        assert "existing.txt" in paths
        assert (staging_game / "new.txt").read_text(encoding="utf-8") == "new content"
        assert (staging_game / "existing.txt").read_text(encoding="utf-8") == "updated content"

    def test_apply_delete_op(self, tmp_path: Path):
        """Test delete operation."""
        from neonrp.core.replay import apply_ops_to_staging
        from neonrp.core.proposal import Proposal, DeleteOp

        staging_game = tmp_path / "game"
        staging_game.mkdir()
        (staging_game / "to_delete.txt").write_text("will be deleted", encoding="utf-8")

        proposal = Proposal(
            agent_id="test-agent",
            branch="main",
            base_head_event=-1,
            rationale="Test",
            ops=[DeleteOp(path="to_delete.txt")],
            run_id="test-run",
            query="test",
        )

        paths = apply_ops_to_staging(staging_game, proposal)

        assert "to_delete.txt" in paths
        assert not (staging_game / "to_delete.txt").exists()

    def test_load_proposal_from_logs_missing(self, tmp_path: Path):
        """Should return None for missing proposal."""
        from neonrp.core.replay import load_proposal_from_logs
        from neonrp.core.paths import get_neonrp_dir

        get_neonrp_dir(tmp_path).mkdir(parents=True, exist_ok=True)

        result = load_proposal_from_logs(tmp_path, "nonexistent-run-id")
        assert result is None

    def test_load_proposal_from_logs_success(self, tmp_path: Path):
        """Should load proposal from logs."""
        from neonrp.core.replay import load_proposal_from_logs

        # Create .neonrp/logs/agents/run-id structure
        logs_dir = tmp_path / ".neonrp" / "logs" / "agents" / "test-run-id"
        logs_dir.mkdir(parents=True)

        proposal_data = {
            "agent_id": "test-agent",
            "branch": "main",
            "base_head_event": 5,
            "rationale": "Test rationale",
            "ops": [{"op": "upsert_text", "path": "test.txt", "content": "test"}],
            "run_id": "test-run-id",
            "query": "test query",
        }
        (logs_dir / "proposal.json").write_text(json.dumps(proposal_data), encoding="utf-8")

        result = load_proposal_from_logs(tmp_path, "test-run-id")

        assert result is not None
        assert result.agent_id == "test-agent"
        assert result.branch == "main"
        assert len(result.ops) == 1


class TestReplayPathTraversal:
    """Path traversal in replay checkout should be rejected."""

    def test_checkout_path_traversal(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        result = runner.invoke(cli, ["replay", "checkout", "--from", "baseline", "--to", "0", "--to-branch", "../x"])
        assert result.exit_code == 1
        # No directory should be created outside branches/
        assert not (tmp_path / "x").exists()

    def test_checkout_path_traversal_json(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        result = runner.invoke(
            cli,
            ["replay", "checkout", "--from", "baseline", "--to", "0", "--to-branch", "../x", "--json"],
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False


class TestReplayVerifyCorrectness:
    """Replay verify must fail when events cannot be replayed."""

    def test_replay_verify_missing_run_id(self, tmp_path: Path, monkeypatch):
        """Event without run_id should cause replay to fail."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        # Append an agent event WITHOUT a run_id in payload
        event = GameEvent(
            id=1,
            type="agent",
            actor="test-agent",
            payload={"query": "test"},  # No run_id
        )
        append_event(tmp_path, "main", event)

        # Update manifest head
        manifest_path = tmp_path / ".neonrp" / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["branches"]["main"]["head_event"] = 1
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

        result = runner.invoke(cli, ["replay", "verify", "--from", "baseline", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False
        assert len(data.get("failed_events", [])) > 0

    def test_replay_verify_missing_proposal(self, tmp_path: Path, monkeypatch):
        """Event with run_id but missing proposal should cause replay to fail."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])
        runner.invoke(cli, ["save", "baseline"])

        # Append event with run_id but no matching proposal.json on disk
        event = GameEvent(
            id=1,
            type="agent",
            actor="test-agent",
            payload={"run_id": "nonexistent-run", "query": "test"},
        )
        append_event(tmp_path, "main", event)

        manifest_path = tmp_path / ".neonrp" / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["branches"]["main"]["head_event"] = 1
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

        result = runner.invoke(cli, ["replay", "verify", "--from", "baseline", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["success"] is False


class TestReplayCheckoutEventLog:
    """Sandbox from replay checkout should have complete event history."""

    def test_checkout_sandbox_has_events_beyond_save(self, tmp_path: Path, monkeypatch):
        """Sandbox event log should include events up to to_event from branch log."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()

        runner.invoke(cli, ["init"])
        runner.invoke(cli, ["game", "new"])  # creates system event id=0
        runner.invoke(cli, ["save", "baseline"])  # save at head_event=0

        # Add events after the save (non-replayable types for simplicity)
        for i in range(1, 4):
            event = GameEvent(
                id=i,
                type="user",
                actor="player",
                payload={"text": f"action {i}"},
            )
            append_event(tmp_path, "main", event)

        # Update manifest head
        manifest_path = tmp_path / ".neonrp" / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["branches"]["main"]["head_event"] = 3
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)

        result = runner.invoke(
            cli,
            ["replay", "checkout", "--from", "baseline", "--to", "3", "--to-branch", "test-sb", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["success"] is True

        # Check that sandbox event log includes all events up to id=3
        # (event 0 from game new + events 1-3 from manual append = 4 total)
        sandbox_events_path = tmp_path / ".neonrp" / "events" / "test-sb.jsonl"
        assert sandbox_events_path.exists()
        lines = [line for line in sandbox_events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 4  # game_new system event + 3 user events
        # Verify event IDs are sequential 0..3
        for i, line in enumerate(lines):
            evt = json.loads(line)
            assert evt["id"] == i
