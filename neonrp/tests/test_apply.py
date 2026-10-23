"""Tests for apply engine."""

from pathlib import Path

from click.testing import CliRunner

from neonrp.cli import cli
from neonrp.core.apply import apply_proposal, generate_run_id
from neonrp.core.proposal import Proposal, UpsertTextOp
from neonrp.core.event_log import read_events


class TestGenerateRunId:
    """Tests for run ID generation."""

    def test_format(self):
        """Should generate run IDs in correct format."""
        run_id = generate_run_id()

        # Check format: YYYYMMDDTHHMMSSZ_6hex
        parts = run_id.split("_")
        assert len(parts) == 2
        assert len(parts[0]) == 16  # YYYYMMDDTHHMMSSZ
        assert parts[0].endswith("Z")
        assert len(parts[1]) == 6  # 6 hex chars

    def test_uniqueness(self):
        """Should generate unique run IDs."""
        ids = [generate_run_id() for _ in range(10)]
        assert len(set(ids)) == 10


class TestApplyProposal:
    """Tests for apply_proposal function."""

    def _setup_project(self, tmp_path: Path) -> Path:
        """Helper to set up a minimal NeonRP project."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as cwd:
            runner.invoke(cli, ["init"])
            return Path(cwd)

    def test_apply_new_file(self, tmp_path: Path):
        """Should create new files."""
        root = self._setup_project(tmp_path)

        # Create world directory
        (root / "game" / "town").mkdir(parents=True)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Add a new town",
            ops=[
                UpsertTextOp(
                    op="upsert_text", path="town/new.json", content='{"id": "new", "kind": "town", "name": "New Town"}'
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)

        assert result.success
        assert "town/new.json" in result.applied_paths
        assert (root / "game" / "town" / "new.json").exists()

    def test_apply_permission_denied(self, tmp_path: Path):
        """Should reject unauthorized writes."""
        root = self._setup_project(tmp_path)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Try to write to agents",
            ops=[UpsertTextOp(op="upsert_text", path="agents/attack.json", content="{}")],
        )

        permissions = {"write_globs": ["game/**"], "deny_globs": ["agents/**", ".neonrp/**"]}
        result = apply_proposal(root, proposal, permissions)

        assert not result.success
        assert "Permission denied" in result.error

    def test_apply_base_head_mismatch(self, tmp_path: Path):
        """Should reject stale proposals."""
        root = self._setup_project(tmp_path)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=999,  # Wrong head event
            query="Stale proposal",
            ops=[],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)

        assert not result.success
        assert "mismatch" in result.error.lower()

    def test_apply_validation_failure(self, tmp_path: Path):
        """Should reject proposals that fail validation."""
        root = self._setup_project(tmp_path)
        (root / "game" / "town").mkdir(parents=True)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Create invalid entity",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="town/bad.json",
                    # Missing required fields: id, kind, name
                    content='{"invalid": true}',
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)

        assert not result.success
        assert result.validation_errors

    def test_apply_domain_rule_validation_failure(self, tmp_path: Path):
        """Should reject proposals that violate enabled domain rules."""
        root = self._setup_project(tmp_path)
        (root / "game" / "player").mkdir(parents=True)
        (root / "game" / "town").mkdir(parents=True)
        (root / "game" / "town" / "start-town.json").write_text(
            '{"id":"start-town","kind":"town","name":"Start Town"}',
            encoding="utf-8",
        )

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Create invalid hp",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="player/hero.json",
                    content='{"id":"hero","kind":"player","name":"Hero","location":"missing-town"}',
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)
        assert not result.success
        assert result.error == "Game rules validation failed"
        assert any(err.get("rule") == "location_exists" for err in result.validation_errors)

    def test_apply_can_disable_domain_rule_validation(self, tmp_path: Path):
        """Should allow domain rule violations when domain validation is disabled."""
        root = self._setup_project(tmp_path)
        (root / "game" / "player").mkdir(parents=True)
        (root / "game" / "town").mkdir(parents=True)
        (root / "game" / "town" / "start-town.json").write_text(
            '{"id":"start-town","kind":"town","name":"Start Town"}',
            encoding="utf-8",
        )
        (root / ".neonrp" / "config.json").write_text(
            '{"rules":{"enable_domain_validation":false}}',
            encoding="utf-8",
        )

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Create negative hp with rules disabled",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="player/hero.json",
                    content='{"id":"hero","kind":"player","name":"Hero","location":"missing-town"}',
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)
        assert result.success

    def test_apply_dry_run(self, tmp_path: Path):
        """Should not commit in dry run mode."""
        root = self._setup_project(tmp_path)
        (root / "game" / "town").mkdir(parents=True)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Dry run test",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="town/dryrun.json",
                    content='{"id": "dryrun", "kind": "town", "name": "Dry Run"}',
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions, dry_run=True)

        assert result.success
        assert result.event_id is None  # No event in dry run
        assert not (root / "game" / "town" / "dryrun.json").exists()

    def test_apply_appends_event(self, tmp_path: Path):
        """Should append event log on success."""
        root = self._setup_project(tmp_path)
        (root / "game" / "town").mkdir(parents=True)

        proposal = Proposal(
            agent_id="test-agent",
            run_id=generate_run_id(),
            branch="main",
            base_head_event=-1,
            query="Event test",
            ops=[
                UpsertTextOp(
                    op="upsert_text",
                    path="town/event.json",
                    content='{"id": "event", "kind": "town", "name": "Event Test"}',
                )
            ],
        )

        permissions = {"write_globs": ["**"], "deny_globs": []}
        result = apply_proposal(root, proposal, permissions)

        assert result.success
        assert result.event_id == 0

        # Check event log
        events = read_events(root, "main")
        assert len(events) == 1
        assert events[0].type == "agent"
        assert events[0].actor == "test-agent"

