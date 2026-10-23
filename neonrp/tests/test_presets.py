"""Preset registry + connection-ping transport tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from neonrp import presets


def test_opencode_preset_registered() -> None:
    assert "opencode" in presets.PRESETS
    p = presets.PRESETS["opencode"]
    assert p["base_url"] == "https://opencode.ai/zen/v1"
    # Bare model id: the OpenAI-compatible endpoint rejects the `opencode/`
    # prefixed id with ModelError (verified against the live endpoint).
    assert p["model"] == "deepseek-v4.1-flash"  # opencode's id for V4.1 Flash (its /models, 10-17)
    assert "opencode/" not in p["model"]
    assert presets.get_provider_type("opencode") is not None


def test_deepseek_preset_uses_official_id() -> None:
    # api.deepseek.com only serves deepseek-flash / deepseek-v4-pro (10-17 /models); deepseek-v4.1-flash → 400
    assert presets.PRESETS["deepseek"]["model"] == "deepseek-flash"


def test_kimi_k3_preset_registered() -> None:
    assert "kimi-k3" in presets.PRESETS
    p = presets.PRESETS["kimi-k3"]
    assert p["base_url"] == "https://api.moonshot.ai/v1"
    assert p["model"] == "kimi-k3"
    assert p["provider"] == "openai"
    # Kimi K3 只接受 temperature=1(其它值 → 400 invalid_request_error)
    assert p["temperature"] == 1.0
    # kimi-k3 走 openai provider type(不是自己的 type)
    assert presets.get_provider_type(p["provider"]) is not None


def test_opencode_is_first_preset() -> None:
    # Recommended default leads the picker (insertion order = picker order).
    assert list(presets.PRESETS)[0] == "opencode"


def test_ping_openai_compatible_sends_user_agent(monkeypatch) -> None:
    """A real User-Agent is required — urllib's default (Python-urllib/x) is
    403'd by Cloudflare-fronted gateways like OpenCode Zen (WOR-42)."""
    captured: dict[str, str] = {}

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured["ua"] = req.get_header("User-agent") or ""
        raise urllib.error.URLError("short-circuit")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    presets._ping_openai_compatible("k", "m", "https://example/v1", 1.0)

    assert captured["ua"], "ping must send a User-Agent header"
    assert "urllib" not in captured["ua"].lower()
    assert "WorldLines" in captured["ua"]


def test_ping_anthropic_sends_user_agent(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_urlopen(req, timeout=0):  # noqa: ANN001
        captured["ua"] = req.get_header("User-agent") or ""
        raise urllib.error.URLError("short-circuit")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    presets._ping_anthropic("k", "claude-haiku-4-5-20251001", 1.0)

    assert captured["ua"] and "urllib" not in captured["ua"].lower()


# --- save_custom_model: shared write behind the web PUT /settings/custom-model
#     route + the TUI「自定义模型」step. Restores the custom OpenAI-compatible
#     endpoint (Ollama/LM Studio/vLLM/self-hosted) config the web Settings lost.


def test_save_custom_model_writes_openai_entry(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", cfg)

    mid = presets.save_custom_model(
        "My LLaMA", "http://localhost:11434/v1", "qwen2.5:14b", "sk-x"
    )
    # id is normalized: lowercased, spaces → hyphens.
    assert mid == "my-llama"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["models"]["my-llama"] == {
        "provider": "openai",
        "model": "qwen2.5:14b",
        "base_url": "http://localhost:11434/v1",
        "api_key": "sk-x",
    }
    # It now surfaces as a from_user_config preset in the picker
    # (list_presets reads the same _USER_CONFIG_PATH we patched).
    assert any(
        p.get("id") == "my-llama" and p.get("from_user_config")
        for p in presets.list_presets()
    )


def test_save_custom_model_optional_key_omitted(monkeypatch, tmp_path) -> None:
    # Local endpoints (Ollama/LM Studio) need no key — blank key ⇒ no api_key field.
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", cfg)
    presets.save_custom_model("local", "http://localhost:1234/v1", "gpt-oss", "")
    entry = json.loads(cfg.read_text(encoding="utf-8"))["models"]["local"]
    assert "api_key" not in entry
    assert entry["base_url"] == "http://localhost:1234/v1"


def test_save_custom_model_preserves_existing_models(monkeypatch, tmp_path) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps({"models": {"keep": {"provider": "openai", "model": "m"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", cfg)
    presets.save_custom_model("new", "http://h/v1", "n", "")
    models = json.loads(cfg.read_text(encoding="utf-8"))["models"]
    assert set(models) == {"keep", "new"}


@pytest.mark.parametrize(
    "mid,base,model",
    [("", "http://h/v1", "m"), ("x", "", "m")],
)
def test_save_custom_model_rejects_missing_fields(
    monkeypatch, tmp_path, mid, base, model
) -> None:
    # id and base_url are required; a blank one raises ValueError → HTTP 400.
    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", tmp_path / "config.json")
    with pytest.raises(ValueError):
        presets.save_custom_model(mid, base, model, "")


def test_save_custom_model_blank_model_falls_back_to_id(monkeypatch, tmp_path) -> None:
    # A blank model name is allowed — it defaults to the id (as the TUI does).
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(presets, "_USER_CONFIG_PATH", cfg)
    presets.save_custom_model("solo", "http://h/v1", "", "")
    assert json.loads(cfg.read_text(encoding="utf-8"))["models"]["solo"]["model"] == "solo"


def test_deepseek_output_cap_not_v3_era() -> None:
    # V4 Pro 输出上限 384K;内置 cap 曾是 4096(V3 时代过时默认)导致创作
    # 高频截断。守住:≥16384,别再回退。
    assert presets.PRESETS["deepseek"]["max_output_tokens"] >= 16384
