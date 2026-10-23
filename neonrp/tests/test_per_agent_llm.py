"""Tests for M8-T5: Per-Agent LLM Configuration.

Tests cover:
- ProviderConfig parsing from config.json
- resolve_provider priority logic
- get_adapter_from_config factory
- Agent LLM config resolution in runner
"""

import pytest
import json

from neonrp.core.config import (
    ProviderConfig,
    ProjectConfig,
    LLMConfig,
    TUIConfig,
    load_config,
    resolve_provider,
    _parse_config,
    _parse_provider_config,
)
from neonrp.core.llm import get_adapter_from_config


class TestProviderConfig:
    """Tests for ProviderConfig dataclass and parsing."""

    def test_provider_config_defaults(self):
        """Test ProviderConfig has sensible defaults."""
        pc = ProviderConfig()
        assert pc.provider == "stub"
        assert pc.model == ""
        assert pc.temperature == 0.7
        assert pc.max_output_tokens == 4096
        assert pc.seed is None
        assert pc.base_url is None
        assert pc.api_key_env is None
        assert pc.extra == {}
        assert pc.disable_streaming is False

    def test_provider_config_custom_values(self):
        """Test ProviderConfig with custom values."""
        pc = ProviderConfig(
            provider="openai",
            model="gpt-4o",
            temperature=0.3,
            max_output_tokens=8192,
            seed=42,
            base_url="https://api.example.com",
            api_key_env="CUSTOM_API_KEY",
            extra={"reasoning": {"effort": "high"}},
        )
        assert pc.provider == "openai"
        assert pc.model == "gpt-4o"
        assert pc.temperature == 0.3
        assert pc.max_output_tokens == 8192
        assert pc.seed == 42
        assert pc.base_url == "https://api.example.com"
        assert pc.api_key_env == "CUSTOM_API_KEY"
        assert pc.extra == {"reasoning": {"effort": "high"}}


class TestParseProviderConfig:
    """Tests for _parse_provider_config function."""

    def test_parse_minimal_config(self):
        """Test parsing minimal provider config."""
        data = {"provider": "openai"}
        pc = _parse_provider_config(data)
        assert pc.provider == "openai"
        assert pc.model == ""

    def test_parse_full_config(self):
        """Test parsing fully specified provider config."""
        data = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.5,
            "max_output_tokens": 2048,
            "seed": 123,
            "base_url": "https://custom.api.com",
            "api_key_env": "MY_API_KEY",
            "extra": {"reasoning": {"effort": "medium"}},
        }
        pc = _parse_provider_config(data)
        assert pc.provider == "openai"
        assert pc.model == "gpt-4o-mini"
        assert pc.temperature == 0.5
        assert pc.max_output_tokens == 2048
        assert pc.seed == 123
        assert pc.base_url == "https://custom.api.com"
        assert pc.api_key_env == "MY_API_KEY"
        assert pc.extra == {"reasoning": {"effort": "medium"}}

    def test_parse_empty_config(self):
        """Test parsing empty config returns defaults."""
        data = {}
        pc = _parse_provider_config(data)
        assert pc.provider == "stub"
        assert pc.model == ""


class TestParseConfigWithProviders:
    """Tests for _parse_config with providers registry."""

    def test_parse_config_with_providers(self):
        """Test parsing config.json with models registry."""
        data = {
            "llm": {"model_ref": "strong"},
            "models": {
                "fast": {"provider": "openai", "model": "gpt-4o-mini"},
                "strong": {"provider": "openai", "model": "gpt-4o"},
                "local": {"provider": "openai", "base_url": "http://localhost:11434/v1"},
            },
        }
        config = _parse_config(data)

        assert len(config.providers) == 3
        assert "fast" in config.providers
        assert "strong" in config.providers
        assert "local" in config.providers

        assert config.providers["fast"].model == "gpt-4o-mini"
        assert config.providers["strong"].model == "gpt-4o"
        assert config.providers["local"].base_url == "http://localhost:11434/v1"

    def test_parse_config_disable_streaming(self):
        """Test disable_streaming is parsed from model config."""
        data = {
            "llm": {"model_ref": "remote"},
            "models": {
                "remote": {
                    "provider": "openai",
                    "model": "test-model",
                    "base_url": "http://remote:11434/v1",
                    "disable_streaming": True,
                },
                "local": {"provider": "openai", "model": "test-local"},
            },
        }
        config = _parse_config(data)
        assert config.providers["remote"].disable_streaming is True
        assert config.providers["local"].disable_streaming is False

    def test_parse_config_no_providers(self):
        """Test parsing config.json without providers."""
        data = {"llm": {"provider": "stub"}}
        config = _parse_config(data)
        assert "default" in config.providers
        assert config.providers["default"].provider == "stub"


