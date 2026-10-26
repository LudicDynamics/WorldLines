"""WorldLines model presets.

Each preset generates a config.json compatible with NeonRP's
``models`` registry + ``model_ref`` system (zero modifications needed).

Presets come from two sources:
1. Built-in PRESETS dict (standard providers: openai, anthropic, glm)
2. User's ~/.neonrp/config.json ``models`` section (custom/local endpoints)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# The chat models ai.worldlines.gg serves (GET https://ai.worldlines.gg/v1/models, kind = chat; read 2026-10-13).
# A preset pointing at the relay must name one of these — the relay answers any other id with 404 model_not_found.
# Refresh this list when the platform's catalog changes (services/ai migrations / admin PUT /admin/v1/models).
WORLDLINES_CATALOG_CHAT: tuple[str, ...] = (
    "deepseek-chat",
    "deepseek-flash",
    "deepseek-reasoner",
    "deepseek-v4-flash",
    "deepseek-v4-pro",
)

PRESETS: dict[str, dict[str, Any]] = {
    # No active "Recommended" pick at the moment. DeepSeek-V4 Pro was
    # promoted in v0.1.9 but the model heavily prefers Chinese output
    # regardless of the prompt's locale, so the ✨ badge mis-leads
    # non-zh users. Picker order kept (deepseek still first), badge
    # removed pending a re-evaluation. list_presets() walks dict in
    # insertion order, which is also the picker order.
    # OpenCode Zen — a hosted, OpenAI-compatible gateway. Listed first as the
    # recommended default: its DeepSeek-V4 Pro ("蓝鲸"/whale) is strong enough
    # for the multi-agent loop. Two gotchas verified against the live endpoint:
    # (1) the OpenAI-compatible /chat/completions wants the BARE model id
    # `deepseek-v4-pro` — the docs' `opencode/`-prefixed id returns ModelError;
    # (2) the endpoint sits behind Cloudflare, which 403s a UA-less request, so
    # the ping MUST send a User-Agent (see _ping_openai_compatible). A free
    # `deepseek-v4-flash-free` also exists but is too weak for multi-agent.
    "opencode": {
        "display": "OpenCode Zen · DeepSeek-V4.1 Flash",
        "provider": "openai",
        "model": "deepseek-v4.1-flash",
        "base_url": "https://opencode.ai/zen/v1",
        "api_key_env": "OPENCODE_ZEN_API_KEY",
        "key_hint": "opencode.ai/zen",
        "temperature": 0.7,
        "max_output_tokens": 4096,
    },
    "deepseek": {
        "display": "DeepSeek-V4.1 Flash",
        "provider": "openai",
        # 官方 API 只认 deepseek-flash(=最新 Flash,10-17 是 V4.1)和 deepseek-v4-pro;
        # deepseek-v4.1-flash 是 opencode 的 id,官方回 400。
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "key_hint": "platform.deepseek.com/api_keys",
        "temperature": 0.7,
        # V4 Pro 官方输出上限 384K/context 1M(2026-08 查证);4096 是 V3 时代
        # 的过时默认,创作整份文件必截断。16K 单文件绰绰有余,截断续写兜底。
        "max_output_tokens": 16384,
    },
    # Worldlines — our model relay (ai.worldlines.gg, OpenAI-compatible; engine-side 10-01). No key needed when the
    # player has connected (`python -m neonrp.core.worldlines_auth connect`); WORLDLINES_API_KEY = a wl_pat_ with api:use.
    "worldlines": {
        "display": "Worldlines",
        "provider": "openai",
        # an id in ai.worldlines.gg's catalog (GET /v1/models; 10-13: v4.1 is DeepSeek's own name, the relay 404s it).
        # tests/test_worldlines_catalog.py pins this against WORLDLINES_CATALOG_CHAT below.
        "model": "deepseek-v4-flash",
        # WORLDLINES_API_BASE (core/worldlines_auth) moves it too: the browser engine's e2e build points it at a local fake
        "base_url": os.environ.get("WORLDLINES_API_BASE", "https://ai.worldlines.gg/v1"),
        "api_key_env": "WORLDLINES_API_KEY",
        "key_hint": "auth.worldlines.gg/connect",
        "temperature": 0.7,
        "max_output_tokens": 16384,
    },
    # Moonshot Kimi K3 — OpenAI-compatible, strong tool-call (verified
    # 2026-07: base_url / model / auth correct; account just needs balance).
    "kimi-k3": {
        "display": "Kimi K3",
        "provider": "openai",
        "model": "kimi-k3",
        "base_url": "https://api.moonshot.ai/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "key_hint": "platform.kimi.ai",
        # Kimi K3 只接受 temperature=1(其它值 → 400 invalid_request_error);别改。
        "temperature": 1.0,
        "max_output_tokens": 4096,
    },
    "anthropic": {
        # One Anthropic entry; default to Opus (top-tier; Sonnet stays
        # available via Settings → Anthropic → model picker).
        "display": "Anthropic Claude",
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_hint": "console.anthropic.com/settings/keys",
        "temperature": 0.7,
        "max_output_tokens": 4096,
    },
    "openai": {
        "display": "OpenAI GPT",
        "provider": "openai",
        "model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "key_hint": "platform.openai.com/api-keys",
        "temperature": 0.7,
        "max_output_tokens": 4096,
    },
    "openrouter": {
        "display": "OpenRouter",
        "provider": "openai",
        "model": "anthropic/claude-sonnet-4.5",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "key_hint": "openrouter.ai/keys",
        "temperature": 0.7,
        "max_output_tokens": 4096,
    },
    # GLM-4.7-Flash from Zhipu — free tier, supports tool-call and
    # reasoning_content (latter requires `thinking.type=enabled` in
    # request extras). Listed last + dimmed in the picker; surfaced
    # mainly as a "no budget? try this" entry-level option.
    "glm": {
        "display": "GLM-4.7-Flash (free)",
        "provider": "openai",
        "model": "glm-4.7-flash",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "key_hint": "zhipuai.cn",
        "temperature": 0.85,
        "max_output_tokens": 4096,
    },
}

# Provider TYPES offered in "Add new" flow.
# Each entry is the starting template for a new user-config entry.
PROVIDER_TYPES: list[dict[str, Any]] = [
    {
        "id": "anthropic",
        "label": "Anthropic (Claude)",
        "provider": "anthropic",
        "default_model": "claude-opus-4-6",
        "models": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "base_url": None,
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_hint": "console.anthropic.com/settings/keys",
    },
    {
        "id": "openai",
        "label": "OpenAI (GPT)",
        "provider": "openai",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4-turbo", "gpt-4.1", "o1", "o3"],
        "base_url": None,
        "api_key_env": "OPENAI_API_KEY",
        "key_hint": "platform.openai.com/api-keys",
    },
    {
        "id": "opencode",
        "label": "OpenCode Zen",
        "provider": "openai",
        # Bare model ids (no `opencode/` prefix) — that's what the OpenAI-
        # compatible endpoint accepts; the prefixed id returns ModelError.
        # deepseek 通用改 V4.1 Flash(不再默认 V4 Pro)。旧 id 保留备选。
        "default_model": "deepseek-v4.1-flash",
        "models": ["deepseek-v4.1-flash", "deepseek-v4-pro", "deepseek-v4-flash-free"],
        "base_url": "https://opencode.ai/zen/v1",
        "api_key_env": "OPENCODE_ZEN_API_KEY",
        "key_hint": "opencode.ai/zen",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "provider": "openai",
        # 官方 API 的 id 只有这两个(10-17 /models);旧 id(v4-flash 等)暂时转到 deepseek-flash。
        "default_model": "deepseek-flash",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "key_hint": "platform.deepseek.com/api_keys",
    },
    {
        "id": "glm",
        "label": "GLM (Zhipu)",
        "provider": "openai",
        "default_model": "glm-4.7-flash",
        # `glm-4-flash` retained as a fallback in case user-side configs
        # still alias the older name on bigmodel.cn.
        "models": ["glm-4.7-flash", "glm-4-flash"],
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "key_hint": "zhipuai.cn",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "provider": "openai",
        "default_model": "anthropic/claude-sonnet-4.5",
        "models": [m["id"] for m in [
            {"id": "anthropic/claude-sonnet-4.5"},
            {"id": "anthropic/claude-opus-4.1"},
            {"id": "openai/gpt-4o"},
            {"id": "google/gemini-2.5-pro"},
            {"id": "deepseek/deepseek-chat"},
            {"id": "meta-llama/llama-3.3-70b-instruct"},
        ]],
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "key_hint": "openrouter.ai/keys",
        "fetch_catalog": True,
    },
    {
        "id": "custom",
        "label": "Custom (OpenAI-compatible endpoint)",
        "provider": "openai",
        "default_model": "",
        "models": [],
        "base_url": "",
        "api_key_env": None,
        "key_hint": "",
    },
]


def get_provider_type(type_id: str) -> dict[str, Any] | None:
    for entry in PROVIDER_TYPES:
        if entry["id"] == type_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# Config health test — small API ping per provider type.
# ---------------------------------------------------------------------------

def test_preset(preset_id: str, *, timeout: float = 6.0) -> dict[str, Any]:
    """Send a tiny "say ok" request to the preset's endpoint.

    Returns a dict with:
        ok        — bool
        latency_ms— int (only when ok)
        error     — str  (only when not ok; short human-readable label)
        provider  — str  (for display)
        model     — str  (for display)
    """
    import time

    entry = _resolve_effective_entry(preset_id)
    if entry is None:
        return {"ok": False, "error": f"Unknown preset: {preset_id}"}

    provider = str(entry.get("provider", "")).lower()
    model = str(entry.get("model", "") or "").strip()
    api_key = str(entry.get("api_key", "") or "").strip()

    if not api_key and entry.get("api_key_env"):
        api_key = os.environ.get(entry["api_key_env"], "").strip()

    # Short-circuit fail fast — don't burn the timeout on entries we know
    # can't authenticate.
    if not api_key and provider != "stub":
        return {"ok": False, "provider": provider, "model": model, "error": "no API key configured"}

    start = time.time()
    try:
        if provider == "anthropic":
            ok, err = _ping_anthropic(api_key, model, timeout)
        elif provider == "openai":
            ok, err = _ping_openai_compatible(
                api_key,
                model,
                str(entry.get("base_url", "") or "https://api.openai.com/v1"),
                timeout,
            )
        elif provider == "stub":
            ok, err = True, None
        else:
            return {"ok": False, "provider": provider, "model": model, "error": f"unsupported provider: {provider}"}
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "error": _clean_network_error(exc),
        }

    elapsed = int((time.time() - start) * 1000)
    if not ok:
        return {
            "ok": False,
            "provider": provider,
            "model": model,
            "error": err or "unknown error",
            "latency_ms": elapsed,
        }
    return {"ok": True, "provider": provider, "model": model, "latency_ms": elapsed}


def _resolve_effective_entry(preset_id: str) -> dict[str, Any] | None:
    """Merge built-in PRESETS defaults with user-config overrides."""
    merged: dict[str, Any] = {}
    if preset_id in PRESETS:
        merged.update(PRESETS[preset_id])
    user_models = _load_user_config_models()
    if preset_id in user_models:
        merged.update(user_models[preset_id])
    return merged or None


def _clean_network_error(exc: Exception) -> str:
    """Turn raw urllib / socket errors into short human-readable labels."""
    import socket

    msg = str(exc) or exc.__class__.__name__
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return "timeout"
    if "getaddrinfo failed" in msg.lower() or "name or service not known" in msg.lower():
        return "DNS failed (check network / base_url)"
    if "connection refused" in msg.lower():
        return "connection refused"
    if "ssl" in msg.lower() and "verify" in msg.lower():
        return "TLS verification failed"
    return msg[:200]


def _user_agent() -> str:
    """A real User-Agent for the ping requests. urllib's default
    (``Python-urllib/x``) is blocked by some edge/WAF layers — notably
    Cloudflare-fronted gateways like OpenCode Zen return 403 (error 1010) to
    it, so the connection test falsely fails even though the openai SDK (which
    sends its own UA) would succeed. Sending a normal product UA gets us past
    the WAF to the real auth result."""
    try:
        from neonrp import __version__

        return f"WorldLines/{__version__} (+https://worldlines.gg)"
    except Exception:
        return "WorldLines (+https://worldlines.gg)"


def _ping_anthropic(api_key: str, model: str, timeout: float) -> tuple[bool, str | None]:
    import urllib.request
    import urllib.error

    body = json.dumps(
        {
            "model": model or "claude-haiku-4-5-20251001",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "ok"}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": _user_agent(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("type") == "message":
            return True, None
        return False, f"unexpected response: {str(payload)[:160]}"
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {body_text}"
    except Exception as exc:
        return False, _clean_network_error(exc)


def _ping_openai_compatible(api_key: str, model: str, base_url: str, timeout: float) -> tuple[bool, str | None]:
    import urllib.request
    import urllib.error

    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "say ok"}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "User-Agent": _user_agent(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and "choices" in payload:
            return True, None
        return False, f"unexpected response: {str(payload)[:160]}"
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {body_text}"
    except Exception as exc:
        return False, _clean_network_error(exc)


# Providers for which users may want to pick a specific model at preset time.
# Maps preset_id -> (models_endpoint, suggested curated models).
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_SUGGESTED_MODELS: list[dict[str, str]] = [
    {"id": "anthropic/claude-sonnet-4.5", "label": "Claude Sonnet 4.5 (默认)"},
    {"id": "anthropic/claude-opus-4.1", "label": "Claude Opus 4.1"},
    {"id": "openai/gpt-4o", "label": "GPT-4o"},
    {"id": "google/gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
    {"id": "deepseek/deepseek-chat", "label": "DeepSeek Chat"},
    {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B"},
]

# Model name fragments that indicate a pure embedding model (skip from chat preset list)
_EMBEDDING_FRAGMENTS = ("embedding", "embed")

_USER_CONFIG_PATH = Path.home() / ".neonrp" / "config.json"


# ---------------------------------------------------------------------------
# User config helpers
# ---------------------------------------------------------------------------

# ``models.*`` keys that are not chat-model entries: the judge's own key and its preset pick (core/judge_settings,
# read by core/system_one) — never a model to play with, so never listed, tested or offered as a preset.
_NON_MODEL_KEYS = frozenset({"typesafe", "judge"})


def _load_user_config_models() -> dict[str, dict[str, Any]]:
    """Read the ``models`` section from ~/.neonrp/config.json (chat-model entries only)."""
    try:
        if not _USER_CONFIG_PATH.exists():
            return {}
        data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
        raw = data.get("models", {})
        return {k: v for k, v in raw.items() if isinstance(v, dict) and k not in _NON_MODEL_KEYS} if isinstance(raw, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Creation-provider selection
#
# The world/soul *creation* LLM is independent of the per-game `model_ref`.
# Which provider creation uses is persisted as a top-level `create_provider`
# key in ~/.neonrp/config.json. When unset, resolve_creation_provider() falls
# back to the first configured OpenAI-compatible provider with a usable key
# (deepseek preferred for continuity), then to the deepseek defaults.
# ---------------------------------------------------------------------------

# Auto-pick preference order: try these provider ids first (when configured
# with a usable key) before scanning the rest. deepseek leads so existing
# users keep their current creation backend; openrouter is the founder's
# requested alternative.
_CREATE_AUTO_PREFERENCE = ("deepseek", "openrouter", "openai", "glm")


def get_create_provider() -> str | None:
    """Return the user's explicitly-selected creation provider id, if any."""
    try:
        if not _USER_CONFIG_PATH.exists():
            return None
        data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
        val = data.get("create_provider")
        return str(val) if val else None
    except Exception:
        return None


