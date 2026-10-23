"""ai.worldlines.gg as an OpenAI-compatible endpoint (PAT or connect session), System One on the new
address with the quota fallback, and x-request-id recorded per call."""
from __future__ import annotations

import io
import json
import time
import urllib.error
from types import SimpleNamespace

import pytest

from neonrp.core import request_ids, system_one, worldlines_auth


def test_credentials_order_pat_then_session_then_none(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLDLINES_IDENTITY_FILE", str(tmp_path / "identity.json"))
    monkeypatch.delenv("WORLDLINES_API_KEY", raising=False)
    monkeypatch.setattr(worldlines_auth, "_manager", lambda: None)
    assert worldlines_auth.access_token() is None
    (tmp_path / "identity.json").write_text(json.dumps({"access_token": "sess", "expires_at": time.time() + 600}), encoding="utf-8")
    assert worldlines_auth.access_token() == "sess"
    (tmp_path / "identity.json").write_text(json.dumps({"access_token": "old", "expires_at": time.time() - 5}), encoding="utf-8")
    assert worldlines_auth.access_token() is None, "an expired stored session without the client library is not signed in"
    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_x")
    assert worldlines_auth.access_token() == "wl_pat_x"
    assert worldlines_auth.is_worldlines("https://ai.worldlines.gg/v1") and not worldlines_auth.is_worldlines("https://api.deepseek.com/v1")


def test_openai_adapter_uses_the_worldlines_token_and_records_request_id(monkeypatch):
    from neonrp.core.llm_openai import OpenAIAdapter

    monkeypatch.setenv("WORLDLINES_API_KEY", "wl_pat_y")
    seen = {}

    class Raw:
        headers = {"x-request-id": "req_123"}

        def parse(self):
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="好", tool_calls=None))], usage=None)

    class FakeOpenAI:
        def __init__(self, **kw):
            seen.update(kw)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: Raw().parse(), with_raw_response=SimpleNamespace(create=lambda **k: Raw())))

    import openai
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    request_ids.reset()
    a = OpenAIAdapter(model="deepseek-v4.1-flash", base_url="https://ai.worldlines.gg/v1", api_key_env="WORLDLINES_NOPE")
    from neonrp.core.llm import Message
    out = a.chat([Message(role="user", content="hi")])
    assert seen["api_key"] == "wl_pat_y" and seen["default_headers"]["X-Worldlines-Product"] == "hub"
    assert out.message.content == "好" and request_ids.take() == [{"id": "req_123", "kind": "llm", "model": "deepseek-v4.1-flash"}]


def test_system_one_quota_429_falls_back_without_jev_and_cools_down(monkeypatch):
    assert system_one.PROXY_URL_DEFAULT == "https://ai.worldlines.gg/v1/systemone"
    monkeypatch.setenv("NEONRP_S1_BACKEND", "proxy")
    monkeypatch.setenv("HUB_API_TOKEN", "t")
    monkeypatch.setattr(system_one, "backend_name", lambda: "proxy")
    system_one._QUOTA["until"] = 0.0
    system_one._CACHE.clear()
    calls = {"n": 0}

    def boom(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {"x-request-id": "req_q"}, io.BytesIO(b'{"error":"quota_exceeded","kind":"systemone"}'))

    monkeypatch.setattr(system_one.urllib.request, "urlopen", boom)
    request_ids.reset()
    q = {"x": system_one.noul("is it?")}
    assert system_one.ask({"s": 1}, q) is None
    assert system_one.last_call()["fallback"] == "quota" and system_one.quota_blocked()
    assert system_one.ask({"s": 2}, q) is None and calls["n"] == 1, "cooldown: no second network call"
    assert request_ids.take()[0]["id"] == "req_q"
    system_one._QUOTA["until"] = 0.0


def test_connect_falls_back_to_the_bundled_client(monkeypatch):
    """10-02: the login client ships with NeonRP — no separate install; an installed worldlines-identity still wins."""
    import builtins

    real = builtins.__import__

    def no_identity(name, *a, **k):
        if name == "worldlines_identity" or name.startswith("worldlines_identity."):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_identity)
    assert worldlines_auth._wl_login().__name__ == "neonrp._vendor.worldlines_identity.login"


def test_interaction_points_for_the_contract(tmp_path):
    """The pack's stop / switch / exit / panel tags, derived from the registry and Pack.modes."""
    import shutil
    from pathlib import Path

    from neonrp.core.interaction import interaction_points
    from neonrp.core.registry import load_registry

    root = tmp_path / "w"
    shutil.copytree(Path(__file__).resolve().parents[1] / "src" / "neonrp" / "templates" / "stoneford-elena", root)  # absolute: other tests chdir
    (root / ".neonrp").mkdir(exist_ok=True)
    shutil.copy(root / "playthrough.json", root / ".neonrp" / "playthrough.json")
    ip = interaction_points(root, load_registry(root))
    req = {r["tag"]: r for r in ip["requests"]}
    assert {"roll", "dice", "referee", "map", "ask"} <= set(req)
    assert req["dice"]["form"] == "[dice <dice> <vs>]…[/dice]" and "layer:combat" in req["dice"]["writers"] and req["dice"]["kind"] == "tool"
    assert req["ask"]["kind"] == "request"
    # D-20261018: combat is a one-shot node the narrator calls, not a layer switch with an exit
    assert req["combat"]["form"] == "[combat <roster>]<note>[/combat]" and req["combat"]["layer"] == "combat" and req["combat"]["kind"] == "tool"
    assert ip["switches"] == [] and ip["exits"] == []
    assert {(p["id"], p["source"]) for p in ip["panels"]} == {("formation", "layer"), ("map", "tool")}
    assert {e["id"] for e in ip["engine"]} >= {"gate", "post_solve", "layer:dungeon"}
