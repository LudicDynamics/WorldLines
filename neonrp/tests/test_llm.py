"""Tests for LLM adapter modules."""

import json
from pathlib import Path

from neonrp.core.llm import LLMResponse, LLMTurnResult, Message, ToolCall, extract_proposal_json, get_adapter
from neonrp.core.llm_stub import StubAdapter


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_success_property_true(self):
        """Should return True when proposal_text is present and no error."""
        response = LLMResponse(proposal_text='{"test": 1}', raw_output='{"test": 1}')
        assert response.success is True

    def test_success_property_false_on_error(self):
        """Should return False when error is present."""
        response = LLMResponse(error="something went wrong")
        assert response.success is False

    def test_success_property_false_on_missing_proposal(self):
        """Should return False when proposal_text is None."""
        response = LLMResponse(raw_output="some output but no proposal")
        assert response.success is False


class TestExtractProposalJson:
    """Tests for extract_proposal_json function."""

    def test_direct_json(self):
        """Should extract direct JSON."""
        raw = '{"agent_id": "test", "ops": []}'
        result = extract_proposal_json(raw)
        assert result == raw

    def test_json_in_markdown(self):
        """Should extract JSON from markdown code block."""
        raw = """Here's the proposal:
```json
{"agent_id": "test", "ops": []}
```
"""
        result = extract_proposal_json(raw)
        assert result is not None
        data = json.loads(result)
        assert data["agent_id"] == "test"

    def test_json_with_prefix(self):
        """Should extract JSON even with text before it."""
        raw = 'Based on the context, here is my proposal: {"agent_id": "test"}'
        result = extract_proposal_json(raw)
        assert result is not None
        data = json.loads(result)
        assert data["agent_id"] == "test"

    def test_invalid_json_returns_none(self):
        """Should return None for invalid JSON."""
        raw = "This is not JSON at all"
        result = extract_proposal_json(raw)
        assert result is None

    def test_nested_json(self):
        """Should handle nested JSON objects."""
        raw = '{"agent_id": "test", "ops": [{"op": "upsert_text", "path": "file.json"}]}'
        result = extract_proposal_json(raw)
        assert result == raw


class TestStubAdapter:
    """Tests for StubAdapter."""

    def test_deterministic_output(self):
        """Same input should produce same output."""
        adapter = StubAdapter()

        result1 = adapter.generate("system", "user prompt")
        # Reset call count for determinism test
        adapter._call_count = 0
        result2 = adapter.generate("system", "user prompt")

        assert result1.proposal_text == result2.proposal_text

    def test_returns_valid_proposal(self):
        """Should return a valid proposal JSON."""
        adapter = StubAdapter()
        result = adapter.generate("system", '{"agent_id": "test", "branch": "main", "base_head_event": 0}')

        assert result.success
        assert result.proposal_text is not None

        proposal = json.loads(result.proposal_text)
        assert "agent_id" in proposal
        assert "ops" in proposal
        assert isinstance(proposal["ops"], list)

    def test_extracts_context_from_prompt(self):
        """Should extract context values from user prompt."""
        adapter = StubAdapter()
        user_prompt = json.dumps(
            {
                "run_id": "test_run_123",
                "agent_id": "my-agent",
                "branch": "feature",
                "base_head_event": 5,
                "query": "do something",
            }
        )

        result = adapter.generate("system", user_prompt)
        proposal = json.loads(result.proposal_text)

        assert proposal["agent_id"] == "my-agent"
        assert proposal["branch"] == "feature"
        assert proposal["base_head_event"] == 5

    def test_fixture_loading(self, tmp_path: Path):
        """Should load proposal from fixture file."""
        fixture = tmp_path / "fixture.json"
        fixture_content = {
            "run_id": "fixture_run",
            "agent_id": "fixture-agent",
            "branch": "main",
            "base_head_event": 0,
            "query": "fixture query",
            "rationale": "from fixture",
            "ops": [{"op": "upsert_text", "path": "test.json", "content": "{}"}],
        }
        fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

        adapter = StubAdapter(fixture_path=fixture)
        result = adapter.generate("system", "ignored prompt")

        assert result.success
        proposal = json.loads(result.proposal_text)
        assert proposal["agent_id"] == "fixture-agent"
        assert len(proposal["ops"]) == 1

    def test_fixture_not_found_error(self, tmp_path: Path):
        """Should return error when fixture file doesn't exist."""
        adapter = StubAdapter(fixture_path=tmp_path / "nonexistent.json")
        result = adapter.generate("system", "prompt")

        assert not result.success
        assert "not found" in result.error.lower()

    def test_fixture_invalid_json_error(self, tmp_path: Path):
        """Should return error for invalid JSON in fixture."""
        fixture = tmp_path / "invalid.json"
        fixture.write_text("not valid json", encoding="utf-8")

        adapter = StubAdapter(fixture_path=fixture)
        result = adapter.generate("system", "prompt")

        assert not result.success
        assert "invalid json" in result.error.lower()


