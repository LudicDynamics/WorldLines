"""Tests for Anthropic adapter message conversion and error handling."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from neonrp.core.llm import LLMTurnResult, Message, ToolCall
from neonrp.core.llm_anthropic import (
    AnthropicAdapter,
    _is_retryable_error,
    _to_anthropic_messages,
)


class TestToAnthropicMessages:
    """Tests for conversion of NeonRP messages to Anthropic payload format."""

    def test_tool_result_sets_is_error_true_on_error_status(self):
        """Tool result blocks should set is_error=True when status is error."""
        tool_payload = json.dumps({"status": "error", "error": "Unknown tool"})
        system, converted = _to_anthropic_messages(
            [
                Message(role="user", content="hi"),
                Message(role="tool", content=tool_payload, tool_call_id="call_1", name="glob"),
            ]
        )

        assert system is None
        assert len(converted) == 2
        tool_block = converted[1]["content"][0]
        assert tool_block["type"] == "tool_result"
        assert tool_block["tool_use_id"] == "call_1"
        assert tool_block["is_error"] is True

    def test_tool_result_sets_is_error_false_on_success_status(self):
        """Tool result blocks should keep is_error=False for successful tool output."""
        tool_payload = json.dumps({"status": "success", "data": {"count": 3}})
        _, converted = _to_anthropic_messages(
            [
                Message(role="tool", content=tool_payload, tool_call_id="call_2", name="glob"),
            ]
        )

        tool_block = converted[0]["content"][0]
        assert tool_block["is_error"] is False


class TestIsRetryableError:
    """Tests for _is_retryable_error classification."""

    def test_bad_request_error_is_retryable(self):
        """400 BadRequestError should be retryable (message history may be fixable)."""
        anthropic = pytest.importorskip("anthropic")
        exc = anthropic.BadRequestError(
            message="invalid tool_use block",
            response=MagicMock(status_code=400),
            body={"error": {"message": "invalid"}},
        )
        assert _is_retryable_error(exc) is True

    def test_auth_error_is_not_retryable(self):
        """401 AuthenticationError should not be retryable."""
        anthropic = pytest.importorskip("anthropic")
        exc = anthropic.AuthenticationError(
            message="invalid api key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "invalid key"}},
        )
        assert _is_retryable_error(exc) is False

    def test_server_error_is_retryable(self):
        """5xx errors should be retryable."""
        anthropic = pytest.importorskip("anthropic")
        exc = anthropic.InternalServerError(
            message="internal error",
            response=MagicMock(status_code=500),
            body={"error": {"message": "internal"}},
        )
        assert _is_retryable_error(exc) is True

    def test_connection_error_is_retryable(self):
        """Connection errors should be retryable."""
        anthropic = pytest.importorskip("anthropic")
        exc = anthropic.APIConnectionError(request=MagicMock())
        assert _is_retryable_error(exc) is True

    def test_generic_exception_is_not_retryable(self):
        """Non-anthropic exceptions should not be retryable."""
        assert _is_retryable_error(ValueError("something")) is False

    def test_no_anthropic_package_returns_false(self):
        """When anthropic is not installed, should return False."""
        with patch.dict("sys.modules", {"anthropic": None}):
            assert _is_retryable_error(RuntimeError("test")) is False


class TestAnthropicAdapterMaxRetries:
    """Tests that max_retries is passed to the Anthropic SDK client."""

    def test_max_retries_passed_to_client(self):
        """max_retries should be forwarded to anthropic.Anthropic()."""
        anthropic = pytest.importorskip("anthropic")
        adapter = AnthropicAdapter(api_key="test-key", max_retries=5)

        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            adapter._get_client()
            mock_cls.assert_called_once_with(api_key="test-key", max_retries=5)

    def test_chat_returns_retryable_on_bad_request(self):
        """chat() should return retryable=True for BadRequestError."""
        anthropic = pytest.importorskip("anthropic")
        adapter = AnthropicAdapter(api_key="test-key")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.BadRequestError(
            message="invalid tool_use",
            response=MagicMock(status_code=400),
            body={"error": {"message": "invalid"}},
        )
        adapter._client = mock_client

        result = adapter.chat([Message(role="user", content="hello")])
        assert result.success is False
        assert result.retryable is True
        assert "Anthropic API error" in result.error

    def test_chat_returns_non_retryable_on_auth_error(self):
        """chat() should return retryable=False for AuthenticationError."""
        anthropic = pytest.importorskip("anthropic")
        adapter = AnthropicAdapter(api_key="bad-key")

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "invalid key"}},
        )
        adapter._client = mock_client

        result = adapter.chat([Message(role="user", content="hello")])
        assert result.success is False
        assert result.retryable is False
