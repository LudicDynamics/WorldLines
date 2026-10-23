"""截断自动续写回归(DeepSeek 创作世界/角色高频截断)。

契约:纯文本 finish_reason=length → 携带部分续请求,≤2 轮无缝拼接;
带 tool_calls 的截断不走此路(既有恢复);usage 跨轮累加。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from neonrp.core.llm import Message
from neonrp.core.llm_openai import OpenAIAdapter


@pytest.fixture(autouse=True)
def _one_shot_chat(monkeypatch):
    """These pin the one-shot chat() path; the stream-collected path (10-15) is in test_llm_stall_watch.py."""
    monkeypatch.setenv("NEONRP_LLM_CHAT_VIA_STREAM", "0")


def _resp(content: str, finish: str, tool_calls=None, usage=(10, 20, 30)):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason=finish,
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=usage[0], completion_tokens=usage[1], total_tokens=usage[2]
        ),
    )


def _adapter() -> OpenAIAdapter:
    a = OpenAIAdapter(model="deepseek-v4-pro", api_key="test-key")
    a._client = MagicMock()
    return a


def test_chat_autocontinues_on_length():
    a = _adapter()
    a._client.chat.completions.create.side_effect = [
        _resp("世界的上半部分,", "length"),
        _resp("以及完整的下半部分。", "stop"),
    ]
    r = a.chat([Message(role="user", content="写一个世界")])
    assert r.error is None
    assert r.message.content == "世界的上半部分,以及完整的下半部分。"
    assert a._client.chat.completions.create.call_count == 2
    # 续请求携带已产出部分 + 续写指令
    cont_msgs = a._client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert cont_msgs[-2]["role"] == "assistant" and "上半部分" in cont_msgs[-2]["content"]
    assert "截断" in cont_msgs[-1]["content"]
    # usage 跨轮累加
    assert r.usage["completion_tokens"] == 40 and r.usage["total_tokens"] == 60


def test_chat_continuation_capped_at_two_rounds():
    a = _adapter()
    a._client.chat.completions.create.side_effect = [
        _resp("一", "length"),
        _resp("二", "length"),
        _resp("三", "length"),  # 第 2 轮续写后仍 length → 停,不再第 3 轮
    ]
    r = a.chat([Message(role="user", content="x")])
    assert a._client.chat.completions.create.call_count == 3  # 首发 + 2 轮
    assert r.message.content == "一二三"


def test_chat_tool_call_truncation_not_autocontinued():
    # 工具调用截断走既有恢复路径,不做文本续写。
    a = _adapter()
    tc = SimpleNamespace(
        id="c1", function=SimpleNamespace(name="write_file", arguments='{"path": "a')
    )
    a._client.chat.completions.create.return_value = _resp("", "length", tool_calls=[tc])
    r = a.chat([Message(role="user", content="x")])
    assert a._client.chat.completions.create.call_count == 1
    assert r.tool_calls and r.tool_calls[0].name == "write_file"


def test_client_sets_explicit_timeouts(monkeypatch):
    """真机卡死复盘(08-11):client 必须带显式 connect/read 超时,
    否则挂死的流按 SDK 缺省要干等 600s×重试。"""
    from neonrp.core.llm_openai import OpenAIAdapter

    a = OpenAIAdapter(model="m", api_key="sk-test", base_url="https://example.com/v1")
    client = a._get_client()
    t = client.timeout
    assert float(t.connect) == 15.0
    # 60 s since the DeepSeek mid-stream-drop fix (project_deepseek_stream_stall):
    # a stalled stream must fail fast so the auto-continue can pick the turn up.
    assert float(t.read) == 60.0
