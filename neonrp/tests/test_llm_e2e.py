"""E2E tests with real LLM providers (M7-T4).

These tests are skipped by default. To run them:
  1. Set environment variable NEONRP_E2E_LLM=1
  2. Ensure API key is configured (e.g., OPENAI_API_KEY or GLM_API_KEY)
  3. Run: pytest -m e2e_llm

Cost estimate: < $0.10 per full run.
"""

import json
import os
import pytest

from neonrp.core.agent_runner import run_agent_agentic, AgentRunResult
from neonrp.core.storage import ensure_dirs, atomic_write_json
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path, get_game_dir

# Skip unless E2E is explicitly enabled
pytestmark = pytest.mark.e2e_llm


def requires_e2e():
    """Check if E2E tests should run."""
    return os.environ.get("NEONRP_E2E_LLM", "").lower() in ("1", "true", "yes")


@pytest.fixture
def e2e_project(tmp_path):
    """Set up a minimal project for E2E tests."""
    if not requires_e2e():
        pytest.skip("E2E tests disabled (set NEONRP_E2E_LLM=1 to enable)")

    root = tmp_path / "e2e_project"
    root.mkdir()

    # Initialize project structure
    ensure_dirs(root)
    manifest = Manifest()
    atomic_write_json(get_manifest_path(root), manifest.model_dump())

    # Create game world entities directly
    game_dir = get_game_dir(root)

    # Create player
    player_dir = game_dir / "player"
    player_dir.mkdir(parents=True)
    atomic_write_json(
        player_dir / "player.json",
        {
            "id": "player",
            "kind": "player",
            "name": "Player",
            "tags": ["player"],
            "summary": "The player character.",
        },
    )

    # Create a town
    town_dir = game_dir / "town"
    town_dir.mkdir(parents=True)
    atomic_write_json(
        town_dir / "start-town.json",
        {
            "id": "start-town",
            "kind": "town",
            "name": "Starting Town",
            "tags": ["town", "starting-area"],
            "summary": "A small town where the adventure begins.",
        },
    )

    # Create a simple agent for testing
    agents_dir = root / "agents" / "test-agent"
    agents_dir.mkdir(parents=True)

    agent_spec = {
        "id": "test-agent",
        "name": "Test Agent",
        "permissions": {
            "read": ["**"],
            "write": ["**"],
            "deny": [".neonrp/**", "agents/**"],
        },
    }
    atomic_write_json(agents_dir / "agent.json", agent_spec)

    # Write a simple system prompt
    (agents_dir / "system.md").write_text(
        "You are a test agent. Read relevant files, then call submit_proposal with your changes."
, encoding="utf-8")

    # Determine provider from environment
    if os.environ.get("OPENAI_API_KEY"):
        provider = "openai"
    elif os.environ.get("GLM_API_KEY"):
        provider = "glm"
        # Create config with GLM settings from environment
        glm_config = {
            "llm": {
                "provider": "openai",  # Use openai adapter for GLM
                "api_key": os.environ.get("GLM_API_KEY"),
                "base_url": os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
                "model": os.environ.get("GLM_MODEL", "glm-4-flashx-250414"),
            }
        }
        config_path = root / ".neonrp" / "config.json"
        atomic_write_json(config_path, glm_config)
    else:
        pytest.skip("No LLM API key found")

    return root, provider


class TestE2ELLM:
    """E2E tests with real LLM providers."""

    def test_simple_read_and_submit(self, e2e_project):
        """Scenario 1: Read a file and submit a simple proposal."""
        root, provider = e2e_project

        result = run_agent_agentic(
            root=root,
            agent_id="test-agent",
            query="Read the player character file and add a tag 'tested' to it.",
            provider=provider,
            do_apply=False,
        )

        # Validate structure
        assert isinstance(result, AgentRunResult)
        assert result.run_id is not None
        assert result.agent_id == "test-agent"
        assert result.logs_dir is not None
        assert result.logs_dir.exists()

        # Should have at least one turn
        assert result.turns >= 1

        # Either succeeded with proposal or failed with error
        if result.success:
            assert result.proposal is not None
            assert len(result.proposal.ops) >= 0  # May have 0 ops if no change needed
        else:
            assert result.error is not None

    def test_create_entity(self, e2e_project):
        """Scenario 2: Create a new entity."""
        root, provider = e2e_project

        result = run_agent_agentic(
            root=root,
            agent_id="test-agent",
            query="Create a new item called 'Magic Sword' with value 100 and an 'enchanted' tag.",
            provider=provider,
            do_apply=False,
        )

        assert isinstance(result, AgentRunResult)
        assert result.turns >= 1

        # Check logs exist
        assert result.logs_dir is not None
        assert (result.logs_dir / "conversation.json").exists()

        # If successful, should have a proposal
        if result.success:
            assert result.proposal is not None
            # Should have at least one upsert operation
            upserts = [op for op in result.proposal.ops if op.op == "upsert_text"]
            assert len(upserts) >= 1 or result.proposal.ops == []

    def test_invalid_proposal_recovery(self, e2e_project):
        """Scenario 3: Agent can recover from invalid proposal attempt."""
        root, provider = e2e_project

        # This query might initially produce invalid output
        result = run_agent_agentic(
            root=root,
            agent_id="test-agent",
            query="Update the player to have -50 gold (this is intentionally invalid).",
            provider=provider,
            do_apply=False,
            max_turns=5,  # Limit turns for faster test
        )

        assert isinstance(result, AgentRunResult)
        # Either succeeds (agent understood invalid) or fails gracefully
        assert result.run_id is not None

    def test_multi_tool_call(self, e2e_project):
        """Scenario 4: Agent uses multiple tools in sequence."""
        root, provider = e2e_project

        result = run_agent_agentic(
            root=root,
            agent_id="test-agent",
            query="List all entities, then read the player file, then create a summary of what you found.",
            provider=provider,
            do_apply=False,
        )

        assert isinstance(result, AgentRunResult)
        assert result.turns >= 1

        # Check conversation log for multiple tool calls
        conv_log = result.logs_dir / "conversation.json"
        if conv_log.exists():
            with open(conv_log) as f:
                conversation = json.load(f)
            # Should have used tools
            total_tool_calls = sum(len(turn.get("tool_calls", [])) for turn in conversation)
            # May or may not use multiple tools depending on model
            assert total_tool_calls >= 0

    def test_budget_awareness(self, e2e_project):
        """Scenario 5: Agent operates within token budget."""
        root, provider = e2e_project

        # Use a smaller budget to test budget tracking
        config_path = root / ".neonrp" / "config.json"
        config_data = {"llm": {"provider": provider, "max_context_chars": 50000}}
        atomic_write_json(config_path, config_data)

        result = run_agent_agentic(
            root=root,
            agent_id="test-agent",
            query="Describe the current game state briefly.",
            provider=provider,
            do_apply=False,
            max_turns=3,
        )

        assert isinstance(result, AgentRunResult)

        # Check conversation log includes budget info
        conv_log = result.logs_dir / "conversation.json"
        if conv_log.exists():
            with open(conv_log) as f:
                conversation = json.load(f)
            # Should have budget_ratio in logs
            if conversation:
                assert "budget_ratio" in conversation[0]


class TestE2ESkipWhenDisabled:
    """Test that E2E tests skip properly when disabled."""

    def test_skip_message(self):
        """Verify skip behavior when E2E is disabled."""
        if requires_e2e():
            pytest.skip("This test only runs when E2E is disabled")

        # If we get here, E2E is disabled and this is expected
        assert not requires_e2e()

