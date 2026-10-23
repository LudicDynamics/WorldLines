"""E2E tests that use the user-configured real endpoint (no stub)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from neonrp.core.config import get_user_config_path, load_config, resolve_provider
from neonrp.core.llm import Message, get_adapter_from_config


pytestmark = pytest.mark.e2e_llm


def _requires_e2e() -> bool:
    return os.environ.get("NEONRP_E2E_LLM", "").lower() in {"1", "true", "yes"}


def _load_user_provider(tmp_path: Path):
    if not _requires_e2e():
        pytest.skip("E2E tests disabled (set NEONRP_E2E_LLM=1)")

    user_cfg = get_user_config_path()
    if not user_cfg.exists():
        pytest.skip(f"User config not found: {user_cfg}")
    raw = json.loads(user_cfg.read_text(encoding="utf-8"))

    config = load_config(tmp_path, include_user_config=True)
    provider = resolve_provider(config)

    if provider.provider == "stub":
        pytest.skip("User config still resolves to stub provider")
    if provider.provider not in {"openai", "glm"}:
        pytest.skip(f"Provider '{provider.provider}' is not OpenAI-compatible for this test")
    if not provider.base_url:
        pytest.skip("User config does not define llm.base_url endpoint")

    configured_base_url = (raw.get("llm", {}) or {}).get("base_url")
    if configured_base_url:
        assert provider.base_url == configured_base_url

    return provider


class TestRealEndpointFromUserConfig:
    def test_chat_uses_user_configured_endpoint(self, tmp_path: Path):
        provider = _load_user_provider(tmp_path)
        adapter = get_adapter_from_config(provider, max_retries=1)

        result = adapter.chat([Message(role="user", content="Reply with one short word.")])

        assert result.error is None
        assert result.message is not None
        assert isinstance(result.message.content, str)
        assert result.message.content.strip() != ""

    def test_chat_stream_uses_user_configured_endpoint(self, tmp_path: Path):
        provider = _load_user_provider(tmp_path)
        adapter = get_adapter_from_config(provider, max_retries=1)

        chunks = list(adapter.chat_stream([Message(role="user", content="Reply with one short word.")]))

        assert chunks
        assert chunks[-1].finished is True
        assert chunks[-1].error is None
