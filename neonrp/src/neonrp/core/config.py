"""Project configuration module for NeonRP.

Handles loading configuration from:
1. User config: ~/.neonrp/config.json (or %NEONRP_HOME%/config.json)
2. Project config: <project>/.neonrp/config.json

Project config overrides user config.
"""

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from neonrp.core.paths import get_neonrp_dir


CONFIG_FILENAME = "config.json"
USER_HOME_ENV = "NEONRP_HOME"
SUPPORTED_MODEL_PROVIDERS = {"stub", "openai", "anthropic", "glm", "gemini"}


@dataclass
class LLMConfig:
    """LLM runtime selection and limits.

    Notes:
    - `model_ref` points to the active named entry under top-level `models`.
    - Provider/model/temperature/etc. are retained as resolved runtime values for
      compatibility with existing code paths and tests.
    """

    model_ref: str = "stub"
    provider: str = "stub"
    model: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 4096
    seed: int | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # passthrough request fields (e.g. OpenRouter reasoning)
    max_retries: int = 3
    max_context_chars: int = 100000  # ~25K tokens, for budget tracking


@dataclass
class TUIConfig:
    """TUI configuration."""

    auto_apply: bool = False  # Auto-apply proposals without confirmation
    session_max_turns: int = 50  # Max user turns (not raw entries) to keep in session
    show_diff_preview: bool = True  # Show diff before applying
    max_tool_rounds: int = 40  # Max tool-calling rounds per conversation turn
    # 40, not 20: an orchestrator world-agent's opening legitimately needs
    # >20 rounds (read all startup.read_first files + delegate to domain
    # sub-agents + update run_state + narrate). 20 cut openings off mid-turn
    # with "exceeded max turns".
    narrator_agent_id: str = "narrator"  # Root routing agent id used by UI/conversation defaults
    language: str = "auto"  # UI locale hint: auto | en | zh


@dataclass
class RulesConfig:
    """Domain-rules configuration.

    Schema validation is always enforced separately; these toggles control
    the optional domain-specific validation/resolve layer.
    """

    enable_domain_validation: bool = True
    enable_resolve_action: bool = True
    profile_path: str | None = None  # project-root relative path preferred


@dataclass
class ProviderConfig:
    """Named model configuration (M8-T5).

    Stored in top-level `models` and referenced by `model_ref`
    (with `provider_ref` accepted as a legacy alias).
    """

    provider: str = "stub"
    model: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 4096
    seed: int | None = None
    base_url: str | None = None  # For custom endpoints (e.g., local Ollama)
    api_key_env: str | None = None  # Custom env var name for API key
    api_key: str | None = None  # Direct API key (stored in config)
    extra: dict[str, Any] = field(default_factory=dict)  # passthrough request fields (provider-specific)
    disable_streaming: bool = False  # disable streaming for unreliable endpoints (e.g. remote Ollama via VPN)


@dataclass
class MCPServerConfig:
    """MCP server configuration (M11-T1).

    Declares an MCP server that NeonRP can connect to and expose tools from.
    """

    command: str = ""  # stdio executable path
    args: list[str] = field(default_factory=list)  # command arguments
    env: dict[str, str] = field(default_factory=dict)  # extra env vars for subprocess
    url: str = ""  # SSE/remote URL (future use)
    transport: str = "stdio"  # "stdio" | "sse"
    enabled: bool = True  # whether this server is active
    permission: str = "confirm"  # "auto" | "confirm" | "deny"
    tool_permissions: dict[str, str] = field(default_factory=dict)  # tool-level overrides
    timeout_s: int = 30  # per-call timeout in seconds


@dataclass
class EmbeddingConfig:
    """Embedding configuration for vector search (opt-in).

    When enabled, entity embeddings are computed and used for semantic
    similarity in read_context retrieval.
    """

    enabled: bool = False  # opt-in: no vector search by default
    model_ref: str = ""  # references a named model in "models" for API credentials
    model: str = "text-embedding-3-small"  # embedding model name
    provider: str = ""  # resolved from model_ref or set directly
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    dimensions: int = 256  # lower dim for efficiency
    vector_weight: float = 0.4  # weight in hybrid scoring (0.0=fuzzy-only, 1.0=vector-only)


