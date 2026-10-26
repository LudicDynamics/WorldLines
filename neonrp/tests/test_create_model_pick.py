"""Which model creation runs on (10-26): the auto-pick takes any provider with a key — anthropic too, not only the
OpenAI-compatible ones — never Worldlines on its own; the explicit pick wins while it is usable."""
from __future__ import annotations

import json

import pytest

import neonrp.presets as P


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(P, "_USER_CONFIG_PATH", path)
    keys: set[str] = set()
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: pid in keys)

    def write(data: dict, *have: str) -> None:
        keys.clear()
        keys.update(have)
        path.write_text(json.dumps(data), encoding="utf-8")

    return write


def test_auto_pick_takes_anthropic(cfg):
    cfg({"models": {"anthropic": {"api_key": "sk-ant-test"}}}, "anthropic")
    assert P.resolve_creation_provider() is None   # the old OpenAI-only scan found nothing
    assert P.resolve_creation_preset_id() == "anthropic"
    from neonrp.core.hub_publish import adapter_for_preset

    a = adapter_for_preset(None)
    assert type(a).__name__.lower().startswith("anthropic")


def test_preference_order_and_no_worldlines(cfg):
    cfg({}, "worldlines", "anthropic", "openrouter")
    assert P.resolve_creation_preset_id() == "openrouter"   # deepseek > openrouter > openai > glm, then the rest
    cfg({}, "worldlines")
    assert P.resolve_creation_preset_id() is None          # Worldlines only when picked explicitly
    cfg({"create_provider": "worldlines"}, "worldlines")
    assert P.resolve_creation_preset_id() == "worldlines"


def test_explicit_wins_while_usable_and_user_models_count(cfg):
    cfg({"create_provider": "qwen", "models": {"qwen": {"provider": "openai", "model": "q", "api_key": "k"}}}, "deepseek")
    assert P.resolve_creation_preset_id() == "qwen"
    cfg({"create_provider": "qwen", "models": {"qwen": {"provider": "openai", "model": "q"}}}, "deepseek")
    assert P.resolve_creation_preset_id() == "deepseek"    # the picked one lost its key → the next usable


def test_create_agent_setting(cfg):
    cfg({})
    assert P.get_create_agent() is None
    P.set_create_agent("codex")
    assert P.get_create_agent() == "codex"
    P.set_create_agent("engine")
    assert P.get_create_agent() is None
