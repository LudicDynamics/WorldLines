"""Tests for LLM retry logic and error categories (M7-T1)."""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from neonrp.core.llm_errors import (
    AuthError,
    BudgetExhaustedError,
    InvalidResponseError,
    LLMError,
    RetryableError,
)
from neonrp.core.llm_openai import OpenAIAdapter, _classify_openai_error


@pytest.fixture(autouse=True)
def _one_shot_chat(monkeypatch):
    """These pin the one-shot chat() path; the stream-collected path (10-15) is in test_llm_stall_watch.py."""
    monkeypatch.setenv("NEONRP_LLM_CHAT_VIA_STREAM", "0")


# --- Error hierarchy tests ---


class TestErrorHierarchy:
    def test_all_errors_inherit_from_llm_error(self):
        assert issubclass(RetryableError, LLMError)
        assert issubclass(AuthError, LLMError)
        assert issubclass(InvalidResponseError, LLMError)
        assert issubclass(BudgetExhaustedError, LLMError)

    def test_retryable_flag(self):
        assert RetryableError.retryable is True
        assert AuthError.retryable is False
        assert InvalidResponseError.retryable is False
        assert BudgetExhaustedError.retryable is False

    def test_status_code(self):
        e = RetryableError("rate limited", status_code=429)
        assert e.status_code == 429
        assert str(e) == "rate limited"

    def test_default_status_code_none(self):
        e = LLMError("generic")
        assert e.status_code is None


# --- Error classification tests ---


class TestClassifyOpenAIError:
    """Test _classify_openai_error with mock openai exceptions."""

    def _make_openai_error(self, cls_name, message="test error", status_code=None):
        """Create a mock openai exception class instance."""
        # We mock the openai module to avoid import dependency
        mock_module = MagicMock()

        @dataclass
        class FakeAPIError(Exception):
            message: str = ""
            status_code: int | None = None

            def __str__(self):
                return self.message

        # Create different error types
        error_classes = {
            "RateLimitError": type("RateLimitError", (FakeAPIError,), {}),
            "APITimeoutError": type("APITimeoutError", (FakeAPIError,), {}),
            "APIConnectionError": type("APIConnectionError", (FakeAPIError,), {}),
            "InternalServerError": type("InternalServerError", (FakeAPIError,), {}),
            "AuthenticationError": type("AuthenticationError", (FakeAPIError,), {}),
            "BadRequestError": type("BadRequestError", (FakeAPIError,), {}),
        }

        for name, cls in error_classes.items():
            setattr(mock_module, name, cls)

        error_cls = error_classes[cls_name]
        error = error_cls(message=message, status_code=status_code)

        return mock_module, error

    def test_rate_limit_classified_as_retryable(self):
        mock_module, error = self._make_openai_error("RateLimitError", status_code=429)
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, RetryableError)

    def test_timeout_classified_as_retryable(self):
        mock_module, error = self._make_openai_error("APITimeoutError")
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, RetryableError)

    def test_connection_error_classified_as_retryable(self):
        mock_module, error = self._make_openai_error("APIConnectionError")
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, RetryableError)

    def test_internal_server_error_classified_as_retryable(self):
        mock_module, error = self._make_openai_error("InternalServerError", status_code=500)
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, RetryableError)

    def test_auth_error_classified_as_auth(self):
        mock_module, error = self._make_openai_error("AuthenticationError", status_code=401)
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, AuthError)

    def test_bad_request_classified_as_invalid(self):
        mock_module, error = self._make_openai_error("BadRequestError", status_code=400)
        with patch.dict("sys.modules", {"openai": mock_module}):
            result = _classify_openai_error(error)
            assert isinstance(result, InvalidResponseError)

    def test_connection_error_python_builtin(self):
        """Python built-in ConnectionError should also be retryable."""
        result = _classify_openai_error(ConnectionError("network down"))
        assert isinstance(result, RetryableError)

    def test_httpx_remote_protocol_error_classified_as_retryable(self):
        """httpx.RemoteProtocolError surfaces when a provider (DeepSeek
        in particular) closes the stream mid-response. Same prompt
        usually succeeds on retry."""
        try:
            import httpx
        except ImportError:
            return
        e = httpx.RemoteProtocolError("peer closed connection without sending complete message body")
        result = _classify_openai_error(e)
        assert isinstance(result, RetryableError)

    def test_unknown_error_passes_through(self):
        """Unknown errors pass through unchanged."""
        e = RuntimeError("something weird")
        result = _classify_openai_error(e)
        assert result is e


class TestRetryableErrorTextClassifier:
    """Test the text-based retryable classifier in conversation."""

    def _classifier(self):
        from neonrp.core.conversation import _looks_retryable_error_text
        return _looks_retryable_error_text

    def test_peer_closed_connection_is_retryable(self):
        f = self._classifier()
        assert f("OpenAI API streaming error: peer closed connection without sending complete message body (incomplete chunked read)") is True

    def test_incomplete_chunked_read_alone_is_retryable(self):
        f = self._classifier()
        assert f("provider hiccup: incomplete chunked read at byte 12345") is True

    def test_remote_protocol_error_is_retryable(self):
        f = self._classifier()
        assert f("httpx.RemoteProtocolError: server hung up") is True

    def test_connection_broken_is_retryable(self):
        f = self._classifier()
        assert f("ChunkedEncodingError: Connection broken") is True

    def test_400_bad_request_is_not_retryable(self):
        """Content-shape errors (400) are NOT retryable; same input → same 400."""
        f = self._classifier()
        # The classifier doesn't have "400" or "bad request" in its
        # markers — content errors fall through to the dispatcher.
        assert f("Invalid request: 400 Bad Request") is False

    def test_empty_or_none_is_not_retryable(self):
        f = self._classifier()
        assert f(None) is False
        assert f("") is False


