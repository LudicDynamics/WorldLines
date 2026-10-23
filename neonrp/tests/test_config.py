"""Tests for config module."""

import json
import os
from pathlib import Path


from neonrp.core.config import (
    LLMConfig,
    MCPServerConfig,
    ProjectConfig,
    RulesConfig,
    TUIConfig,
    load_config,
    apply_overrides,
    get_api_key,
    create_default_config_template,
    get_user_config_path,
    load_dotenv,
)


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = LLMConfig()
        assert config.provider == "stub"
        assert config.model == ""
        assert config.temperature == 0.7
        assert config.max_output_tokens == 4096
        assert config.seed is None

    def test_custom_values(self):
        """Should accept custom values."""
        config = LLMConfig(provider="openai", model="gpt-4", temperature=0.5, max_output_tokens=2048, seed=42)
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.temperature == 0.5
        assert config.max_output_tokens == 2048
        assert config.seed == 42


class TestProjectConfig:
    """Tests for ProjectConfig dataclass."""

    def test_default(self):
        """Should create with default LLMConfig."""
        config = ProjectConfig.default()
        assert config.llm.provider == "stub"
        assert config.llm.temperature == 0.7
        assert config.tui.language == "auto"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_missing_config_returns_defaults(self, tmp_path: Path):
        """Should return defaults when config file doesn't exist."""
        (tmp_path / ".neonrp").mkdir()
        config = load_config(tmp_path)
        assert config.llm.provider == "stub"
        assert config.llm.temperature == 0.7

    def test_load_valid_config(self, tmp_path: Path):
        """Should load valid config file."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "llm": {"provider": "openai", "model": "gpt-4", "temperature": 0.3, "max_output_tokens": 1000, "seed": 123}
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4"
        assert config.llm.temperature == 0.3
        assert config.llm.max_output_tokens == 1000
        assert config.llm.seed == 123

    def test_partial_config_uses_defaults(self, tmp_path: Path):
        """Should use defaults for missing fields."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {"llm": {"provider": "anthropic"}}
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)
        assert config.llm.provider == "anthropic"
        assert config.llm.model == ""  # default
        assert config.llm.temperature == 0.7  # default

    def test_load_tui_language(self, tmp_path: Path):
        """Should load optional TUI language override."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {"tui": {"language": "zh-CN"}}
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)
        assert config.tui.language == "zh-CN"

    def test_provider_comments_are_ignored(self, tmp_path: Path):
        """Non-object entries in providers should be ignored."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "providers": {
                "_comment": "Named providers",
                "fast": {"provider": "openai", "model": "gpt-4o-mini"},
            }
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)
        assert "fast" in config.providers
        assert config.providers["fast"].provider == "openai"

    def test_invalid_json_returns_defaults(self, tmp_path: Path):
        """Should return defaults on invalid JSON."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text("not valid json", encoding="utf-8")

        config = load_config(tmp_path)
        assert config.llm.provider == "stub"

    def test_user_config_fallback(self, tmp_path: Path, monkeypatch):
        """Should read user-level config when project config is missing."""
        monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "user-home"))
        user_config_path = get_user_config_path()
        user_config_path.parent.mkdir(parents=True, exist_ok=True)
        user_config_path.write_text(
            json.dumps(
                {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "base_url": "https://api.openai.com/v1",
                        "api_key_env": "OPENAI_API_KEY",
                    }
                }
            ),
            encoding="utf-8",
        )

        # Explicitly include user config for deterministic assertion under pytest.
        config = load_config(tmp_path, include_user_config=True)
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o-mini"
        assert config.llm.base_url == "https://api.openai.com/v1"
        assert config.llm.api_key_env == "OPENAI_API_KEY"

    def test_project_config_overrides_user_config(self, tmp_path: Path, monkeypatch):
        """Project config should override user-level values."""
        monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "user-home"))
        user_config_path = get_user_config_path()
        user_config_path.parent.mkdir(parents=True, exist_ok=True)
        user_config_path.write_text(
            json.dumps({"llm": {"provider": "openai", "model": "gpt-4o-mini"}}),
            encoding="utf-8",
        )

        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps({"llm": {"provider": "glm", "model": "glm-4"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=True)
        assert config.llm.provider == "glm"
        assert config.llm.model == "glm-4"

    def test_project_config_overrides_user_config(self, tmp_path: Path, monkeypatch):
        """Project config takes priority over user config (standard convention)."""
        monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "user-home"))
        user_config_path = get_user_config_path()
        user_config_path.parent.mkdir(parents=True, exist_ok=True)
        user_config_path.write_text(
            json.dumps({"llm": {"provider": "openai", "model": "gpt-5", "base_url": "https://api.openai.com/v1"}}),
            encoding="utf-8",
        )

        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps({"llm": {"provider": "stub", "model": "", "base_url": ""}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=True)
        # Project explicitly set provider=stub, so it wins over user's openai.
        assert config.llm.provider == "stub"

    def test_user_config_fills_in_when_project_omits(self, tmp_path: Path, monkeypatch):
        """User config provides defaults for keys the project doesn't set."""
        monkeypatch.setenv("NEONRP_HOME", str(tmp_path / "user-home"))
        user_config_path = get_user_config_path()
        user_config_path.parent.mkdir(parents=True, exist_ok=True)
        user_config_path.write_text(
            json.dumps({
                "llm": {"model_ref": "my-model", "max_retries": 5},
                "tui": {"max_tool_rounds": 100, "narrator_agent_id": "gm"},
            }),
            encoding="utf-8",
        )

        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        # Project config is minimal — only sets rules.
        (neonrp_dir / "config.json").write_text(
            json.dumps({"rules": {"enable_resolve_action": False}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=True)
        # User values inherited where project is silent.
        assert config.llm.max_retries == 5
        assert config.tui.max_tool_rounds == 100
        assert config.tui.narrator_agent_id == "gm"
        # Project override takes effect.
        assert config.rules.enable_resolve_action is False

    def test_tui_narrator_agent_id_defaults_to_narrator(self, tmp_path: Path):
        """Narrator id should default to 'narrator' when omitted."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(json.dumps({"tui": {}}), encoding="utf-8")

        config = load_config(tmp_path, include_user_config=False)
        assert config.tui.narrator_agent_id == "narrator"

    def test_tui_narrator_agent_id_can_be_overridden(self, tmp_path: Path):
        """Project config should allow custom narrator/router agent id."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps({"tui": {"narrator_agent_id": "game-master"}}),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=False)
        assert config.tui.narrator_agent_id == "game-master"

    def test_legacy_api_key_env_value_is_treated_as_direct_api_key(self, tmp_path: Path):
        """Old configs with raw key in api_key_env should still work."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps(
                {
                    "llm": {
                        "provider": "openai",
                        "model": "gpt-5",
                        "base_url": "https://api.openai.com/v1",
                        "api_key_env": "key1234",
                    }
                }
            ),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=False)
        assert config.llm.api_key == "key1234"
        assert config.llm.api_key_env is None

    def test_model_extra_is_loaded_into_runtime_llm(self, tmp_path: Path):
        """Model-specific extra payload should be available in resolved runtime config."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps(
                {
                    "llm": {"model_ref": "openrouter"},
                    "models": {
                        "openrouter": {
                            "provider": "openai",
                            "base_url": "https://openrouter.ai/api/v1",
                            "model": "openai/gpt-5-mini",
                            "extra": {"reasoning": {"effort": "high"}},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=False)
        assert config.llm.provider == "openai"
        assert config.llm.extra == {"reasoning": {"effort": "high"}}
        assert config.providers["openrouter"].extra == {"reasoning": {"effort": "high"}}

    def test_load_rules_config(self, tmp_path: Path):
        """Should parse rules section from config.json."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps(
                {
                    "rules": {
                        "enable_domain_validation": False,
                        "enable_resolve_action": False,
                        "profile_path": ".neonrp/rules.profile.json",
                    }
                }
            ),
            encoding="utf-8",
        )
        config = load_config(tmp_path, include_user_config=False)
        assert config.rules.enable_domain_validation is False
        assert config.rules.enable_resolve_action is False
        assert config.rules.profile_path == ".neonrp/rules.profile.json"

    def test_embedding_model_ref_inherits_model_registry_fields(self, tmp_path: Path):
        """embedding.model_ref-only config should resolve model/provider/auth from models registry."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(
            json.dumps(
                {
                    "models": {
                        "local-embed": {
                            "provider": "openai",
                            "base_url": "http://127.0.0.1:1234/v1",
                            "model": "text-embedding-qwen3-embedding-0.6b",
                            "api_key": "1234",
                        }
                    },
                    "embedding": {"enabled": True, "model_ref": "local-embed"},
                }
            ),
            encoding="utf-8",
        )

        config = load_config(tmp_path, include_user_config=False)
        assert config.embedding.enabled is True
        assert config.embedding.model_ref == "local-embed"
        assert config.embedding.model == "text-embedding-qwen3-embedding-0.6b"
        assert config.embedding.provider == "openai"
        assert config.embedding.base_url == "http://127.0.0.1:1234/v1"
        assert config.embedding.api_key == "1234"


class TestApplyOverrides:
    """Tests for apply_overrides function."""

    def test_override_provider(self):
        """Should override provider."""
        base = ProjectConfig.default()
        config = apply_overrides(base, {"provider": "openai"})
        assert config.llm.provider == "openai"

    def test_override_multiple(self):
        """Should override multiple fields."""
        base = ProjectConfig.default()
        config = apply_overrides(base, {"provider": "anthropic", "model": "claude-3", "temperature": 0.1})
        assert config.llm.provider == "anthropic"
        assert config.llm.model == "claude-3"
        assert config.llm.temperature == 0.1

    def test_empty_overrides(self):
        """Should keep base config with empty overrides."""
        base = ProjectConfig(llm=LLMConfig(provider="test"))
        config = apply_overrides(base, {})
        assert config.llm.provider == "test"

    def test_preserves_rules_config(self):
        """apply_overrides should preserve rules settings."""
        base = ProjectConfig(
            llm=LLMConfig(provider="test"),
            rules=RulesConfig(
                enable_domain_validation=False,
                enable_resolve_action=False,
                profile_path="rules/profile.json",
            ),
        )
        config = apply_overrides(base, {"provider": "openai"})
        assert config.rules.enable_domain_validation is False
        assert config.rules.enable_resolve_action is False
        assert config.rules.profile_path == "rules/profile.json"


class TestGetApiKey:
    """Tests for get_api_key function."""

    def test_generic_key(self, monkeypatch):
        """Should return generic NEONRP_LLM_API_KEY."""
        monkeypatch.setenv("NEONRP_LLM_API_KEY", "test-key")
        assert get_api_key("openai") == "test-key"

    def test_provider_specific_key(self, monkeypatch):
        """Should return provider-specific key when generic not set."""
        monkeypatch.delenv("NEONRP_LLM_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        assert get_api_key("openai") == "openai-key"

    def test_generic_takes_precedence(self, monkeypatch):
        """Generic key should take precedence over provider-specific."""
        monkeypatch.setenv("NEONRP_LLM_API_KEY", "generic-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        assert get_api_key("openai") == "generic-key"

    def test_no_key_returns_none(self, monkeypatch):
        """Should return None when no key is set."""
        monkeypatch.delenv("NEONRP_LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert get_api_key("openai") is None

    def test_literal_env_var_name(self, monkeypatch):
        """Should support passing env var name directly."""
        monkeypatch.delenv("NEONRP_LLM_API_KEY", raising=False)
        monkeypatch.setenv("CUSTOM_OPENAI_API_KEY", "custom-key")
        assert get_api_key("CUSTOM_OPENAI_API_KEY") == "custom-key"


class TestConfigTemplate:
    """Tests for create_default_config_template."""

    def test_is_minimal(self):
        """Template should stay minimal while exposing core routing knobs."""
        template = create_default_config_template()
        assert "llm" in template
        assert "tui" in template
        assert "rules" in template
        assert "models" in template
        assert "mcp_servers" in template
        # Only stub model in template; no example providers that would pollute merges.
        model_names = [k for k in template["models"] if not k.startswith("_")]
        assert model_names == ["stub"]
        # TUI keeps only narrator/router identity by default.
        tui_keys = [k for k in template.get("tui", {}) if not k.startswith("_")]
        assert tui_keys == ["narrator_agent_id"]


class TestLoadDotenv:
    """Tests for load_dotenv function."""

    def test_load_env_file(self, tmp_path: Path, monkeypatch):
        """Should load .env file and set environment variables."""
        env_content = "TEST_DOTENV_KEY=test_value\nTEST_DOTENV_OTHER=hello\n"
        (tmp_path / ".env").write_text(env_content, encoding="utf-8")
        # Ensure keys don't exist before
        monkeypatch.delenv("TEST_DOTENV_KEY", raising=False)
        monkeypatch.delenv("TEST_DOTENV_OTHER", raising=False)

        load_dotenv(tmp_path)

        assert os.environ.get("TEST_DOTENV_KEY") == "test_value"
        assert os.environ.get("TEST_DOTENV_OTHER") == "hello"

        # Cleanup
        os.environ.pop("TEST_DOTENV_KEY", None)
        os.environ.pop("TEST_DOTENV_OTHER", None)

    def test_does_not_override_existing(self, tmp_path: Path, monkeypatch):
        """Should not override existing environment variables."""
        env_content = "TEST_DOTENV_EXIST=new_value\n"
        (tmp_path / ".env").write_text(env_content, encoding="utf-8")
        monkeypatch.setenv("TEST_DOTENV_EXIST", "original")

        load_dotenv(tmp_path)

        assert os.environ.get("TEST_DOTENV_EXIST") == "original"

    def test_ignores_comments_and_blanks(self, tmp_path: Path, monkeypatch):
        """Should ignore comments and blank lines."""
        env_content = "# This is a comment\n\nTEST_DOTENV_COMMENT=works\n  \n"
        (tmp_path / ".env").write_text(env_content, encoding="utf-8")
        monkeypatch.delenv("TEST_DOTENV_COMMENT", raising=False)

        load_dotenv(tmp_path)

        assert os.environ.get("TEST_DOTENV_COMMENT") == "works"
        os.environ.pop("TEST_DOTENV_COMMENT", None)

    def test_strips_quotes(self, tmp_path: Path, monkeypatch):
        """Should strip surrounding quotes from values."""
        env_content = "TEST_DOTENV_DQ=\"double quoted\"\nTEST_DOTENV_SQ='single quoted'\n"
        (tmp_path / ".env").write_text(env_content, encoding="utf-8")
        monkeypatch.delenv("TEST_DOTENV_DQ", raising=False)
        monkeypatch.delenv("TEST_DOTENV_SQ", raising=False)

        load_dotenv(tmp_path)

        assert os.environ.get("TEST_DOTENV_DQ") == "double quoted"
        assert os.environ.get("TEST_DOTENV_SQ") == "single quoted"

        os.environ.pop("TEST_DOTENV_DQ", None)
        os.environ.pop("TEST_DOTENV_SQ", None)

    def test_missing_env_file_is_noop(self, tmp_path: Path):
        """Should silently do nothing if .env file doesn't exist."""
        load_dotenv(tmp_path)  # Should not raise


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass and parsing (M11-T1)."""

    def test_defaults(self):
        """Should have sensible defaults."""
        config = MCPServerConfig()
        assert config.command == ""
        assert config.args == []
        assert config.env == {}
        assert config.url == ""
        assert config.transport == "stdio"
        assert config.enabled is True
        assert config.permission == "confirm"
        assert config.tool_permissions == {}
        assert config.timeout_s == 30

    def test_load_mcp_servers_from_config(self, tmp_path: Path):
        """Should parse mcp_servers section from config.json."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "mcp_servers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                    "transport": "stdio",
                    "enabled": True,
                    "permission": "auto",
                    "timeout_s": 60,
                    "tool_permissions": {"write_file": "confirm"},
                },
                "dice": {
                    "command": "python",
                    "args": ["dice_server.py"],
                    "permission": "deny",
                },
            }
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")

        config = load_config(tmp_path)
        assert len(config.mcp_servers) == 2
        fs = config.mcp_servers["filesystem"]
        assert fs.command == "npx"
        assert fs.args == ["-y", "@modelcontextprotocol/server-filesystem", "."]
        assert fs.transport == "stdio"
        assert fs.enabled is True
        assert fs.permission == "auto"
        assert fs.timeout_s == 60
        assert fs.tool_permissions == {"write_file": "confirm"}

        dice = config.mcp_servers["dice"]
        assert dice.command == "python"
        assert dice.permission == "deny"
        assert dice.enabled is True  # default

    def test_empty_mcp_servers_is_valid(self, tmp_path: Path):
        """Empty or missing mcp_servers should result in empty dict."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(json.dumps({"mcp_servers": {}}), encoding="utf-8")
        config = load_config(tmp_path)
        assert config.mcp_servers == {}

    def test_missing_mcp_servers_defaults_empty(self, tmp_path: Path):
        """Config without mcp_servers should have empty dict."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        (neonrp_dir / "config.json").write_text(json.dumps({"llm": {"provider": "stub"}}), encoding="utf-8")
        config = load_config(tmp_path)
        assert config.mcp_servers == {}

    def test_invalid_permission_falls_back(self, tmp_path: Path):
        """Invalid permission value should fallback to confirm."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "mcp_servers": {
                "bad": {"command": "echo", "permission": "yolo"},
            }
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")
        config = load_config(tmp_path)
        assert config.mcp_servers["bad"].permission == "confirm"

    def test_invalid_transport_falls_back(self, tmp_path: Path):
        """Invalid transport should fallback to stdio."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "mcp_servers": {
                "bad": {"command": "echo", "transport": "websocket"},
            }
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")
        config = load_config(tmp_path)
        assert config.mcp_servers["bad"].transport == "stdio"

    def test_comment_entries_in_mcp_servers_ignored(self, tmp_path: Path):
        """Non-dict entries (like _comment strings) should be skipped."""
        neonrp_dir = tmp_path / ".neonrp"
        neonrp_dir.mkdir()
        config_data = {
            "mcp_servers": {
                "_comment": "MCP servers here",
                "echo": {"command": "echo"},
            }
        }
        (neonrp_dir / "config.json").write_text(json.dumps(config_data), encoding="utf-8")
        config = load_config(tmp_path)
        assert len(config.mcp_servers) == 1
        assert "echo" in config.mcp_servers

    def test_apply_overrides_preserves_mcp_servers(self):
        """apply_overrides should carry forward mcp_servers."""
        base = ProjectConfig(
            llm=LLMConfig(),
            mcp_servers={"test": MCPServerConfig(command="echo")},
        )
        config = apply_overrides(base, {"provider": "openai"})
        assert "test" in config.mcp_servers
        assert config.mcp_servers["test"].command == "echo"

    def test_default_config_template_has_mcp_section(self):
        """Template should include mcp_servers section."""
        template = create_default_config_template()
        assert "mcp_servers" in template
