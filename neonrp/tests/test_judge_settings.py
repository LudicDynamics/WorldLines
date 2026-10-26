"""判断器(Jev)设置页(10-25):TUI /settings 和本地网页共用 core.judge_settings;
judge.mode / models.typesafe.api_key / models.judge.preset 落 ~/.neonrp/config.json,引擎 backend_name 认 judge.mode。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neonrp.core import judge_settings, system_one as s1


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("neonrp.core.user_config.USER_CONFIG_PATH", tmp_path / ".neonrp" / "config.json")
    for k in ("NEONRP_S1_BACKEND", "TYPESAFE_API_KEY", "HUB_API_TOKEN", "NEONRP_S1_LLM_PRESET", "WORLDLINES_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", None)
    with patch("neonrp.core.worldlines_auth.access_token", return_value=None), patch("neonrp.core.judge_settings.preset_choices", return_value=["deepseek"]):
        yield tmp_path


def _cfg(home: Path) -> dict:
    return json.loads((home / ".neonrp" / "config.json").read_text(encoding="utf-8"))


def test_defaults_are_auto_and_off(home):
    st = judge_settings.read()
    assert st["mode"] == "auto" and st["mode_source"] == "default"
    assert st["effective"] == "off" and not st["key_set"] and st["llm_preset"] == ""


def test_config_mode_pins_the_backend(home):
    judge_settings.save(mode="off")
    assert _cfg(home)["judge"]["mode"] == "off" and s1.backend_name() == "off"
    judge_settings.save(mode="llm")
    assert s1.backend_name() == "llm" and judge_settings.read()["mode_source"] == "config"
    judge_settings.save(mode="auto")
    assert "judge" not in _cfg(home) and s1.backend_name() == "off"


def test_env_backend_beats_config(home, monkeypatch):
    judge_settings.save(mode="off")
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    assert s1.backend_name() == "stub"
    assert judge_settings.read()["mode_source"] == "env"


def test_own_key_round_trip(home):
    st = judge_settings.save(api_key="ts-1234567890abcd")
    assert st["key_set"] and st["key_masked"] == "ts-1…abcd" and st["key_source"] == "config"
    assert "ts-1234567890abcd" not in json.dumps(st), "the page never gets the key back"
    assert s1.api_key() == "ts-1234567890abcd" and s1.backend_name() == "jev" and st["effective"] == "jev"
    st = judge_settings.save(clear_key=True)
    assert not st["key_set"] and "typesafe" not in _cfg(home)["models"] and s1.backend_name() == "off"


def test_judge_preset_round_trip(home):
    st = judge_settings.save(llm_preset="deepseek")
    assert st["llm_preset"] == "deepseek" and s1.llm_judge_preset() == "deepseek" and s1.backend_name() == "llm"
    st = judge_settings.save(llm_preset="")
    assert st["llm_preset"] == "" and "judge" not in _cfg(home)["models"]


def test_bad_mode_rejected(home):
    with pytest.raises(ValueError):
        judge_settings.save(mode="jevv")


def test_probe_off_and_stub(home, monkeypatch):
    assert judge_settings.probe()["error"] == "off"
    monkeypatch.setenv("NEONRP_S1_BACKEND", "stub")
    s1.install_stub(lambda state, qs: {k: s1.Answer("noul", 0.9) for k in qs})
    try:
        r = judge_settings.probe()
    finally:
        s1.install_stub(None)
    assert r["ok"] and r["backend"] == "stub" and r["yes"] == 0.9


# ── TUI page ────────────────────────────────────────────────────────────


def _flow():
    from neonrp.tui.settings_flow import SettingsFlow

    host = MagicMock()
    host.locale = host.ui_locale = "zh"
    return SettingsFlow(host=host), host


def test_root_has_a_judge_row(home):
    flow, host = _flow()
    with patch("neonrp.tui.settings_flow.list_configured_entries", return_value=[]):
        flow.open_root()
    screen, cb = host.push_screen.call_args.args[:2]
    assert "judge" in [v for _, v in screen._options]
    cb("judge")
    labels = [lab for lab, _ in host.push_screen.call_args.args[0]._options]
    values = [v for _, v in host.push_screen.call_args.args[0]._options]
    assert {"mode", "key", "preset", "test", "back"} <= set(values)
    assert any("判断器" in lab for lab in labels) and not any("settings.judge" in lab for lab in labels)


def test_mode_picker_saves(home):
    flow, host = _flow()
    flow._pick_judge_mode()
    screen, cb = host.push_screen.call_args.args[:2]
    assert "m::off" in [v for _, v in screen._options]
    cb("m::off")
    assert _cfg(home)["judge"]["mode"] == "off"


def test_blank_key_cancels_and_clear_row_only_when_saved(home):
    flow, host = _flow()
    flow._apply_judge(api_key="   ")
    assert not (home / ".neonrp" / "config.json").exists()
    flow._open_judge_settings()
    assert "key_clear" not in [v for _, v in host.push_screen.call_args.args[0]._options]
    flow._apply_judge(api_key="ts-key-0001")
    assert "key_clear" in [v for _, v in host.push_screen.call_args.args[0]._options]
    assert any("…0001" in lab for lab, _ in host.push_screen.call_args.args[0]._options)


def test_judge_keys_are_not_model_entries(home):
    """models.typesafe / models.judge 不是聊天模型:设置页的模型列表、list_presets 都不该把它们当自定义条目。"""
    from neonrp.presets import _load_user_config_models, list_presets
    from neonrp.tui.settings_flow import list_configured_entries

    with patch("neonrp.core.judge_settings.preset_choices", return_value=[]):
        judge_settings.save(api_key="ts-key-0001", llm_preset="deepseek")
    with patch("neonrp.presets._USER_CONFIG_PATH", home / ".neonrp" / "config.json"):
        assert not ({"typesafe", "judge"} & set(_load_user_config_models()))
        assert not ({"typesafe", "judge"} & {p["id"] for p in list_presets()})
        assert not ({"typesafe", "judge"} & {e["id"] for e in list_configured_entries()})


# ── follow-up (10-25):pin 了但用不了 · 配置路径走 user_config ─────────────────


def _no_call(*a, **k):
    raise AssertionError("a pinned judge with no key / session must not be called")


def test_pinned_jev_without_key_is_not_called(home, monkeypatch):
    """固定 Jev 却没 key:不发注定失败的请求,按「不可用」走回退(无 LLM 判 → off;有 → llm);页面如实说。"""
    monkeypatch.setattr(s1, "_post_jev", _no_call)
    judge_settings.save(mode="jev")
    assert s1.pinned_unusable() == "no_key" and s1.backend_name() == "off" and not s1.fast_judge_available()
    st = judge_settings.read()
    assert st["mode"] == "jev" and st["pinned_unusable"] == "no_key" and st["effective"] == "off"
    s1._CACHE.clear()
    assert s1.ask({"t": "pin-1"}, {"q": s1.noul("ok?")}) is None

    class _Judge:
        def chat(self, msgs):
            return MagicMock(message=MagicMock(content=json.dumps({"q": {"noul": 0.8}})))

    monkeypatch.setattr(s1, "LLM_ADAPTER_FACTORY", lambda: _Judge())
    assert s1.backend_name() == "llm" and judge_settings.read()["effective"] == "llm"
    a = s1.ask({"t": "pin-2"}, {"q": s1.noul("ok?")})
    assert a is not None and a["q"].value == 0.8

    judge_settings.save(api_key="ts-key-0001")
    assert s1.pinned_unusable() is None and s1.backend_name() == "jev" and judge_settings.read()["pinned_unusable"] is None


def test_pinned_proxy_signed_out(home, monkeypatch):
    judge_settings.save(mode="proxy")
    assert s1.pinned_unusable() == "signed_out" and s1.backend_name() == "off"
    assert judge_settings.read()["pinned_unusable"] == "signed_out"
    monkeypatch.setenv("HUB_API_TOKEN", "sess-test")
    assert s1.pinned_unusable() is None and s1.backend_name() == "proxy"


def test_env_pin_without_key_also_falls_back(home, monkeypatch):
    monkeypatch.setenv("NEONRP_S1_BACKEND", "jev")
    assert s1.backend_name() == "off" and judge_settings.read()["pinned_unusable"] == "no_key"
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-env-key")
    assert s1.backend_name() == "jev"


def test_tui_now_row_names_the_unusable_pin(home):
    flow, host = _flow()
    judge_settings.save(mode="jev")
    flow._open_judge_settings()
    labels = [lab for lab, _ in host.push_screen.call_args.args[0]._options]
    assert any("没有可用的 key" in lab and "实际" in lab for lab in labels)


def test_web_judge_box_has_the_pin_note_in_four_languages():
    ui = Path(__file__).resolve().parents[1] / "worldlines" / "ui" / "app"
    js = (ui / "src" / "settings.js").read_text(encoding="utf-8")
    assert "j.pinned_unusable" in js
    for zh in ("固定用 Jev key,但没有可用的 key", "固定用账号的 Jev,但没登录 Worldlines", "实际:"):
        assert zh in js
        for lang in ("en", "ja", "ko"):
            assert f'"{zh}":' in (ui / "real" / f"i18n-{lang}.js").read_text(encoding="utf-8"), (zh, lang)


def test_judge_config_goes_through_user_config(tmp_path, monkeypatch):
    """system_one 读 config 走 core.user_config(和设置页同一路径),不是写死 ~/.neonrp:HOME 指别处也读得到。"""
    monkeypatch.setenv("HOME", str(tmp_path / "elsewhere"))
    cfg = tmp_path / "cfg" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"judge": {"mode": "llm"}, "models": {"judge": {"preset": "qwen"}, "typesafe": {"api_key": "ts-x"}}, "hub": {"api_token": "h-1"}}), encoding="utf-8")
    monkeypatch.setattr("neonrp.core.user_config.USER_CONFIG_PATH", cfg)
    for k in ("NEONRP_S1_BACKEND", "TYPESAFE_API_KEY", "HUB_API_TOKEN", "NEONRP_S1_LLM_PRESET"):
        monkeypatch.delenv(k, raising=False)
    with patch("neonrp.core.worldlines_auth.access_token", return_value=None):
        assert s1.config_mode() == "llm" and s1.llm_judge_preset() == "qwen" and s1.api_key() == "ts-x" and s1.proxy_token() == "h-1"
    monkeypatch.setattr("neonrp.core.user_config.USER_CONFIG_PATH", tmp_path / "missing" / "config.json")
    assert s1.config_mode() is None and s1.api_key() is None