class TestResolveProvider:
    """Tests for resolve_provider priority logic."""

    def setup_method(self):
        """Set up test config."""
        self.config = ProjectConfig(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            tui=TUIConfig(),
            providers={
                "fast": ProviderConfig(provider="openai", model="gpt-4o-mini"),
                "strong": ProviderConfig(provider="openai", model="gpt-4o", temperature=0.2),
                "local": ProviderConfig(provider="openai", base_url="http://localhost:11434/v1"),
            },
        )

    def test_priority_cli_override(self):
        """Test CLI --provider has highest priority."""
        result = resolve_provider(
            self.config,
            agent_llm_config={"provider": "anthropic", "model": "claude-3"},
            cli_provider="glm",
        )
        assert result.provider == "glm"

    def test_priority_agent_inline_config(self):
        """Test agent inline config has priority over global."""
        result = resolve_provider(
            self.config,
            agent_llm_config={"provider": "anthropic", "model": "claude-3"},
            cli_provider=None,
        )
        assert result.provider == "anthropic"
        assert result.model == "claude-3"

    def test_priority_agent_provider_ref(self):
        """Test agent provider_ref resolves to named provider."""
        result = resolve_provider(
            self.config,
            agent_llm_config={"provider_ref": "fast"},
            cli_provider=None,
        )
        assert result.provider == "openai"
        assert result.model == "gpt-4o-mini"

    def test_priority_fallback_to_global(self):
        """Test fallback to global config when no agent config."""
        result = resolve_provider(self.config, agent_llm_config=None, cli_provider=None)
        assert result.provider == "openai"
        assert result.model == "gpt-4o"

    def test_unknown_provider_ref_fallback(self):
        """Test unknown provider_ref falls back to global."""
        result = resolve_provider(
            self.config,
            agent_llm_config={"provider_ref": "nonexistent"},
            cli_provider=None,
        )
        # Falls through to global config
        assert result.provider == "openai"
        assert result.model == "gpt-4o"

    def test_agent_inline_with_base_url(self):
        """Test agent inline config with custom base_url."""
        result = resolve_provider(
            self.config,
            agent_llm_config={
                "provider": "openai",
                "model": "local-llama",
                "base_url": "http://localhost:8080/v1",
            },
            cli_provider=None,
        )
        assert result.provider == "openai"
        assert result.model == "local-llama"
        assert result.base_url == "http://localhost:8080/v1"

    def test_agent_inline_with_api_key_env(self):
        """Test agent inline config with custom api_key_env."""
        result = resolve_provider(
            self.config,
            agent_llm_config={
                "provider": "openai",
                "api_key_env": "CUSTOM_AGENT_KEY",
            },
            cli_provider=None,
        )
        assert result.api_key_env == "CUSTOM_AGENT_KEY"

    def test_agent_inline_with_extra_payload(self):
        """Test agent inline config can pass provider-specific extra payload."""
        result = resolve_provider(
            self.config,
            agent_llm_config={
                "provider": "openai",
                "extra": {"reasoning": {"effort": "high"}},
            },
            cli_provider=None,
        )
        assert result.extra == {"reasoning": {"effort": "high"}}