# --- Retry logic tests ---


class TestRetryLogic:
    """Test _call_with_retry behavior."""

    def _make_adapter(self, max_retries=3):
        """Create adapter with mock client to avoid real API calls."""
        adapter = OpenAIAdapter(
            api_key="test-key",
            max_retries=max_retries,
        )
        adapter._client = MagicMock()
        return adapter

    def test_success_on_first_attempt(self):
        adapter = self._make_adapter()
        result = adapter._call_with_retry(lambda: "ok")
        assert result == "ok"

    @patch("neonrp.core.llm_openai.time.sleep")
    def test_retries_on_retryable_error(self, mock_sleep):
        adapter = self._make_adapter(max_retries=3)
        call_count = 0

        def flaky_call():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("rate limited")
            return "ok"

        result = adapter._call_with_retry(flaky_call)
        assert result == "ok"
        assert call_count == 3
        assert mock_sleep.call_count == 2  # Slept before retry 2 and 3

    @patch("neonrp.core.llm_openai.time.sleep")
    def test_exhausts_retries(self, mock_sleep):
        adapter = self._make_adapter(max_retries=2)

        def always_fail():
            raise RetryableError("always rate limited")

        with pytest.raises(RetryableError, match="after 2 retries"):
            adapter._call_with_retry(always_fail)

        assert mock_sleep.call_count == 2

    def test_no_retry_on_auth_error(self):
        adapter = self._make_adapter(max_retries=3)
        call_count = 0

        def auth_fail():
            nonlocal call_count
            call_count += 1
            raise AuthError("bad key")

        with pytest.raises(AuthError):
            adapter._call_with_retry(auth_fail)

        assert call_count == 1  # No retry

    def test_no_retry_on_invalid_response(self):
        adapter = self._make_adapter(max_retries=3)
        call_count = 0

        def bad_request():
            nonlocal call_count
            call_count += 1
            raise InvalidResponseError("bad request")

        with pytest.raises(InvalidResponseError):
            adapter._call_with_retry(bad_request)

        assert call_count == 1

    @patch("neonrp.core.llm_openai.time.sleep")
    def test_backoff_increases(self, mock_sleep):
        adapter = self._make_adapter(max_retries=3)

        def always_fail():
            raise RetryableError("fail")

        with pytest.raises(RetryableError):
            adapter._call_with_retry(always_fail)

        # 3 retries → 3 sleep calls, each with increasing base
        assert mock_sleep.call_count == 3
        # Backoff: 2^0 + jitter, 2^1 + jitter, 2^2 + jitter
        for i, call in enumerate(mock_sleep.call_args_list):
            sleep_time = call[0][0]
            assert sleep_time >= 2**i  # At least the base
            assert sleep_time <= 2**i + 1  # At most base + 1s jitter

    def test_zero_retries(self):
        adapter = self._make_adapter(max_retries=0)

        def fail_once():
            raise RetryableError("fail")

        with pytest.raises(RetryableError, match="after 0 retries"):
            adapter._call_with_retry(fail_once)


# --- Integration: chat() with retry ---


class TestChatWithRetry:
    """Test that chat() uses retry and returns proper LLMTurnResult on errors."""

    def _make_adapter(self, max_retries=1):
        adapter = OpenAIAdapter(api_key="test-key", max_retries=max_retries)
        adapter._client = MagicMock()
        return adapter

    @patch("neonrp.core.llm_openai.time.sleep")
    def test_chat_auth_error_fails_immediately(self, mock_sleep):
        adapter = self._make_adapter()

        # Make chat.completions.create raise AuthError
        adapter._client.chat.completions.create.side_effect = AuthError("bad key")

        from neonrp.core.llm import Message

        result = adapter.chat([Message(role="user", content="hello")])
        assert not result.success
        assert "Authentication failed" in result.error
        assert mock_sleep.call_count == 0

    @patch("neonrp.core.llm_openai.time.sleep")
    def test_chat_retryable_error_retries_and_fails(self, mock_sleep):
        adapter = self._make_adapter(max_retries=2)

        adapter._client.chat.completions.create.side_effect = RetryableError("rate limited")

        from neonrp.core.llm import Message

        result = adapter.chat([Message(role="user", content="hello")])
        assert not result.success
        assert "after retries" in result.error
        assert result.retryable is True


# --- Config integration ---


class TestConfigMaxRetries:
    def test_default_max_retries(self):
        from neonrp.core.config import LLMConfig

        config = LLMConfig()
        assert config.max_retries == 3

    def test_custom_max_retries(self):
        from neonrp.core.config import LLMConfig

        config = LLMConfig(max_retries=5)
        assert config.max_retries == 5

    def test_max_context_chars_default(self):
        from neonrp.core.config import LLMConfig

        config = LLMConfig()
        assert config.max_context_chars == 100000