def set_create_provider(preset_id: str | None) -> None:
    """Persist (or clear) the creation provider id in ~/.neonrp/config.json."""
    try:
        if _USER_CONFIG_PATH.exists():
            data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
        else:
            data = {}
        if preset_id:
            data["create_provider"] = preset_id
        else:
            data.pop("create_provider", None)
        _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _USER_CONFIG_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def get_create_agent() -> str | None:
    """The local workbench's creation agent: None = the engine's own build session (with the creation provider above),
    or a local CLI ("claude-code" / "codex", webui/agent_cli_backend.py). Top-level ``create_agent`` in the user config."""
    try:
        if not _USER_CONFIG_PATH.exists():
            return None
        val = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")).get("create_agent")
        return str(val) if val else None
    except Exception:
        return None


def set_create_agent(agent_id: str | None) -> None:
    """Persist (or clear) the workbench creation agent; "engine" clears it."""
    try:
        data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")) if _USER_CONFIG_PATH.exists() else {}
        if agent_id and agent_id != "engine":
            data["create_agent"] = agent_id
        else:
            data.pop("create_agent", None)
        _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _provider_create_config(preset_id: str) -> tuple[str, str, str | None] | None:
    """Resolve (base_url, model, api_key) for *preset_id* for creation use.

    Merges built-in PRESETS defaults with user-config overrides. Returns
    None when the provider is not OpenAI-compatible (creation only speaks
    the OpenAI SDK) or has no usable key.
    """
    entry = _resolve_effective_entry(preset_id)
    if not entry:
        return None
    if str(entry.get("provider", "")).lower() != "openai":
        # Creation engine is OpenAI-SDK only — skip anthropic/etc.
        return None

    api_key = str(entry.get("api_key", "") or "").strip()
    if not api_key:
        env_name = entry.get("api_key_env", "")
        if env_name:
            api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        return None

    base_url = str(entry.get("base_url", "") or "").strip() or "https://api.openai.com/v1"
    model = str(entry.get("model", "") or "").strip()
    return base_url, model, api_key


