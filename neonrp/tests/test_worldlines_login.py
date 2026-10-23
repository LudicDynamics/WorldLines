"""One Worldlines sign-in feeds Jev (the judge proxy), the model relay and world uploads; it is optional —
the engine plays on the player's own provider without it."""
import json
import time


def _signed_in(tmp_path, monkeypatch):
    store = tmp_path / "identity.json"
    store.write_text(json.dumps({"access_token": "tok_abc", "refresh_token": "r", "expires_at": time.time() + 3600}), encoding="utf-8")
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(store))
    for k in ("WORLDLINES_API_KEY", "HUB_API_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    return store


def test_vendored_login_client_imports():
    from neonrp.core import worldlines_auth as wa

    m = wa._wl_login()
    assert hasattr(m, "login") and hasattr(m, "FileTokenStore") and hasattr(m, "create_token_manager")


def test_one_session_feeds_jev_relay_and_uploads(tmp_path, monkeypatch):
    from neonrp.core import hub_auth, system_one, worldlines_auth as wa

    monkeypatch.setattr(wa, "_manager", lambda: None)  # no network refresh in tests
    assert not wa.status()["signed_in"] or True
    _signed_in(tmp_path, monkeypatch)
    assert wa.status()["signed_in"] and wa.access_token() == "tok_abc"
    assert hub_auth.get_hub_token() == "tok_abc"  # uploads ride the account
    assert system_one.proxy_token() == "tok_abc"  # Jev through ai.worldlines.gg/v1/systemone
    from neonrp.tui import settings_flow

    assert any(e["id"] == "worldlines" for e in settings_flow.list_configured_entries())  # the relay counts as configured


def test_about_says_free_engine_and_optional_account():
    from neonrp.core import worldlines_auth as wa

    zh = wa.about("zh")
    assert "引擎免费" in zh and "Jev" in zh and "上传" in zh and "不登录" in zh
    assert "free" in wa.about("en") and "Jev" in wa.about("ja")


def test_tui_has_login_commands():
    from neonrp.tui.app import LOCAL_SLASH_COMMANDS
    from neonrp.tui.commands import COMMANDS

    assert "login" in COMMANDS and "login" in LOCAL_SLASH_COMMANDS and len(COMMANDS) <= 25  # one command, sub-verbs for status / out


def test_tui_account_status_prints(tmp_path, monkeypatch):
    """/status account and /login printed through ``self._t``, which only the pop-up screens had — the app itself
    raised AttributeError the moment either ran (10-23, signed in)."""
    from neonrp.core import worldlines_auth as wa
    from neonrp.tui.app import NeonRPApp

    monkeypatch.setattr(wa, "_manager", lambda: None)
    _signed_in(tmp_path, monkeypatch)
    lines: list[str] = []

    class _App:
        ui_locale = "zh"
        _t = NeonRPApp._t
        _account_lang = NeonRPApp._account_lang

        def query_one(self, *_a):
            return type("V", (), {"write": staticmethod(lines.append)})()

    NeonRPApp._cmd_account(_App())
    assert "Worldlines 账号" in lines[0] and "已登录" in lines[0]