class TestGetAdapterFromConfig:
    """Tests for get_adapter_from_config factory function."""

    def test_stub_adapter_creation(self):
        """Test creating stub adapter from config."""
        pc = ProviderConfig(provider="stub")
        adapter = get_adapter_from_config(pc)
        assert adapter is not None

    def test_stub_adapter_with_fixture(self):
        """Test stub adapter accepts fixture_path kwarg."""
        pc = ProviderConfig(provider="stub")
        # Should not raise
        adapter = get_adapter_from_config(pc, fixture_path="test.json")
        assert adapter is not None

    def test_anthropic_provider_is_supported(self):
        """Anthropic provider should be accepted."""
        pc = ProviderConfig(provider="anthropic")
        adapter = get_adapter_from_config(pc)
        assert adapter is not None

    def test_openai_provider_passes_extra_kwargs(self):
        """OpenAI-compatible adapter should receive ProviderConfig.extra."""
        pc = ProviderConfig(provider="openai", model="gpt-4o-mini", extra={"reasoning": {"effort": "high"}})
        adapter = get_adapter_from_config(pc)
        assert getattr(adapter, "extra_kwargs", {}) == {"reasoning": {"effort": "high"}}

    def test_unsupported_provider_raises(self):
        """Test unsupported provider raises ValueError."""
        pc = ProviderConfig(provider="unsupported_provider")
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            get_adapter_from_config(pc)


class TestLoadConfigWithProviders:
    """Integration tests for loading config with providers."""

    def test_load_config_with_providers_registry(self, tmp_path):
        """Test loading config.json with providers from file."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()

        config_data = {
            "llm": {"model_ref": "fast"},
            "models": {
                "fast": {"provider": "openai", "model": "gpt-4o-mini"},
                "local": {"provider": "openai", "base_url": "http://localhost:11434/v1"},
            },
        }

        config_path = neonrp_dir / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)

        assert len(config.providers) == 2
        assert config.providers["fast"].model == "gpt-4o-mini"
        assert config.providers["local"].base_url == "http://localhost:11434/v1"


class TestSubAgentLLMInheritance:
    """Tests for sub-agent LLM configuration inheritance."""

    def setup_method(self):
        """Set up test config with providers."""
        self.config = ProjectConfig(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            tui=TUIConfig(),
            providers={
                "fast": ProviderConfig(provider="openai", model="gpt-4o-mini"),
            },
        )

    def test_sub_agent_inherits_parent_cli_override(self):
        """Test that CLI override propagates correctly."""
        # When parent has CLI override, sub-agent should also use it
        # (simulated by passing same cli_provider to resolve_provider)
        result = resolve_provider(self.config, None, cli_provider="glm")
        assert result.provider == "glm"

    def test_sub_agent_can_override_parent(self):
        """Test sub-agent can have its own config."""
        # Parent uses global config
        parent_result = resolve_provider(self.config, None, None)
        assert parent_result.model == "gpt-4o"

        # Sub-agent can use provider_ref
        sub_result = resolve_provider(
            self.config,
            agent_llm_config={"provider_ref": "fast"},
            cli_provider=None,
        )
        assert sub_result.model == "gpt-4o-mini"


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing configs."""

    def test_config_without_providers_still_works(self):
        """Test that configs without providers section work."""
        data = {
            "llm": {"provider": "openai", "model": "gpt-4o"},
            "tui": {"auto_apply": False},
        }
        config = _parse_config(data)

        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"
        assert "default" in config.providers

    def test_agent_without_llm_uses_global(self):
        """Test agent without llm block uses global config."""
        config = ProjectConfig(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            tui=TUIConfig(),
        )

        result = resolve_provider(config, agent_llm_config=None, cli_provider=None)
        assert result.provider == "openai"
        assert result.model == "gpt-4o"

    def test_empty_agent_llm_block_uses_global(self):
        """Test agent with empty llm block uses global config."""
        config = ProjectConfig(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            tui=TUIConfig(),
        )

        # Empty dict (no provider or provider_ref)
        result = resolve_provider(config, agent_llm_config={}, cli_provider=None)
        assert result.provider == "openai"
        assert result.model == "gpt-4o"
