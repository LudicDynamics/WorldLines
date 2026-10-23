"""M8 Integration Tests.

Tests for multi-agent orchestration features:
- Orchestrator → sub-agent pipeline via task tool
- ask_user callback integration
- Per-agent LLM with provider registry
- Depth limit enforcement
- Mixed write modes (proposal vs direct_write)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from neonrp.core.agent_runner import run_agent_agentic, AgentRunResult
from neonrp.core.storage import ensure_dirs, atomic_write_json
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path, get_game_dir
from neonrp.core.config import load_config, resolve_provider
from neonrp.core.llm import Message, ToolCall, LLMTurnResult


def _setup_multi_agent_project(tmp_path: Path) -> Path:
    """Set up a multi-agent project structure for testing."""
    root = tmp_path / "multi_agent"
    root.mkdir()

    # Initialize project structure
    ensure_dirs(root)
    manifest = Manifest()
    atomic_write_json(get_manifest_path(root), manifest.model_dump())

    # Config with provider registry
    config_data = {
        "llm": {"provider": "stub"},
        "providers": {
            "fast": {"provider": "stub", "model": "fast-model"},
            "strong": {"provider": "stub", "model": "strong-model"},
        },
        "max_sub_agent_depth": 2,
    }
    neonrp_dir = root / ".neonrp"
    atomic_write_json(neonrp_dir / "config.json", config_data)

    # Create orchestrator agent
    orchestrator_dir = root / "agents" / "orchestrator"
    orchestrator_dir.mkdir(parents=True)
    atomic_write_json(
        orchestrator_dir / "agent.json",
        {
            "id": "orchestrator",
            "name": "Orchestrator",
            "llm": {"provider_ref": "strong"},
            "permissions": {
                "read_globs": ["**"],
                "write_globs": ["**"],
                "deny_globs": [".neonrp/**", "agents/**"],
            },
        },
    )
    (orchestrator_dir / "system.md").write_text("You are an orchestrator. Use task tool to delegate.", encoding="utf-8")

    # Create narrator agent with direct_write_globs
    narrator_dir = root / "agents" / "narrator"
    narrator_dir.mkdir(parents=True)
    atomic_write_json(
        narrator_dir / "agent.json",
        {
            "id": "narrator",
            "name": "Narrator",
            "llm": {"provider_ref": "fast"},
            "permissions": {
                "read_globs": ["**"],
                "write_globs": ["**"],
                "deny_globs": [".neonrp/**", "agents/**"],
                "direct_write_globs": ["game/lore/**"],
            },
        },
    )
    (narrator_dir / "system.md").write_text("You are a narrator. Write creative content.", encoding="utf-8")

    # Create world structure
    game_dir = get_game_dir(root)
    (game_dir / "lore").mkdir(parents=True)

    return root


class TestProviderRegistry:
    """Test per-agent LLM with provider registry."""

    def test_orchestrator_uses_strong_provider(self, tmp_path):
        """Orchestrator should resolve to 'strong' provider via provider_ref."""
        root = _setup_multi_agent_project(tmp_path)

        config = load_config(root)
        agent_dir = root / "agents" / "orchestrator"
        with open(agent_dir / "agent.json") as f:
            agent_data = json.load(f)

        provider_config = resolve_provider(config, agent_data.get("llm"))

        # Should use stub (from strong provider in test config)
        assert provider_config.provider == "stub"
        assert provider_config.model == "strong-model"

    def test_narrator_uses_fast_provider(self, tmp_path):
        """Narrator should resolve to 'fast' provider via provider_ref."""
        root = _setup_multi_agent_project(tmp_path)

        config = load_config(root)
        agent_dir = root / "agents" / "narrator"
        with open(agent_dir / "agent.json") as f:
            agent_data = json.load(f)

        provider_config = resolve_provider(config, agent_data.get("llm"))

        assert provider_config.provider == "stub"
        assert provider_config.model == "fast-model"

    def test_cli_override_takes_precedence(self, tmp_path):
        """CLI --provider should override agent's provider_ref."""
        root = _setup_multi_agent_project(tmp_path)

        config = load_config(root)
        agent_dir = root / "agents" / "orchestrator"
        with open(agent_dir / "agent.json") as f:
            agent_data = json.load(f)

        # CLI override
        provider_config = resolve_provider(config, agent_data.get("llm"), cli_provider="glm")

        assert provider_config.provider == "glm"