@dataclass
class ProjectConfig:
    """Project-level configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    tui: TUIConfig = field(default_factory=TUIConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    max_sub_agent_depth: int = 2  # 2 = parent + 1 sub-agent level
    providers: dict[str, ProviderConfig] = field(default_factory=dict)  # Backed by config key: models
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)  # M11: MCP servers

    @property
    def models(self) -> dict[str, ProviderConfig]:
        """Alias for named model registry (`providers` internal name retained for compatibility)."""
        return self.providers

    @classmethod
    def default(cls) -> "ProjectConfig":
        """Create with default values."""
        return cls(
            llm=LLMConfig(), tui=TUIConfig(), rules=RulesConfig(),
            embedding=EmbeddingConfig(), providers={}, mcp_servers={},
        )


def get_config_path(root: Path) -> Path:
    """Get the config file path."""
    return get_neonrp_dir(root) / CONFIG_FILENAME


def get_user_neonrp_dir() -> Path:
    """Get user-level NeonRP config directory."""
    custom_home = os.environ.get(USER_HOME_ENV)
    if custom_home:
        return Path(custom_home)
    return Path.home() / ".neonrp"


def get_user_config_path() -> Path:
    """Get user-level config path (~/.neonrp/config.json by default)."""
    return get_user_neonrp_dir() / CONFIG_FILENAME


def _read_config_dict(path: Path) -> dict[str, Any] | None:
    """Read JSON config file into dict, returning None on failure."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None
    return data if isinstance(data, dict) else None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dicts. Values in override win."""
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def _is_env_var_name(value: Any) -> bool:
    """Return True if value looks like an env var token (e.g., OPENAI_API_KEY)."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value:
        return False
    if not value.replace("_", "").isalnum():
        return False
    return value.upper() == value and "_" in value


