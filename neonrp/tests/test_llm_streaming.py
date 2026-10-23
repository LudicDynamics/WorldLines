"""Tests for M6-T7 LLM streaming functionality."""

from types import SimpleNamespace

from neonrp.core.llm import LLMTurnResult, Message, StreamChunk, ToolCall
from neonrp.core.llm_openai import _finalize_streamed_arguments, _merge_streamed_arguments, _tool_calls_need_recovery


class TestStreamChunk:
    """Tests for StreamChunk dataclass."""

    def test_stream_chunk_defaults(self):
        """Verify StreamChunk default values."""
        chunk = StreamChunk()
        assert chunk.delta == ""
        assert chunk.tool_calls is None
        assert chunk.finished is False
        assert chunk.usage == {}
        assert chunk.error is None
        assert chunk.retryable is False

    def test_stream_chunk_with_delta(self):
        """Verify StreamChunk with delta content."""
        chunk = StreamChunk(delta="Hello, ")
        assert chunk.delta == "Hello, "
        assert chunk.finished is False

    def test_stream_chunk_finished(self):
        """Verify StreamChunk final chunk."""
        tool_call = ToolCall(id="call_123", name="submit_proposal", arguments={"ops": []})
        chunk = StreamChunk(
            tool_calls=[tool_call],
            finished=True,
            usage={"total_tokens": 100},
        )
        assert chunk.finished is True
        assert len(chunk.tool_calls) == 1
        assert chunk.usage["total_tokens"] == 100

    def test_stream_chunk_error(self):
        """Verify StreamChunk with error."""
        chunk = StreamChunk(error="API connection failed", finished=True)
        assert chunk.error == "API connection failed"
        assert chunk.finished is True


class TestStubAdapterStreaming:
    """Tests for StubAdapter.chat_stream()."""

    def test_stub_chat_stream_yields_chunks(self):
        """Verify StubAdapter.chat_stream yields chunks."""
        from neonrp.core.llm_stub import StubAdapter

        adapter = StubAdapter()
        messages = [
            Message(role="system", content="You are a test agent."),
            Message(role="user", content="Hello"),
        ]

        chunks = list(adapter.chat_stream(messages))

        # Should have at least one chunk
        assert len(chunks) >= 1

        # Last chunk should be finished
        assert chunks[-1].finished is True

    def test_stub_chat_stream_has_tool_call(self):
        """Verify StubAdapter.chat_stream yields tool calls on finish."""
        from neonrp.core.llm_stub import StubAdapter

        adapter = StubAdapter()
        messages = [
            Message(role="system", content="You are a test agent."),
            Message(role="user", content='{"run_id": "test_run", "agent_id": "test-agent", "query": "test"}'),
        ]

        # 真实 agent 路径总是带 tools;tools=None 现在是纯对话面
        # (ask_soul/心跳/直聊,返回确定性文本,2026-08-14 stub 修复)。
        chunks = list(
            adapter.chat_stream(messages, tools=[{"name": "submit_proposal"}])
        )
        final_chunk = chunks[-1]

        assert final_chunk.finished is True
        assert final_chunk.tool_calls is not None
        assert len(final_chunk.tool_calls) == 1
        assert final_chunk.tool_calls[0].name == "submit_proposal"

    def test_stub_chat_stream_accumulates_delta(self):
        """Verify delta accumulation (for adapters that yield content)."""
        from neonrp.core.llm_stub import StubAdapter

        adapter = StubAdapter()
        messages = [
            Message(role="user", content="Hello"),
        ]

        chunks = list(adapter.chat_stream(messages))

        # Accumulate all deltas
        _full_content = "".join(c.delta for c in chunks)  # noqa: F841

        # Final chunk has tool calls
        final = chunks[-1]
        assert final.finished is True


class TestOpenAIAdapterStreamingInterface:
    """Tests for OpenAIAdapter.chat_stream interface (mock-based)."""

    def test_openai_adapter_has_chat_stream(self):
        """Verify OpenAIAdapter has chat_stream method."""
        from neonrp.core.llm_openai import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o-mini")
        assert hasattr(adapter, "chat_stream")
        assert callable(adapter.chat_stream)

    def test_openai_adapter_chat_stream_error_handling(self):
        """Verify OpenAIAdapter.chat_stream handles missing API key gracefully."""
        from neonrp.core.llm_openai import OpenAIAdapter
        import os

        # Temporarily clear API keys
        old_openai = os.environ.pop("OPENAI_API_KEY", None)
        old_neonrp = os.environ.pop("NEONRP_LLM_API_KEY", None)

        try:
            adapter = OpenAIAdapter(model="gpt-4o-mini")
            messages = [Message(role="user", content="test")]

            chunks = list(adapter.chat_stream(messages))

            # Should yield error chunk
            assert len(chunks) == 1
            assert chunks[0].finished is True
            assert chunks[0].error is not None
            # May fail due to missing openai package OR missing API key
            assert "API key" in chunks[0].error or "openai package" in chunks[0].error
        finally:
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai
            if old_neonrp:
                os.environ["NEONRP_LLM_API_KEY"] = old_neonrp


class TestStreamingProtocol:
    """Tests for streaming protocol compatibility."""

    def test_llm_adapter_protocol_has_chat_stream(self):
        """Verify LLMAdapter protocol includes chat_stream."""
        from neonrp.core.llm import LLMAdapter
        import inspect

        # Check protocol has chat_stream method
        members = inspect.getmembers(LLMAdapter)
        method_names = [name for name, _ in members]
        assert "chat_stream" in method_names

    def test_get_adapter_returns_streaming_capable(self):
        """Verify get_adapter returns adapters with chat_stream."""
        from neonrp.core.llm import get_adapter

        adapter = get_adapter("stub")
        assert hasattr(adapter, "chat_stream")
        assert callable(adapter.chat_stream)