def resolve_creation_provider() -> tuple[str, str, str | None] | None:
    """Resolve the creation provider's (base_url, model, api_key).

    1. Explicit `create_provider` selection (if it has a usable key).
    2. Auto-pick: preferred ids first, then any remaining configured
       OpenAI-compatible provider with a usable key.

    Returns None when nothing usable is configured (caller falls back to
    deepseek defaults).
    """
    # 1. Explicit selection.
    chosen = get_create_provider()
    if chosen:
        cfg = _provider_create_config(chosen)
        if cfg is not None:
            return cfg

    # 2. Auto-pick — preference order first.
    candidates: list[str] = list(_CREATE_AUTO_PREFERENCE)
    # Then any other configured providers (PRESETS + user-config models),
    # preserving a stable order.
    for pid in (*PRESETS.keys(), *_load_user_config_models().keys()):
        if pid not in candidates and pid != "stub":
            candidates.append(pid)

    for pid in candidates:
        cfg = _provider_create_config(pid)
        if cfg is not None:
            return cfg

    return None


def _preset_usable(preset_id: str) -> bool:
    """A built-in with its key (or Worldlines while signed in), or a user-config model with a key — any provider."""
    if preset_id in PRESETS:
        return _preset_key_available(preset_id)
    entry = _load_user_config_models().get(preset_id)
    return bool(entry) and str(entry.get("provider", "stub")) != "stub" and _user_model_key_available(entry)