class TestGetAdapter:
    """Tests for get_adapter factory function."""

    def test_get_stub_adapter(self):
        """Should return StubAdapter for 'stub' provider."""
        adapter = get_adapter("stub")
        assert isinstance(adapter, StubAdapter)

    def test_get_stub_with_fixture(self, tmp_path: Path):
        """Should pass fixture_path to StubAdapter."""
        fixture = tmp_path / "test.json"
        fixture.write_text('{"agent_id": "test", "ops": []}', encoding="utf-8")

        adapter = get_adapter("stub", fixture_path=fixture)
        assert isinstance(adapter, StubAdapter)
        assert adapter.fixture_path == fixture

    def test_unknown_provider_raises(self):
        """Should raise ValueError for unknown provider."""
        try:
            get_adapter("unknown_provider")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "unsupported" in str(e).lower()

    def test_get_glm_adapter(self, monkeypatch):
        """Should return OpenAIAdapter configured for GLM."""
        from neonrp.core.llm_openai import OpenAIAdapter

        monkeypatch.setenv("GLM_API_KEY", "fake-key")
        monkeypatch.setenv("GLM_BASE_URL", "https://example.com/api")
        monkeypatch.setenv("GLM_MODEL", "glm-test")
        monkeypatch.setenv("GLM_TEMPERATURE", "0.3")
        monkeypatch.setenv("GLM_MAX_TOKENS", "2048")
        monkeypatch.setenv("GLM_TOP_P", "0.8")
        monkeypatch.setenv("GLM_RESPONSE_FORMAT", "json_object")

        adapter = get_adapter("glm")
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.model == "glm-test"
        assert adapter.temperature == 0.3
        assert adapter.max_tokens == 2048
        assert adapter.base_url == "https://example.com/api"
        assert adapter.extra_kwargs.get("top_p") == 0.8
        assert adapter.extra_kwargs.get("response_format") == {"type": "json_object"}

    def test_get_lmstudio_adapter_not_supported(self):
        """LM Studio provider has been removed from supported providers."""
        try:
            get_adapter("lmstudio")
            assert False, "Expected ValueError"
        except ValueError as e:
            assert "unsupported" in str(e).lower()


# M6 Tool Calling Tests