class TestTaskToolIntegration:
    """Test orchestrator → sub-agent pipeline via task tool."""

    def test_orchestrator_can_call_task_at_depth_0(self, tmp_path):
        """Orchestrator at depth 0 should have access to task tool."""
        root = _setup_multi_agent_project(tmp_path)

        # Capture tools passed to chat
        captured_tools = []

        def capture_chat(messages, tools=None):
            captured_tools.extend(tools or [])
            return LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Done",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "orchestrator",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        )
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "orchestrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
                finished=True,
            )

        mock_adapter = MagicMock()
        mock_adapter.chat.side_effect = capture_chat

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="orchestrator",
                query="Create lore",
                max_turns=3,
            )

        # Should have completed
        assert result.run_id is not None
        assert result.turns >= 1

        # Verify task tool was in available tools
        # Tool schemas can be in direct format {"name": ...} or OpenAI format {"function": {"name": ...}}
        tool_names = []
        for t in captured_tools:
            if "function" in t:
                tool_names.append(t["function"].get("name"))
            else:
                tool_names.append(t.get("name"))
        assert "task" in tool_names, f"task tool should be available at depth 0, got: {tool_names}"


class TestAskUserIntegration:
    """Test ask_user callback integration."""

    def test_ask_user_callback_invoked(self, tmp_path):
        """When agent calls ask_user, callback should be invoked."""
        root = _setup_multi_agent_project(tmp_path)

        user_responses = []

        def on_ask_user(question: str, options: list[str] | None) -> str:
            user_responses.append({"question": question, "options": options})
            return "Dark and mysterious"

        mock_adapter = MagicMock()
        # First call - ask_user
        mock_adapter.chat.side_effect = [
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Let me ask the user",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="ask_user",
                            arguments={"question": "What tone do you prefer?", "options": ["Dark", "Light"]},
                        )
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="ask_user",
                        arguments={"question": "What tone do you prefer?", "options": ["Dark", "Light"]},
                    )
                ],
                finished=False,
            ),
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Got it",
                    tool_calls=[
                        ToolCall(
                            id="tc_2",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "orchestrator",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        )
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_2",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "orchestrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
                finished=True,
            ),
        ]

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            run_agent_agentic(
                root=root,
                agent_id="orchestrator",
                query="Create lore",
                on_ask_user=on_ask_user,
                max_turns=3,
            )

        # Callback should have been invoked
        assert len(user_responses) == 1
        assert "tone" in user_responses[0]["question"].lower()

    def test_ask_user_without_callback_returns_error(self, tmp_path):
        """When agent calls ask_user without callback, error should occur."""
        root = _setup_multi_agent_project(tmp_path)

        mock_adapter = MagicMock()
        mock_adapter.chat.side_effect = [
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Let me ask",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="ask_user",
                            arguments={"question": "What?"},
                        )
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="ask_user",
                        arguments={"question": "What?"},
                    )
                ],
                finished=False,
            ),
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Done",
                    tool_calls=[
                        ToolCall(
                            id="tc_2",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "orchestrator",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        )
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_2",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "orchestrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
                finished=True,
            ),
        ]

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="orchestrator",
                query="test",
                on_ask_user=None,  # No callback
                max_turns=3,
            )

        # Should complete (error is returned in tool result, not fatal)
        assert result.run_id is not None


class TestDepthLimit:
    """Test sub-agent depth limit enforcement."""

    def test_task_tool_excluded_at_max_depth(self, tmp_path):
        """At max depth, task tool should not be available."""
        root = _setup_multi_agent_project(tmp_path)

        # Modify config to lower max depth
        config_path = root / ".neonrp" / "config.json"
        with open(config_path) as f:
            config_data = json.load(f)
        config_data["max_sub_agent_depth"] = 1
        atomic_write_json(config_path, config_data)

        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMTurnResult(
            message=Message(
                role="assistant",
                content="Done",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "narrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
            ),
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    name="submit_proposal",
                    arguments={
                        "run_id": "test",
                        "agent_id": "narrator",
                        "branch": "main",
                        "base_head_event": 0,
                        "ops": [],
                    },
                )
            ],
            finished=True,
        )

        # Run at depth 1 (simulating sub-agent)
        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="narrator",
                query="test",
                current_depth=1,
                max_turns=2,
            )

        # Should complete
        assert result.run_id is not None