def resolve_creation_preset_id() -> str | None:
    """Which preset creation runs on, any provider (anthropic / gemini … too, not only OpenAI-compatible):
    the explicit ``create_provider`` when it is usable, else the first usable one — preference order first, then the rest.
    The auto-pick never lands on Worldlines (that spends the account's credits; pick it explicitly)."""
    chosen = get_create_provider()
    if chosen and _preset_usable(chosen):
        return chosen
    user = _load_user_config_models()
    candidates: list[str] = list(_CREATE_AUTO_PREFERENCE)
    for pid in (*PRESETS.keys(), *user.keys()):
        if pid not in candidates:
            candidates.append(pid)
    for pid in candidates:
        if pid in ("stub", "worldlines", "web") or (pid in user and _is_embedding_model(pid, user[pid])):
            continue
        if _preset_usable(pid):
            return pid
    return None


def _save_key_to_user_config(preset_id: str, key: str, *, model_override: str | None = None) -> None:
    """Persist an API key for a built-in preset into ~/.neonrp/config.json."""
    try:
        if _USER_CONFIG_PATH.exists():
            data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
        else:
            data = {}

        if "models" not in data or not isinstance(data["models"], dict):
            data["models"] = {}

        # Create or update the model entry. We merge into the existing
        # entry instead of overwriting — that way a user who edited the
        # `model` (e.g. deepseek → deepseek-v4-pro) and then re-entered
        # their API key doesn't see their model choice silently revert
        # to the PRESETS default. `model_override` (currently used by
        # the OpenRouter flow) still wins over both.
        preset = PRESETS.get(preset_id, {})
        entry = data["models"].get(preset_id, {})
        entry["provider"] = entry.get("provider") or preset.get("provider", "")
        if model_override:
            entry["model"] = model_override
        elif not entry.get("model"):
            entry["model"] = preset.get("model", "")
        entry["api_key"] = key
        if not entry.get("base_url") and preset.get("base_url"):
            entry["base_url"] = preset["base_url"]
        data["models"][preset_id] = entry

        _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def save_custom_model(
    model_id: str, base_url: str, model_name: str, api_key: str = ""
) -> str:
    """Persist a custom OpenAI-compatible model into ~/.neonrp/config.json.

    Shared by the TUI settings screen (custom endpoint flow) and the web
    settings API. Returns the normalized model id. Raises ValueError on bad
    input (empty id / base_url / model_name after normalization).
    """
    mid = (model_id or "").strip().lower().replace(" ", "-")
    base = (base_url or "").strip()
    model = (model_name or mid).strip()
    if not mid:
        raise ValueError("model id is required")
    if not base:
        raise ValueError("base_url is required")
    if not model:
        raise ValueError("model name is required")

    data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")) if _USER_CONFIG_PATH.exists() else {}
    if not isinstance(data.get("models"), dict):
        data["models"] = {}
    entry: dict[str, Any] = {"provider": "openai", "model": model, "base_url": base}
    if (api_key or "").strip():
        entry["api_key"] = api_key.strip()
    data["models"][mid] = entry
    _USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _USER_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return mid