class TestOpenAIStreamingArgumentMerge:
    """Tests for merging streamed tool-call arguments from compatible providers."""

    def test_merge_delta_fragments(self):
        merged = ""
        for fragment in ['{"path":"a', 'b","content":"he', 'llo"}']:
            merged = _merge_streamed_arguments(merged, fragment)
        assert merged == '{"path":"ab","content":"hello"}'

    def test_merge_cumulative_fragments(self):
        merged = ""
        for fragment in ['{"path":"a', '{"path":"ab","content":"h', '{"path":"ab","content":"hello"}']:
            merged = _merge_streamed_arguments(merged, fragment)
        assert merged == '{"path":"ab","content":"hello"}'

    def test_merge_duplicate_fragment_no_growth(self):
        merged = _merge_streamed_arguments('{"a":1', '{"a":1')
        assert merged == '{"a":1'

    def test_finalize_streamed_arguments_preserves_repeated_delta_fragments(self):
        fragments = ['{"path":"game', "/player", "/player", '.json"}']
        assert _finalize_streamed_arguments(fragments) == '{"path":"game/player/player.json"}'

    def test_finalize_streamed_arguments_picks_cumulative_snapshot(self):
        fragments = ['{"path":"a', '{"path":"ab","content":"h', '{"path":"ab","content":"hello"}']
        assert _finalize_streamed_arguments(fragments) == '{"path":"ab","content":"hello"}'


class TestOpenAIStreamingRecovery:
    """Tests for streamed tool-call recovery path."""

    def test_tool_calls_need_recovery_heuristics(self):
        assert _tool_calls_need_recovery([ToolCall(id="1", name="write_file", arguments={})]) is True
        assert _tool_calls_need_recovery([ToolCall(id="1", name="", arguments={"path": "a"})]) is True
        assert _tool_calls_need_recovery([ToolCall(id="1", name="write_file", arguments={"raw": "{bad"})]) is True
        assert _tool_calls_need_recovery([ToolCall(id="1", name="write_file", arguments={"path": "a"})]) is False

    def test_chat_stream_recovers_incomplete_tool_calls_via_chat(self, monkeypatch):
        """When stream ends with incomplete tool args, adapter.chat() recovery should be used."""
        from neonrp.core.llm_openai import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="test-key")

        # Minimal stream that emits an incomplete tool call and ends with finish_reason=length.
        stream_chunks = [
            SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="tc_1",
                                    function=SimpleNamespace(name="write_file", arguments=""),
                                )
                            ],
                        ),
                    )
                ],
            ),
            SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(finish_reason="length", delta=SimpleNamespace(content=None, tool_calls=None))],
            ),
        ]

        monkeypatch.setattr(adapter, "_get_client", lambda: object())
        monkeypatch.setattr(adapter, "_call_with_retry", lambda _api_call, error_prefix="": iter(stream_chunks))
        monkeypatch.setattr(
            adapter,
            "chat",
            lambda messages, tools=None: LLMTurnResult(
                tool_calls=[
                    ToolCall(
                        id="tc_recovered",
                        name="write_file",
                        arguments={"path": "snake-game.html", "content": "<!DOCTYPE html><html></html>"},
                    )
                ]
            ),
        )

        chunks = list(adapter.chat_stream([Message(role="user", content="test")], tools=[]))
        final = chunks[-1]

        assert final.finished is True
        assert final.tool_calls is not None
        assert len(final.tool_calls) == 1
        assert final.tool_calls[0].id == "tc_recovered"
        assert final.tool_calls[0].arguments["path"] == "snake-game.html"

    def test_chat_stream_keeps_repeated_adjacent_argument_fragments(self, monkeypatch):
        """Delta streams with repeated adjacent tokens should not lose a segment."""
        from neonrp.core.llm_openai import OpenAIAdapter

        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="test-key")

        stream_chunks = [
            SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="tc_1",
                                    function=SimpleNamespace(name="edit_file", arguments='{"path":"game'),
                                )
                            ],
                        ),
                    )
                ],
            ),
            SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments="/player"),
                                )
                            ],
                        ),
                    )
                ],
            ),
            SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments="/player"),
                                )
                            ],
                        ),
                    )
                ],
            ),
            SimpleNamespace(
                usage=None,
                choices=[
                    SimpleNamespace(
                        finish_reason=None,
                        delta=SimpleNamespace(
                            content=None,
                            reasoning_content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id=None,
                                    function=SimpleNamespace(name=None, arguments='.json","old_text":"x","new_text":"y"}'),
                                )
                            ],
                        ),
                    )
                ],
            ),
            SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(finish_reason="tool_calls", delta=SimpleNamespace(content=None, tool_calls=None))],
            ),
        ]

        monkeypatch.setattr(adapter, "_get_client", lambda: object())
        monkeypatch.setattr(adapter, "_call_with_retry", lambda _api_call, error_prefix="": iter(stream_chunks))

        chunks = list(adapter.chat_stream([Message(role="user", content="test")], tools=[]))
        final = chunks[-1]

        assert final.finished is True
        assert final.tool_calls is not None
        assert final.tool_calls[0].arguments["path"] == "game/player/player.json"