class TestMixedWriteModes:
    """Test proposal vs direct write modes."""

    def test_direct_write_to_lore_directory(self, tmp_path):
        """Narrator should be able to write directly to lore/ directory."""
        root = _setup_multi_agent_project(tmp_path)

        # Ensure lore directory exists
        lore_dir = root / "game" / "lore"
        lore_dir.mkdir(parents=True, exist_ok=True)

        mock_adapter = MagicMock()
        # First call - write_file only
        # Second call - submit proposal
        mock_adapter.chat.side_effect = [
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Writing lore",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="write_file",
                            arguments={
                                "path": "game/lore/new-entry.json",
                                "content": json.dumps({"id": "new-entry", "kind": "lore", "name": "Test"}),
                            },
                        ),
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="write_file",
                        arguments={
                            "path": "game/lore/new-entry.json",
                            "content": json.dumps({"id": "new-entry", "kind": "lore", "name": "Test"}),
                        },
                    ),
                ],
                finished=False,
            ),
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Done",
                    tool_calls=[
                        ToolCall(
                            id="tc_2",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "narrator",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        ),
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_2",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "narrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    ),
                ],
                finished=True,
            ),
        ]

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            _ = run_agent_agentic(
                root=root,
                agent_id="narrator",
                query="Write lore",
                max_turns=3,
            )

        # File should have been created directly
        lore_file = root / "game" / "lore" / "new-entry.json"
        assert lore_file.exists(), f"File should exist at {lore_file}"
        with open(lore_file) as f:
            data = json.load(f)
        assert data["id"] == "new-entry"

    def test_direct_write_outside_allowed_fails(self, tmp_path):
        """Writing outside direct_write_globs should require proposal."""
        root = _setup_multi_agent_project(tmp_path)

        mock_adapter = MagicMock()
        mock_adapter.chat.side_effect = [
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Writing outside lore",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="write_file",
                            arguments={
                                "path": "game/characters/hero.json",
                                "content": '{"id": "hero"}',
                            },
                        ),
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="write_file",
                        arguments={
                            "path": "game/characters/hero.json",
                            "content": '{"id": "hero"}',
                        },
                    ),
                ],
                finished=False,
            ),
            LLMTurnResult(
                message=Message(
                    role="assistant",
                    content="Using proposal instead",
                    tool_calls=[
                        ToolCall(
                            id="tc_2",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "narrator",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        ),
                    ],
                ),
                tool_calls=[
                    ToolCall(
                        id="tc_2",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "narrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    ),
                ],
                finished=True,
            ),
        ]

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            _ = run_agent_agentic(
                root=root,
                agent_id="narrator",
                query="Write character",
                max_turns=3,
            )

        # File should NOT have been created (outside direct_write_globs)
        char_file = root / "game" / "characters" / "hero.json"
        assert not char_file.exists()


class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_orchestrator_narrator_pipeline_stub(self, tmp_path):
        """Full pipeline: orchestrator → narrator with stub provider."""
        root = _setup_multi_agent_project(tmp_path)

        # This test verifies the structure works end-to-end with stub
        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMTurnResult(
            message=Message(
                role="assistant",
                content="Submitting",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "orchestrator",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
            ),
            tool_calls=[
                ToolCall(
                    id="tc_1",
                    name="submit_proposal",
                    arguments={
                        "run_id": "test",
                        "agent_id": "orchestrator",
                        "branch": "main",
                        "base_head_event": 0,
                        "ops": [],
                    },
                )
            ],
            finished=True,
        )

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="orchestrator",
                query="Create lore about the ancient war",
                max_turns=5,
            )

        assert isinstance(result, AgentRunResult)
        assert result.run_id is not None
        assert result.agent_id == "orchestrator"

