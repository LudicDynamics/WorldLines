"""回归:缺 key 报错提示的环境变量名不得双后缀。

presets 的 api_key_env 存完整变量名(如 OPENCODE_ZEN_API_KEY);旧文案
无脑拼 `{env}.upper()}_API_KEY` 会指引用户去设不存在的
OPENCODE_ZEN_API_KEY_API_KEY(prod 日志里刷了近 300 次)。提示必须与
config.get_api_key 的解析规则一致:完整名原样用,provider 名补后缀。
"""

from __future__ import annotations

import pytest

from neonrp.core.llm_openai import OpenAIAdapter


def _err_for(env_name: str, monkeypatch) -> str:
    monkeypatch.delenv(env_name if env_name.endswith("_API_KEY")
                       else f"{env_name.upper()}_API_KEY", raising=False)
    monkeypatch.delenv("NEONRP_LLM_API_KEY", raising=False)
    adapter = OpenAIAdapter(model="x", api_key_env=env_name)
    with pytest.raises(ValueError) as ei:
        adapter._get_client()
    return str(ei.value)


def test_full_env_name_not_double_suffixed(monkeypatch) -> None:
    msg = _err_for("OPENCODE_ZEN_API_KEY", monkeypatch)
    assert "OPENCODE_ZEN_API_KEY_API_KEY" not in msg
    assert "Set OPENCODE_ZEN_API_KEY or NEONRP_LLM_API_KEY" in msg


def test_provider_name_gets_suffix(monkeypatch) -> None:
    msg = _err_for("openai", monkeypatch)
    assert "Set OPENAI_API_KEY or NEONRP_LLM_API_KEY" in msg