def fetch_openrouter_models(api_key: str, *, timeout: float = 6.0) -> list[dict[str, str]]:
    """Fetch the OpenRouter model catalog. Returns [] on any failure."""
    try:
        import urllib.request

        req = urllib.request.Request(
            OPENROUTER_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "neonrp"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = payload.get("data", []) if isinstance(payload, dict) else []
        result: list[dict[str, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id", "")).strip()
            if not model_id:
                continue
            name = str(item.get("name") or model_id).strip()
            result.append({"id": model_id, "label": name})
        return result
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Key availability
# ---------------------------------------------------------------------------

def _worldlines_signed_in() -> bool:
    """A Worldlines session (/login) or PAT is here — the relay needs no key of the player's own then. Never raises."""
    try:
        from neonrp.core import worldlines_auth as wa

        return bool(wa.status().get("signed_in"))
    except Exception:  # noqa: BLE001
        return False


def _preset_key_available(preset_id: str) -> bool:
    """Return True if the API key for this built-in preset is already configured."""
    info = PRESETS.get(preset_id, {})
    if preset_id == "worldlines" and _worldlines_signed_in():
        return True

    # Direct key in PRESETS (shouldn't happen for built-ins, defensive)
    if info.get("api_key"):
        return True

    # Environment variable
    api_key_env = info.get("api_key_env", "")
    if api_key_env and os.environ.get(api_key_env):
        return True

    # Previously saved in user config
    user_models = _load_user_config_models()
    if preset_id in user_models and user_models[preset_id].get("api_key"):
        return True

    return False


def _user_model_key_available(model_data: dict[str, Any]) -> bool:
    """Return True if a user-config model has a usable API key."""
    if model_data.get("api_key"):
        return True
    api_key_env = model_data.get("api_key_env", "")
    return bool(api_key_env and os.environ.get(api_key_env))


def _is_embedding_model(model_id: str, model_data: dict[str, Any]) -> bool:
    combined = (model_id + " " + model_data.get("model", "")).lower()
    return any(frag in combined for frag in _EMBEDDING_FRAGMENTS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_presets() -> list[dict[str, Any]]:
    """Return display-friendly preset list (built-in + user config).

    Each entry:
    - ``id``:              identifier for build_config_dict / /wl-model
    - ``display``:         human label (includes ✓ if key found)
    - ``available``:       True if API key detected
    - ``from_user_config``: True if sourced from ~/.neonrp/config.json
    """
    result: list[dict[str, Any]] = []

    for preset_id, info in PRESETS.items():
        available = _preset_key_available(preset_id)
        badge = " ✓" if available else ""
        result.append({
            "id": preset_id,
            "display": f"{info['display']}{badge}",
            "available": available,
            "from_user_config": False,
        })

    user_models = _load_user_config_models()
    for model_id, model_data in user_models.items():
        if model_id in ("stub", *PRESETS):
            continue
        if _is_embedding_model(model_id, model_data):
            continue
        available = _user_model_key_available(model_data)
        badge = " ✓" if available else ""
        # Caller appends the localized "[custom]" tag via
        # `from_user_config` — kept out of display so the label is
        # locale-agnostic at this layer.
        result.append({
            "id": model_id,
            "display": f"{model_id}{badge}",
            "available": available,
            "from_user_config": True,
        })

    return result


def first_custom_entry_example() -> str:
    """Pick a concrete example `entry_id` for the Add-custom prompt.

    Prefers a real entry the user already has in `~/.neonrp/config.json`
    (so the prompt's example matches their own naming habit). Falls
    back to a common nickname when the user has no custom entries yet.
    """
    try:
        user_models = _load_user_config_models()
        for model_id, data in user_models.items():
            if model_id in PRESETS or model_id == "stub":
                continue
            if _is_embedding_model(model_id, data):
                continue
            return model_id
    except Exception:
        pass
    return "qwen"


def preset_ready(preset_id: str) -> bool:
    """The preset can run right now without asking the player for anything: a user-config model, a built-in with its
    key present, or Worldlines while signed in (10-24: the launcher asks the chooser instead of the key prompt when the
    remembered model is not ready — a remembered Worldlines after the session ended used to drop the player into
    「Paste API key」)."""
    return preset_id not in PRESETS or _preset_key_available(preset_id)


def ensure_preset_key(preset_id: str) -> bool:
    """Ensure the API key for *preset_id* is available, prompting if needed.

    For built-in presets without a configured key, interactively asks the user
    to paste their key and saves it to ~/.neonrp/config.json for future use.

    Returns:
        True  – key is available (was already set, or user just entered it)
        False – user skipped / left blank (caller should abort or go back)
    """
    import click

    # User-config models are assumed to have their own key already
    if preset_id not in PRESETS:
        return True

    if _preset_key_available(preset_id):
        return True

    from neonrp.tui.i18n import get_message, resolve_locale

    locale = resolve_locale()

    info = PRESETS[preset_id]
    api_key_env = info.get("api_key_env", "")
    key_hint = info.get("key_hint", "")

    click.echo()
    if preset_id == "worldlines":
        # the relay is for signed-in players: say so (and /login) — the PAT paste below stays as the quiet alternative
        click.echo("  " + get_message(locale, "preset.worldlines_signin"))
    else:
        click.echo("  " + get_message(locale, "preset.api_key_needed").format(display=info["display"]))
        if key_hint:
            click.echo("  " + get_message(locale, "preset.api_key_get_at").format(url=key_hint))
    click.echo()

    raw = click.prompt("  " + get_message(locale, "prompt.api_key"), default="", show_default=False).strip()
    if not raw:
        return False

    model_override: str | None = None
    if preset_id == "openrouter":
        model_override = _prompt_openrouter_model(raw)

    # Persist to user config
    _save_key_to_user_config(preset_id, raw, model_override=model_override)

    # Also set in current process env so it's immediately usable
    if api_key_env:
        os.environ[api_key_env] = raw

    click.echo("  " + get_message(locale, "preset.api_key_saved"))
    return True


def _prompt_openrouter_model(api_key: str) -> str | None:
    """Offer the user a curated list + optional full catalog for OpenRouter."""
    import click

    click.echo()
    click.echo("  OpenRouter 模型选择：")
    options: list[dict[str, str]] = list(OPENROUTER_SUGGESTED_MODELS)

    for idx, item in enumerate(options, 1):
        click.echo(f"    {idx}. {item['label']}  [{item['id']}]")
    fetch_idx = len(options) + 1
    custom_idx = len(options) + 2
    click.echo(f"    {fetch_idx}. 拉取完整模型列表")
    click.echo(f"    {custom_idx}. 手动输入 model id")

    raw = click.prompt("  选择（留空=默认第1项）", default="1", show_default=False).strip()
    if not raw:
        return None
    try:
        choice = int(raw)
    except ValueError:
        return None

    if 1 <= choice <= len(options):
        return options[choice - 1]["id"]
    if choice == fetch_idx:
        catalog = fetch_openrouter_models(api_key)
        if not catalog:
            click.echo("  未能拉取模型列表，使用默认。")
            return None
        return _prompt_from_catalog(catalog)
    if choice == custom_idx:
        typed = click.prompt("  model id", default="", show_default=False).strip()
        return typed or None
    return None


def _prompt_from_catalog(catalog: list[dict[str, str]]) -> str | None:
    """Show a paginated catalog and let user pick by number or substring."""
    import click

    total = len(catalog)
    click.echo(f"  共 {total} 个模型，输入关键字过滤（回车显示前 30 个）：")
    keyword = click.prompt("  关键字", default="", show_default=False).strip().lower()
    filtered = [m for m in catalog if keyword in m["id"].lower() or keyword in m["label"].lower()] if keyword else catalog

    shown = filtered[:30]
    if not shown:
        click.echo("  没有匹配项。")
        return None
    for idx, item in enumerate(shown, 1):
        click.echo(f"    {idx}. {item['label']}  [{item['id']}]")
    raw = click.prompt("  选择编号（留空取消）", default="", show_default=False).strip()
    if not raw:
        return None
    try:
        choice = int(raw)
    except ValueError:
        return None
    if 1 <= choice <= len(shown):
        return shown[choice - 1]["id"]
    return None


def default_model_ref() -> str | None:
    """The model a NEW run should start on when nobody chose one.

    Not ``list_presets()[0]``: that slot used to be a virtual preset whose
    config is the stub provider — so a run opened from the TUI came up
    answering "Stub provider active" although the user had four working keys.

    Order: the user's own `llm.model_ref` → Worldlines when signed in (10-23:
    signed in, a new game still opened on a key saved in ~/.neonrp, the first
    in preset order) → the first built-in preset whose key is actually
    present → any model saved in user config → None (caller leaves the run on
    the stub and the TUI points at /settings).
    """
    user_models = _load_user_config_models()
    try:
        data = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8")) if _USER_CONFIG_PATH.exists() else {}
        chosen = str((data.get("llm") or {}).get("model_ref") or "").strip()
    except Exception:
        chosen = ""
    if chosen and chosen != "stub" and (chosen in user_models or chosen in PRESETS):
        return chosen
    if "worldlines" in PRESETS and _worldlines_signed_in():
        return "worldlines"
    for preset_id in PRESETS:
        if _preset_key_available(preset_id):
            return preset_id
    for name, entry in user_models.items():
        if entry.get("provider", "stub") != "stub" and (entry.get("api_key") or entry.get("api_key_env")):
            return name
    return None


def build_config_dict(preset_id: str) -> dict[str, Any]:
    """Build a complete NeonRP config.json dict for the given preset or user model.

    The output is directly compatible with NeonRP's config system:
    - ``llm.model_ref`` selects the active model
    - ``models`` section registers the named model
    """
    # Built-in preset — user config wins per field, PRESETS is the
    # fallback. Without this, an edit in Settings (e.g. setting deepseek
    # to deepseek-v4-pro instead of the default deepseek-chat) would
    # silently revert to the PRESETS hardcoded model on every launch.
    if preset_id in PRESETS:
        preset = PRESETS[preset_id]
        user_entry = _load_user_config_models().get(preset_id, {}) or {}

        def _pick(key: str, default: Any = None) -> Any:
            value = user_entry.get(key)
            if value not in (None, ""):
                return value
            return preset.get(key, default)

        model_entry: dict[str, Any] = {
            "provider": _pick("provider", "openai"),
            "model": _pick("model", ""),
            "temperature": _pick("temperature", 0.7),
            "max_output_tokens": _pick("max_output_tokens", 4096),
        }
        base_url = _pick("base_url")
        if base_url:
            model_entry["base_url"] = base_url

        saved_key = user_entry.get("api_key", "")
        if saved_key:
            model_entry["api_key"] = saved_key
        elif preset.get("api_key_env"):
            model_entry["api_key_env"] = preset["api_key_env"]

        return {
            "llm": {"model_ref": preset_id},
            "tui": {"narrator_agent_id": "narrator"},
            "rules": {},
            "models": {preset_id: model_entry},
            "mcp_servers": {},
        }

    # User-config model
    user_models = _load_user_config_models()
    if preset_id in user_models:
        return {
            "llm": {"model_ref": preset_id},
            "tui": {"narrator_agent_id": "narrator"},
            "rules": {},
            "models": {preset_id: dict(user_models[preset_id])},
            "mcp_servers": {},
        }

    raise KeyError(f"Unknown preset or model: {preset_id!r}")
