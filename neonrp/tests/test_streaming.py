"""Tests for TUI streaming integration (M7-T8)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from neonrp.core.agent_runner import run_agent_agentic
from neonrp.core.dispatcher import dispatch
from neonrp.core.llm import Message, ToolCall, StreamChunk, LLMTurnResult


def _setup_project(tmp_path: Path) -> Path:
    """Setup a minimal project for testing."""
    # Initialize project structure
    neonrp_dir = tmp_path / ".neonrp"
    neonrp_dir.mkdir()

    # Manifest
    manifest = {"version": "0.2", "current_branch": "main", "branches": {"main": {"head_event": 0}}, "entities": {}}
    (neonrp_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # Config
    (neonrp_dir / "config.json").write_text(json.dumps({"llm": {"provider": "stub"}}), encoding="utf-8")

    # Event log
    (neonrp_dir / "events.jsonl").write_text("", encoding="utf-8")

    # World directory
    game_dir = tmp_path / "game"
    game_dir.mkdir()

    # Agent
    agents_dir = tmp_path / "agents" / "test-agent"
    agents_dir.mkdir(parents=True)
    (agents_dir / "agent.json").write_text(json.dumps({"id": "test-agent", "name": "Test Agent", "version": "0.1"}), encoding="utf-8")
    (agents_dir / "system.md").write_text("You are a test agent.", encoding="utf-8")

    return tmp_path


class TestStreamingCallback:
    """Test streaming callback in run_agent_agentic."""

    def test_on_chunk_called_with_streaming_adapter(self, tmp_path: Path):
        """When on_chunk is provided, callback should be called with delta text."""
        root = _setup_project(tmp_path)

        chunks_received = []

        def on_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        # Mock streaming adapter that yields chunks
        mock_adapter = MagicMock()

        def mock_chat_stream(messages, tools=None):
            # Yield a few chunks then finish
            yield StreamChunk(delta="Hello ")
            yield StreamChunk(delta="World!")
            # Return tool call to submit proposal
            yield StreamChunk(
                delta="",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "test-agent",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
                finished=True,
            )

        mock_adapter.chat_stream = mock_chat_stream

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test query",
                on_chunk=on_chunk,
            )

        # Verify text chunks were received
        assert "Hello " in chunks_received
        assert "World!" in chunks_received
        # Note: submit_proposal doesn't trigger tool indicator since loop breaks immediately after

    def test_no_on_chunk_uses_chat_fallback(self, tmp_path: Path):
        """Without on_chunk, should use chat() instead of chat_stream()."""
        root = _setup_project(tmp_path)

        mock_adapter = MagicMock()
        mock_adapter.chat.return_value = LLMTurnResult(
            message=Message(
                role="assistant",
                content="response",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "test-agent",
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
                        "agent_id": "test-agent",
                        "branch": "main",
                        "base_head_event": 0,
                        "ops": [],
                    },
                )
            ],
            finished=False,
        )

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test query",
                on_chunk=None,  # No callback
            )

        # chat() should have been called, not chat_stream()
        mock_adapter.chat.assert_called()
        mock_adapter.chat_stream.assert_not_called()


class TestDispatchPassthrough:
    """Test on_chunk passthrough in dispatcher."""

    def test_dispatch_passes_on_chunk_to_runner(self, tmp_path: Path):
        """dispatch() should pass on_chunk to run_agent_agentic."""
        root = _setup_project(tmp_path)

        chunks_received = []

        def on_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        # Mock adapter for streaming
        mock_adapter = MagicMock()

        def mock_chat_stream(messages, tools=None):
            yield StreamChunk(delta="streaming ")
            yield StreamChunk(delta="test")
            yield StreamChunk(
                delta="",
                tool_calls=[
                    ToolCall(
                        id="tc_1",
                        name="submit_proposal",
                        arguments={
                            "run_id": "test",
                            "agent_id": "test-agent",
                            "branch": "main",
                            "base_head_event": 0,
                            "ops": [],
                        },
                    )
                ],
                finished=True,
            )

        mock_adapter.chat_stream = mock_chat_stream

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            dispatch(
                root=root,
                query="test",
                agentic=True,
                on_chunk=on_chunk,
            )

        # Verify streaming was used
        assert "streaming " in chunks_received
        assert "test" in chunks_received


class TestStreamingErrorHandling:
    """Test error handling during streaming."""

    def test_streaming_error_returns_failure(self, tmp_path: Path):
        """Streaming errors should be caught and returned as failure."""
        root = _setup_project(tmp_path)

        def on_chunk(chunk: str) -> None:
            pass

        mock_adapter = MagicMock()

        def mock_chat_stream(messages, tools=None):
            yield StreamChunk(delta="starting...")
            yield StreamChunk(error="Stream failed")

        mock_adapter.chat_stream = mock_chat_stream

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                on_chunk=on_chunk,
            )

        # Should fail due to streaming error
        assert not result.success
        assert "Stream failed" in (result.error or "")

    def test_streaming_exception_caught(self, tmp_path: Path):
        """Exceptions during streaming should be caught."""
        root = _setup_project(tmp_path)

        def on_chunk(chunk: str) -> None:
            pass

        mock_adapter = MagicMock()

        def mock_chat_stream(messages, tools=None):
            raise RuntimeError("Connection lost")

        mock_adapter.chat_stream = mock_chat_stream

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            result = run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                on_chunk=on_chunk,
            )

        # Should fail gracefully
        assert not result.success
        assert "Connection lost" in (result.error or "")


class TestStreamingToolIndicator:
    """Test tool use indicator during streaming."""

    def test_tool_indicator_sent_on_tool_calls(self, tmp_path: Path):
        """When non-submit tools are called, tool indicator is sent via on_chunk."""
        root = _setup_project(tmp_path)

        chunks_received = []

        def on_chunk(chunk: str) -> None:
            chunks_received.append(chunk)

        mock_adapter = MagicMock()

        # First call - uses read_file tool (non-submit, so tool indicator should appear)
        # Second call - submits proposal
        call_count = [0]

        def mock_chat_stream(messages, tools=None):
            call_count[0] += 1
            if call_count[0] == 1:
                yield StreamChunk(delta="Let me check...")
                # Early notification: tool name arrives before args finish
                yield StreamChunk(tool_call_starts=["read_file"])
                yield StreamChunk(
                    tool_calls=[ToolCall(id="tc_1", name="read_file", arguments={"path": "test.json"})],
                    finished=False,  # Not finished - will process tool
                )
            else:
                yield StreamChunk(delta="Done!")
                yield StreamChunk(tool_call_starts=["submit_proposal"])
                yield StreamChunk(
                    tool_calls=[
                        ToolCall(
                            id="tc_2",
                            name="submit_proposal",
                            arguments={
                                "run_id": "test",
                                "agent_id": "test-agent",
                                "branch": "main",
                                "base_head_event": 0,
                                "ops": [],
                            },
                        )
                    ],
                    finished=True,
                )

        mock_adapter.chat_stream = mock_chat_stream

        with patch("neonrp.core.agent_runner.get_adapter_from_config", return_value=mock_adapter):
            run_agent_agentic(
                root=root,
                agent_id="test-agent",
                query="test",
                on_chunk=on_chunk,
            )

        # Should have received early tool call notification for read_file
        tool_notifications = [c for c in chunks_received if "calling" in c.lower()]
        assert len(tool_notifications) >= 1
        assert "read_file" in "".join(tool_notifications)

