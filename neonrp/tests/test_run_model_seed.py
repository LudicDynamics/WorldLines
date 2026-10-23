"""Which model a fresh run starts on.

A run opened with `/open` answered "Stub provider active" although four
working keys were saved in ~/.neonrp/config.json. Cause: the scaffold seeded
`list_presets()[0]`, and that slot was a virtual preset whose config *is*
the stub. These pin the
replacement: `default_model_ref()` never hands back stub while a real model
exists, and `seed_run_model()` merges without clobbering the run's config.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import neonrp.presets as P
from neonrp.worlds import scaffold_template_into, seed_run_model


@pytest.fixture
def user_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(P, "_USER_CONFIG_PATH", path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: False)
    monkeypatch.setattr(P, "_worldlines_signed_in", lambda: False)

    def write(data: dict) -> Path:
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    return write


def test_user_choice_wins(user_config):
    user_config({"llm": {"model_ref": "qwen"}, "models": {"qwen": {"provider": "openai", "api_key": "k"}}})
    assert P.default_model_ref() == "qwen"


def test_user_choice_of_stub_is_not_a_choice(user_config):
    user_config({"llm": {"model_ref": "stub"}, "models": {"qwen": {"provider": "openai", "api_key": "k"}}})
    assert P.default_model_ref() == "qwen"


def test_dangling_user_choice_is_skipped(user_config):
    user_config({"llm": {"model_ref": "gone"}, "models": {"qwen": {"provider": "openai", "api_key": "k"}}})
    assert P.default_model_ref() == "qwen"


def test_builtin_preset_with_a_key_beats_saved_models(user_config, monkeypatch):
    user_config({"models": {"qwen": {"provider": "openai", "api_key": "k"}}})
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: pid == "deepseek")
    assert P.default_model_ref() == "deepseek"


def test_a_saved_model_with_a_key_env_counts(user_config):
    user_config({"models": {"kimi": {"provider": "openai", "api_key_env": "KIMI_KEY"}}})
    assert P.default_model_ref() == "kimi"


def test_nothing_configured_is_none(user_config):
    user_config({})
    assert P.default_model_ref() is None


def test_stub_only_saved_models_do_not_count(user_config, monkeypatch):
    user_config({"models": {"s": {"provider": "stub", "api_key": "x"}}})
    assert P.default_model_ref() is None


def test_broken_user_config_does_not_raise(user_config, monkeypatch):
    P._USER_CONFIG_PATH.write_text("{not json", encoding="utf-8")
    assert P.default_model_ref() is None


# ── seed_run_model ────────────────────────────────────────────────────


def _cfg(run: Path) -> dict:
    return json.loads((run / ".neonrp" / "config.json").read_text(encoding="utf-8"))


def test_seed_merges_into_existing_run_config(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / ".neonrp").mkdir(parents=True)
    (run / ".neonrp" / "config.json").write_text(
        json.dumps({"llm": {"model_ref": "stub", "temperature": 0.3}, "models": {"old": {"provider": "stub"}}, "image": {"on": 1}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        P, "build_config_dict",
        lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "openai", "model": "q"}}},
    )
    assert seed_run_model(run, "qwen") == "qwen"
    cfg = _cfg(run)
    assert cfg["llm"] == {"model_ref": "qwen", "temperature": 0.3}, "换模型不丢别的 llm 设置"
    assert set(cfg["models"]) == {"old", "qwen"}
    assert cfg["image"] == {"on": 1}, "无关段落原样保留"


def test_seed_with_nothing_usable_leaves_the_run_alone(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / ".neonrp").mkdir(parents=True)
    monkeypatch.setattr(P, "default_model_ref", lambda: None)
    assert seed_run_model(run) is None
    assert not (run / ".neonrp" / "config.json").exists()


def test_seed_unknown_ref_is_a_noop(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / ".neonrp").mkdir(parents=True)
    monkeypatch.setattr(P, "build_config_dict", lambda ref: (_ for _ in ()).throw(KeyError(ref)))
    assert seed_run_model(run, "ghost") is None


def test_scaffold_never_seeds_stub_when_a_real_model_exists(tmp_path, monkeypatch):
    """The exact shape of the bug, end to end: one real key saved."""
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: False)
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"models": {"qwen": {"provider": "openai", "api_key": "k", "model": "q", "base_url": "http://x"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(P, "_USER_CONFIG_PATH", path)
    run = scaffold_template_into("white-blank", tmp_path / "plays" / "r")
    cfg = _cfg(run)
    assert cfg["llm"]["model_ref"] == "qwen"
    assert cfg["models"]["qwen"]["provider"] != "stub"


def test_scaffold_respects_an_explicit_ref(tmp_path, monkeypatch):
    monkeypatch.setattr(
        P, "build_config_dict",
        lambda ref: {"llm": {"model_ref": ref}, "models": {ref: {"provider": "openai", "model": "m"}}},
    )
    run = scaffold_template_into("white-blank", tmp_path / "plays" / "r", model_ref="kimi")
    assert _cfg(run)["llm"]["model_ref"] == "kimi"


def test_signed_in_a_new_game_starts_on_worldlines(user_config, monkeypatch):
    """10-23 niko: signed in to Worldlines, a new game still opened on a key saved in ~/.neonrp (deepseek first in preset
    order). Signed in and nothing chosen → the relay; a model the player chose in /settings still wins."""
    user_config({"models": {"deepseek": {"provider": "openai", "api_key": "k"}}})
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: pid == "deepseek")
    assert P.default_model_ref() == "deepseek"
    monkeypatch.setattr(P, "_worldlines_signed_in", lambda: True)
    assert P.default_model_ref() == "worldlines"
    user_config({"llm": {"model_ref": "deepseek"}, "models": {"deepseek": {"provider": "openai", "api_key": "k"}}})
    assert P.default_model_ref() == "deepseek"


def test_a_session_counts_as_the_relays_key(tmp_path, monkeypatch):
    import time

    from neonrp.core import worldlines_auth as wa

    monkeypatch.setattr(wa, "_manager", lambda: None)
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    assert not P._preset_key_available("worldlines")
    store = tmp_path / "identity.json"
    store.write_text(json.dumps({"access_token": "tok", "refresh_token": "r", "expires_at": time.time() + 3600}), encoding="utf-8")
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(store))
    assert P._preset_key_available("worldlines")


def test_worldlines_signed_out_is_not_ready_and_the_prompt_says_login(user_config, monkeypatch, capsys):
    """10-24 niko: a remembered Worldlines model after the session ended dropped the player into 「Paste API key」.
    The launcher asks the chooser instead (preset_ready); the explicit choice says /login, not an API-key page."""
    import click

    assert not P.preset_ready("worldlines")
    monkeypatch.setattr(P, "_worldlines_signed_in", lambda: True)
    monkeypatch.setattr(P, "_preset_key_available", lambda pid: pid == "worldlines" and P._worldlines_signed_in())
    assert P.preset_ready("worldlines")
    monkeypatch.setattr(P, "_worldlines_signed_in", lambda: False)
    monkeypatch.setattr(click, "prompt", lambda *a, **k: "")
    assert P.ensure_preset_key("worldlines") is False
    out = capsys.readouterr().out
    assert "/login" in out and "API key" not in out