def _merge_user_and_project_config(
    user_data: dict[str, Any] | None,
    project_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge user and project config.

    Standard priority: project > user > built-in defaults.
    User config provides the base; project config overrides it.
    """
    if user_data is None and project_data is None:
        return {}
    if user_data is None:
        return dict(project_data or {})
    if project_data is None:
        return dict(user_data)

    return _deep_merge(user_data, project_data)


def _use_user_config_by_default() -> bool:
    """Whether load_config should include user config."""
    if os.environ.get("NEONRP_DISABLE_USER_CONFIG") == "1":
        return False
    # Keep tests deterministic regardless of the developer machine state.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def load_config(root: Path, *, include_user_config: bool | None = None) -> ProjectConfig:
    """Load configuration with optional user-level fallback.

    Merge order:
    1) user config (optional)
    2) project config
    Later layers override earlier ones.

    Args:
        root: Project root directory
        include_user_config: Whether to include user config. If None, use default policy.

    Returns:
        ProjectConfig with loaded or default values
    """
    config_path = get_config_path(root)
    user_config_path = get_user_config_path()

    if include_user_config is None:
        include_user_config = _use_user_config_by_default()

    user_data = _read_config_dict(user_config_path) if include_user_config else None
    project_data = _read_config_dict(config_path)
    merged = _merge_user_and_project_config(user_data, project_data)

    if not merged:
        return ProjectConfig.default()

    try:
        return _parse_config(merged)
    except Exception:
        # Invalid config - return defaults
        return ProjectConfig.default()


def _parse_provider_config(data: dict[str, Any]) -> ProviderConfig:
    """Parse a provider configuration dict into ProviderConfig."""
    api_key_env = data.get("api_key_env")
    api_key = data.get("api_key")
    # Backward compatibility: old /auth set could store raw key in api_key_env.
    if not api_key and api_key_env and not _is_env_var_name(api_key_env):
        api_key = api_key_env
        api_key_env = None
    extra = data.get("extra")
    if not isinstance(extra, dict):
        extra = {}

    return ProviderConfig(
        provider=data.get("provider", "stub"),
        model=data.get("model", ""),
        temperature=data.get("temperature", 0.7),
        max_output_tokens=data.get("max_output_tokens", 4096),
        seed=data.get("seed"),
        base_url=data.get("base_url"),
        api_key_env=api_key_env,
        api_key=api_key,
        extra=dict(extra),
        disable_streaming=bool(data.get("disable_streaming", False)),
    )


def _parse_mcp_server_config(data: dict[str, Any]) -> MCPServerConfig:
    """Parse a single MCP server configuration dict into MCPServerConfig."""
    # Parse tool_permissions ensuring values are valid
    raw_tool_perms = data.get("tool_permissions", {})
    tool_permissions: dict[str, str] = {}
    if isinstance(raw_tool_perms, dict):
        valid_perms = {"auto", "confirm", "deny"}
        for tool_name, perm in raw_tool_perms.items():
            if isinstance(perm, str) and perm in valid_perms:
                tool_permissions[str(tool_name)] = perm

    permission = data.get("permission", "confirm")
    if permission not in {"auto", "confirm", "deny"}:
        permission = "confirm"

    transport = data.get("transport", "stdio")
    if transport not in {"stdio", "sse"}:
        transport = "stdio"

    return MCPServerConfig(
        command=str(data.get("command", "")),
        args=[str(a) for a in data.get("args", []) if isinstance(data.get("args"), list)] if isinstance(data.get("args"), list) else [],
        env={str(k): str(v) for k, v in data.get("env", {}).items()} if isinstance(data.get("env"), dict) else {},
        url=str(data.get("url", "")),
        transport=transport,
        enabled=bool(data.get("enabled", True)),
        permission=permission,
        tool_permissions=tool_permissions,
        timeout_s=int(data.get("timeout_s", 30)),
    )


def _parse_config(data: dict[str, Any]) -> ProjectConfig:
    """Parse config dict into ProjectConfig."""
    llm_data = data.get("llm", {})
    tui_data = data.get("tui", {})
    rules_data = data.get("rules", {})
    models_data = data.get("models")
    if not isinstance(models_data, dict):
        # Backward compatibility: pre-migration key.
        models_data = data.get("providers", {})

    tui = TUIConfig(
        auto_apply=tui_data.get("auto_apply", False),
        session_max_turns=tui_data.get("session_max_turns", 50),
        show_diff_preview=tui_data.get("show_diff_preview", True),
        max_tool_rounds=tui_data.get("max_tool_rounds", 40),
        narrator_agent_id=str(tui_data.get("narrator_agent_id", "narrator") or "narrator").strip() or "narrator",
        language=str(tui_data.get("language", "auto") or "auto").strip() or "auto",
    )

    profile_path = rules_data.get("profile_path") if isinstance(rules_data, dict) else None
    if profile_path is not None and not isinstance(profile_path, str):
        profile_path = None
    rules = RulesConfig(
        enable_domain_validation=bool(rules_data.get("enable_domain_validation", True))
        if isinstance(rules_data, dict)
        else True,
        enable_resolve_action=bool(rules_data.get("enable_resolve_action", True))
        if isinstance(rules_data, dict)
        else True,
        profile_path=profile_path,
    )

    # Parse named model registry (M8-T5)
    providers: dict[str, ProviderConfig] = {}
    for name, pdata in models_data.items():
        if not isinstance(pdata, dict):
            # Allow comment-like scalar entries in config templates.
            continue
        providers[name] = _parse_provider_config(pdata)

    # Backward compatibility: if no named models exist but legacy llm has inline provider settings,
    # synthesize a "default" model entry from legacy fields.
    if not providers and isinstance(llm_data, dict) and llm_data.get("provider"):
        providers["default"] = _parse_provider_config(llm_data)

    selected_model_ref = llm_data.get("model_ref")
    if not selected_model_ref:
        # Legacy fallback: llm.model might be a model ref if it matches a registry key.
        llm_model_field = llm_data.get("model")
        if isinstance(llm_model_field, str) and llm_model_field in providers:
            selected_model_ref = llm_model_field

    if not selected_model_ref:
        selected_model_ref = "default" if "default" in providers else "stub"

    if selected_model_ref not in providers and providers:
        selected_model_ref = next(iter(providers.keys()))

    active_provider = providers.get(selected_model_ref, ProviderConfig(provider="stub"))
    llm_extra = dict(active_provider.extra) if isinstance(active_provider.extra, dict) else {}
    inline_extra = llm_data.get("extra")
    if isinstance(inline_extra, dict):
        llm_extra = _deep_merge(llm_extra, inline_extra)
    llm = LLMConfig(
        model_ref=selected_model_ref,
        provider=active_provider.provider,
        model=active_provider.model,
        temperature=active_provider.temperature,
        max_output_tokens=active_provider.max_output_tokens,
        seed=active_provider.seed,
        base_url=active_provider.base_url,
        api_key_env=active_provider.api_key_env,
        api_key=active_provider.api_key,
        extra=llm_extra,
        max_retries=llm_data.get("max_retries", 3),
        max_context_chars=llm_data.get("max_context_chars", 100000),
    )

    # Parse MCP servers (M11)
    mcp_servers_data = data.get("mcp_servers", {})
    mcp_servers: dict[str, MCPServerConfig] = {}
    if isinstance(mcp_servers_data, dict):
        for name, sdata in mcp_servers_data.items():
            if not isinstance(sdata, dict):
                continue
            mcp_servers[name] = _parse_mcp_server_config(sdata)

    # Parse embedding config (vector search)
    emb_data = data.get("embedding", {})
    if not isinstance(emb_data, dict):
        emb_data = {}
    embedding = EmbeddingConfig(enabled=bool(emb_data.get("enabled", False)))
    if embedding.enabled:
        emb_model_ref = emb_data.get("model_ref", "")
        emb_provider_cfg = providers.get(emb_model_ref, ProviderConfig()) if emb_model_ref else ProviderConfig()
        # Prefer explicit embedding.model; otherwise inherit model from referenced
        # named model entry to support minimal embedding config:
        # {"embedding": {"enabled": true, "model_ref": "..."}}
        resolved_embedding_model = emb_data.get("model") or emb_provider_cfg.model or "text-embedding-3-small"
        embedding = EmbeddingConfig(
            enabled=True,
            model_ref=emb_model_ref,
            model=resolved_embedding_model,
            provider=emb_data.get("provider", emb_provider_cfg.provider),
            base_url=emb_data.get("base_url", emb_provider_cfg.base_url),
            api_key_env=emb_data.get("api_key_env", emb_provider_cfg.api_key_env),
            api_key=emb_data.get("api_key", emb_provider_cfg.api_key),
            dimensions=emb_data.get("dimensions", 256),
            vector_weight=emb_data.get("vector_weight", 0.4),
        )

    return ProjectConfig(
        llm=llm,
        tui=tui,
        rules=rules,
        embedding=embedding,
        max_sub_agent_depth=data.get("max_sub_agent_depth", 2),
        providers=providers,
        mcp_servers=mcp_servers,
    )


def apply_overrides(config: ProjectConfig, overrides: dict[str, Any]) -> ProjectConfig:
    """Apply CLI flag overrides to config.

    Args:
        config: Base configuration
        overrides: Dict of override values (provider, model, temperature, etc.)

    Returns:
        New ProjectConfig with overrides applied
    """
    llm = LLMConfig(
        model_ref=overrides.get("model_ref", config.llm.model_ref),
        provider=overrides.get("provider", config.llm.provider),
        model=overrides.get("model", config.llm.model),
        temperature=overrides.get("temperature", config.llm.temperature),
        max_output_tokens=overrides.get("max_output_tokens", config.llm.max_output_tokens),
        seed=overrides.get("seed", config.llm.seed),
        base_url=overrides.get("base_url", config.llm.base_url),
        api_key_env=overrides.get("api_key_env", config.llm.api_key_env),
        api_key=overrides.get("api_key", config.llm.api_key),
        extra=overrides.get("extra", config.llm.extra),
        max_retries=overrides.get("max_retries", config.llm.max_retries),
        max_context_chars=overrides.get("max_context_chars", config.llm.max_context_chars),
    )

    tui = TUIConfig(
        auto_apply=overrides.get("auto_apply", config.tui.auto_apply),
        session_max_turns=overrides.get("session_max_turns", config.tui.session_max_turns),
        show_diff_preview=overrides.get("show_diff_preview", config.tui.show_diff_preview),
        max_tool_rounds=overrides.get("max_tool_rounds", config.tui.max_tool_rounds),
        narrator_agent_id=overrides.get("narrator_agent_id", config.tui.narrator_agent_id),
        language=overrides.get("language", config.tui.language),
    )

    return ProjectConfig(
        llm=llm,
        tui=tui,
        rules=config.rules,
        embedding=config.embedding,
        max_sub_agent_depth=config.max_sub_agent_depth,
        providers=config.providers,
        mcp_servers=config.mcp_servers,
    )


def get_api_key(provider: str) -> str | None:
    """Get API key for provider from environment.

    Checks:
    1. NEONRP_LLM_API_KEY (generic)
    2. Provider-specific (e.g., OPENAI_API_KEY, ANTHROPIC_API_KEY)

    Args:
        provider: Provider name (openai, anthropic, etc.)

    Returns:
        API key string or None if not found
    """
    # Check generic key first
    key = os.environ.get("NEONRP_LLM_API_KEY")
    if key:
        return key

    provider_upper = provider.upper()
    # Allow passing a literal env var name (e.g., OPENAI_API_KEY)
    if provider_upper.endswith("_API_KEY"):
        return os.environ.get(provider_upper)

    # Check provider-specific
    provider_key = os.environ.get(f"{provider_upper}_API_KEY")
    if provider_key:
        return provider_key

    return None


def resolve_provider(
    config: ProjectConfig,
    agent_llm_config: dict[str, Any] | None = None,
    cli_provider: str | None = None,
) -> ProviderConfig:
    """Resolve LLM provider configuration with priority (M8-T5).

    Priority order (highest to lowest):
    1. CLI --provider override (over active model config)
    2. Agent inline LLM config
    3. Agent model_ref/provider_ref (reference to named model in config.models)
    4. Global config.llm.model_ref

    Args:
        config: Project configuration
        agent_llm_config: Optional LLM config from agent.json {"llm": {...}}
        cli_provider: Optional CLI --provider override

    Returns:
        ProviderConfig to use for adapter creation
    """
    def _base_from_model_ref(model_ref: str | None) -> ProviderConfig:
        if model_ref and model_ref in config.providers:
            cfg = config.providers[model_ref]
            llm_extra = getattr(config.llm, "extra", {})
            if isinstance(llm_extra, dict) and llm_extra:
                return replace(cfg, extra=_deep_merge(dict(cfg.extra), llm_extra))
            return cfg
        legacy_fields_present = bool(
            config.llm.model
            or config.llm.base_url
            or config.llm.api_key_env
            or config.llm.api_key
            or config.llm.provider not in {"", "stub"}
        )
        if legacy_fields_present:
            return ProviderConfig(
                provider=config.llm.provider,
                model=config.llm.model,
                temperature=config.llm.temperature,
                max_output_tokens=config.llm.max_output_tokens,
                seed=config.llm.seed,
                base_url=config.llm.base_url,
                api_key_env=config.llm.api_key_env,
                api_key=config.llm.api_key,
                extra=config.llm.extra,
            )
        if config.providers:
            return next(iter(config.providers.values()))
        return ProviderConfig(
            provider=config.llm.provider,
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_output_tokens=config.llm.max_output_tokens,
            seed=config.llm.seed,
            base_url=config.llm.base_url,
            api_key_env=config.llm.api_key_env,
            api_key=config.llm.api_key,
            extra=config.llm.extra,
        )

    base_cfg = _base_from_model_ref(getattr(config.llm, "model_ref", None))

    # Priority 1: CLI override - keep active model fields, override provider protocol.
    if cli_provider:
        return replace(base_cfg, provider=cli_provider)

    # Check agent config
    if agent_llm_config:
        # Priority 2: Agent inline config (has "provider" key)
        if "provider" in agent_llm_config:
            resolved_extra = agent_llm_config.get("extra", base_cfg.extra)
            if not isinstance(resolved_extra, dict):
                resolved_extra = base_cfg.extra
            return ProviderConfig(
                provider=agent_llm_config.get("provider", base_cfg.provider),
                model=agent_llm_config.get("model", base_cfg.model),
                temperature=agent_llm_config.get("temperature", base_cfg.temperature),
                max_output_tokens=agent_llm_config.get("max_output_tokens", base_cfg.max_output_tokens),
                seed=agent_llm_config.get("seed", base_cfg.seed),
                base_url=agent_llm_config.get("base_url", base_cfg.base_url),
                api_key_env=agent_llm_config.get("api_key_env", base_cfg.api_key_env),
                api_key=agent_llm_config.get("api_key", base_cfg.api_key),
                extra=resolved_extra,
            )

        # Priority 3: Agent model_ref (provider_ref kept as legacy alias)
        model_ref = agent_llm_config.get("model_ref") or agent_llm_config.get("provider_ref")
        if model_ref and model_ref in config.providers:
            return config.providers[model_ref]

    # Priority 4: Global selected model
    return base_cfg


def create_default_config_template() -> dict[str, Any]:
    """Create a default config.json template for init command.

    Returns:
        Dict that can be serialized to JSON
    """
    return {
        "_comment": (
            "NeonRP project config. Only set keys you want to override. "
            "User config (~/.neonrp/config.json) provides defaults; "
            "project config takes priority. "
            "Models and TUI prefs are usually set in user config."
        ),
        "llm": {
            "_comment": "Set model_ref to select a model from user or project 'models' section.",
        },
        "tui": {
            "_comment": "Optional TUI overrides. narrator_agent_id defines which agent is treated as the top-level narrator/router.",
            "narrator_agent_id": "narrator",
        },
        "rules": {
            "_comment": "Optional data-driven domain rules profile (project-root relative path).",
        },
        "models": {
            "_comment": "Project-specific models. User-level models are inherited automatically.",
            "stub": {"provider": "stub", "model": "stub"},
        },
        "mcp_servers": {
            "_comment": "MCP servers - declare external tool servers here.",
        },
    }


def load_dotenv(root: Path) -> None:
    """Load environment variables from .env file in project root.

    Simple .env parser: supports KEY=VALUE lines, ignores comments (#) and blanks.
    Values may be optionally quoted with single or double quotes.
    Does NOT override existing environment variables.

    Args:
        root: Project root directory
    """
    env_path = root / ".env"
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip optional quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            # Don't override existing env vars
            if key and key not in os.environ:
                os.environ[key] = value
    except IOError:
        pass