class TestMessage:
    """Tests for Message dataclass."""

    def test_basic_user_message(self):
        """Should create a basic user message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None

    def test_to_api_dict_simple(self):
        """Should convert to API format correctly."""
        msg = Message(role="user", content="Hello")
        api_dict = msg.to_api_dict()

        assert api_dict["role"] == "user"
        assert api_dict["content"] == "Hello"
        assert "tool_calls" not in api_dict

    def test_to_api_dict_with_tool_calls(self):
        """Should include tool calls in API format."""
        tool_call = ToolCall(id="call_123", name="read_file", arguments={"path": "test.txt"})
        msg = Message(role="assistant", content=None, tool_calls=[tool_call])
        api_dict = msg.to_api_dict()

        assert api_dict["role"] == "assistant"
        assert len(api_dict["tool_calls"]) == 1
        assert api_dict["tool_calls"][0]["id"] == "call_123"
        assert api_dict["tool_calls"][0]["type"] == "function"
        assert api_dict["tool_calls"][0]["function"]["name"] == "read_file"

    def test_to_api_dict_assistant_always_has_content(self):
        """Assistant messages must always include 'content' for Ollama compatibility."""
        # content=None → should become ""
        tc = ToolCall(id="c1", name="ask_user", arguments={"question": "hi"})
        msg = Message(role="assistant", content=None, tool_calls=[tc])
        api_dict = msg.to_api_dict()
        assert "content" in api_dict
        assert api_dict["content"] == ""

        # content with text → should stay as-is
        msg2 = Message(role="assistant", content="some text", tool_calls=[tc])
        api_dict2 = msg2.to_api_dict()
        assert api_dict2["content"] == "some text"

        # non-assistant messages with None content → no content key
        msg3 = Message(role="user", content=None)
        api_dict3 = msg3.to_api_dict()
        assert "content" not in api_dict3

    def test_to_api_dict_tool_response(self):
        """Should include tool_call_id for tool responses."""
        msg = Message(role="tool", content="file contents", tool_call_id="call_123", name="read_file")
        api_dict = msg.to_api_dict()

        assert api_dict["role"] == "tool"
        assert api_dict["content"] == "file contents"
        assert api_dict["tool_call_id"] == "call_123"
        assert api_dict["name"] == "read_file"


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_basic_tool_call(self):
        """Should create a tool call with arguments."""
        tc = ToolCall(id="call_abc", name="read_file", arguments={"path": "game/test.json"})
        assert tc.id == "call_abc"
        assert tc.name == "read_file"
        assert tc.arguments["path"] == "game/test.json"


class TestLLMTurnResult:
    """Tests for LLMTurnResult dataclass."""

    def test_success_property(self):
        """Should return True when message is present and no error."""
        msg = Message(role="assistant", content="Done")
        result = LLMTurnResult(message=msg, finished=True)
        assert result.success is True

    def test_success_false_on_error(self):
        """Should return False when error is present."""
        result = LLMTurnResult(error="API error", finished=True)
        assert result.success is False

    def test_with_tool_calls(self):
        """Should include tool calls."""
        tc = ToolCall(id="call_1", name="read_file", arguments={})
        msg = Message(role="assistant", tool_calls=[tc])
        result = LLMTurnResult(message=msg, tool_calls=[tc], finished=False)

        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.finished is False


class TestStubAdapterChat:
    """Tests for StubAdapter chat() method (M6)."""

    def test_chat_returns_submit_proposal(self):
        """chat() should return a submit_proposal tool call."""
        adapter = StubAdapter()
        messages = [
            Message(role="system", content="You are an agent."),
            Message(
                role="user",
                content=json.dumps(
                    {
                        "run_id": "test_run",
                        "agent_id": "test-agent",
                        "branch": "main",
                        "base_head_event": 0,
                        "query": "do something",
                    }
                ),
            ),
        ]

        result = adapter.chat(messages, tools=[{"name": "submit_proposal"}])

        assert result.success
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "submit_proposal"
        assert result.finished is False  # Tool call needs processing

    def test_chat_extracts_context(self):
        """chat() should extract context from messages."""
        adapter = StubAdapter()
        messages = [
            Message(
                role="user",
                content=json.dumps(
                    {
                        "agent_id": "context-agent",
                        "branch": "feature",
                    }
                ),
            ),
        ]

        result = adapter.chat(messages, tools=[{"name": "submit_proposal"}])

        assert result.success
        tc = result.tool_calls[0]
        assert tc.arguments["agent_id"] == "context-agent"
        assert tc.arguments["branch"] == "feature"

    def test_chat_with_fixture(self, tmp_path: Path):
        """chat() should use fixture for proposal data."""
        fixture = tmp_path / "chat_fixture.json"
        fixture_content = {
            "run_id": "fixture_run",
            "agent_id": "fixture-agent",
            "branch": "main",
            "base_head_event": 0,
            "ops": [{"op": "upsert_text", "path": "test.json", "content": "{}"}],
        }
        fixture.write_text(json.dumps(fixture_content), encoding="utf-8")

        adapter = StubAdapter(fixture_path=fixture)
        messages = [Message(role="user", content="test")]

        result = adapter.chat(messages, tools=[{"name": "submit_proposal"}])

        assert result.success
        assert result.tool_calls[0].arguments["agent_id"] == "fixture-agent"
        assert len(result.tool_calls[0].arguments["ops"]) == 1

    def test_chat_finishes_when_submit_proposal_not_available(self):
        """chat() should return plain text if submit_proposal tool is absent."""
        adapter = StubAdapter()
        messages = [Message(role="user", content="hello")]
        tools = [{"name": "read_file", "parameters": {"type": "object"}}]

        result = adapter.chat(messages, tools=tools)

        assert result.success
        assert result.finished is True
        assert result.tool_calls == []
        assert result.message is not None
        assert "Stub provider active" in (result.message.content or "")
