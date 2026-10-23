"""Tests for OpenAIAdapter extra kwargs passthrough."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from neonrp.core.llm import Message
from neonrp.core.llm_openai import OpenAIAdapter


@pytest.fixture(autouse=True)
def _one_shot_chat(monkeypatch):
    """These pin the one-shot chat() path; the stream-collected path (10-15) is in test_llm_stall_watch.py."""
    monkeypatch.setenv("NEONRP_LLM_CHAT_VIA_STREAM", "0")


class TestOpenAIExtraKwargs:
    def test_chat_includes_extra_kwargs_in_request_payload(self):
        adapter = OpenAIAdapter(
            model="gpt-4o-mini",
            api_key="test-key",
            extra_kwargs={"reasoning": {"effort": "high"}},
        )
        adapter._client = MagicMock()
        adapter._client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="ok", tool_calls=None),
                )
            ],
            usage=None,
        )

        result = adapter.chat([Message(role="user", content="hello")])

        assert result.error is None
        call_kwargs = adapter._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["extra_body"]["reasoning"] == {"effort": "high"}

    def test_chat_stream_includes_extra_kwargs_via_extra_body(self):
        adapter = OpenAIAdapter(
            model="gpt-4o-mini",
            api_key="test-key",
            extra_kwargs={"reasoning": {"effort": "high"}},
        )
        adapter._client = MagicMock()
        adapter._client.chat.completions.create.return_value = iter(
            [
                SimpleNamespace(
                    usage=None,
                    choices=[
                        SimpleNamespace(
                            finish_reason="stop",
                            delta=SimpleNamespace(content=None, tool_calls=None, reasoning_content=None),
                        )
                    ],
                )
            ]
        )

        chunks = list(adapter.chat_stream([Message(role="user", content="hello")]))

        assert chunks[-1].finished is True
        call_kwargs = adapter._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["extra_body"]["reasoning"] == {"effort": "high"}
