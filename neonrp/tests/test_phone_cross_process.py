"""Two processes, one run (10-21 · TEMPLATE-LAYERS-1019 stage B): a real engine (``neonrp web`` on its own port, a slow
fake model) is in the middle of the player's turn on a run; another process — here, the test — has a followed character
act in that same run. Her world execution must not write while the engine's turn holds the run (core/run_lock's file
lock): it waits as pending, and is settled once the turn is over. Needs the private layer (the phone orchestration)
and ports 8803 / 8804 free; otherwise skipped."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from _paths import ENGINE_ROOT, PRODUCT_TEMPLATES
from neonrp.core import node_kinds, player_data, run_lock, soul_chat, soul_tick
from neonrp.core.llm import LLMTurnResult, Message
from neonrp.core.paths import get_data_dir_name

P = node_kinds.module_of("phone")
ENGINE, AI = 8803, 8804


class Fake:
    def __init__(self, *raws: str):
        self.raws = list(raws)

    def chat(self, messages, tools=None):
        raw = self.raws.pop(0) if len(self.raws) > 1 else self.raws[0]
        return LLMTurnResult(message=Message(role="assistant", content=raw), finished=True, usage={})


def _busy_port(p: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def _get(url: str, data: dict | None = None, timeout: float = 5) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    if P is None:
        pytest.skip("no private layer")
    if _busy_port(ENGINE) or _busy_port(AI):
        pytest.skip(f"ports {ENGINE} / {AI} are in use (someone else's server): not running against it")
    home = tmp_path / "home"
    (home / ".neonrp").mkdir(parents=True)
    store = home / "templates"
    shutil.copytree(PRODUCT_TEMPLATES / "wuwu.template", store / "wuwu.template")
    monkeypatch.setenv("NEONRP_TEMPLATE_PATH", str(store))
    plays = home / ".worldlines" / "plays"
    from neonrp import worlds

    monkeypatch.setattr(worlds, "PLAYS_HOME", plays)
    from neonrp.core import graph_test as G

    root = G._world({"template": str(store / "wuwu.template"), "root": str(plays / "wuwu-1")}, tmp_path)  # a playable run
    mock_cfg = {"llm": {"model_ref": "mock"}, "models": {"mock": {"provider": "openai", "model": "mock-1",
                                                                   "base_url": f"http://127.0.0.1:{AI}/v1", "api_key": "mock"}}}
    for cj in (home / ".neonrp" / "config.json", root / ".neonrp" / "config.json"):  # the engine talks to the slow fake model
        cj.write_text(json.dumps(mock_cfg), encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    mock = subprocess.Popen([sys.executable, str(ENGINE_ROOT / "worldlines/ui/player/e2e/mock_ai.py"), "--port", str(AI)],
                            stdout=open(logs / "mock.log", "w"), stderr=subprocess.STDOUT)
    env = {**os.environ, "HOME": str(home), "NEONRP_TEMPLATE_PATH": str(store), "NEONRP_STRICT_PORT": "1", "NEONRP_DISABLE_CLAUDE_CODE": "1"}
    env.pop("PYTEST_CURRENT_TEST", None)
    srv = subprocess.Popen([sys.executable, "-m", "neonrp", "web", "--project", str(root), "--port", str(ENGINE), "--no-browser"],
                           cwd=str(ENGINE_ROOT), env=env, stdout=open(logs / "engine.log", "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(240):
            if srv.poll() is not None:
                pytest.skip(f"the engine did not start: {(logs / 'engine.log').read_text()[-600:]}")
            if _busy_port(ENGINE) and _busy_port(AI):
                break
            time.sleep(0.5)
        else:
            pytest.skip("the engine did not come up")
        yield root
    finally:
        for p in (srv, mock):
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def test_a_turn_in_another_engine_keeps_her_action_waiting_then_it_lands(engine, monkeypatch):
    root = engine
    _get(f"http://127.0.0.1:{AI}/_mock/plan", {"slow": 8})
    deadline = time.time() + 120
    started = False
    while time.time() < deadline and not started:  # the engine may still be on its opening: ask until it takes the line
        code, body = _get(f"http://127.0.0.1:{ENGINE}/cmd", {"text": "我四处看看"})
        started = code == 202
        if not started:
            time.sleep(1)
    assert started, "the other engine took the player's turn"
    for _ in range(40):  # its turn holds the run's lock (a file lock: another process)
        with run_lock.try_hold(root) as free:
            if not free:
                break
        time.sleep(0.25)
    else:
        pytest.fail("the other engine's turn never held the run")

    player_data._add("characters", {"sid": "vera", "name": "薇拉", "world": "wuwu", "how": "test", "memory": "fresh"}, ("sid", "world"))
    c = soul_chat.resolve("wuwu", "vera")
    soul_chat.subscription("wuwu", "vera", {"on": True})
    rs = (root / get_data_dir_name(root) / "meta" / "world_results.jsonl")
    out = soul_tick.run(c, adapter=Fake('{"did": "想去码头", "mood": "", "message": ""}', '<act where="T001/berth7">去码头搬货</act>'),
                        lang="zh", force=True)
    assert out["acted"]["why"] == "deferred", out
    assert soul_chat.subscription("wuwu", "vera")["pending"] is True and not rs.exists(), "nothing written while the other engine's turn runs"

    _get(f"http://127.0.0.1:{AI}/_mock/plan", {"slow": 0})
    for _ in range(240):  # its turn is over: the run is free again
        with run_lock.try_hold(root) as free:
            if free:
                break
        time.sleep(0.5)
    from neonrp.core import mechanics, turn_v3
    from neonrp.core import graph_test as G

    world = G._ScriptAdapter(["<lines>\n薇拉去码头搬完了货。\n</lines>", "<vars>\n</vars>\n<files>\n</files>"])
    monkeypatch.setattr(turn_v3, "ADAPTER_FACTORY", lambda root, provider: world)
    real = mechanics.get
    monkeypatch.setattr(mechanics, "get", lambda r, seam: (lambda root, iid, **kw: {"ok": True, "name": iid, "text": "我在原地", "proposed_move": None})
                        if seam == "soul_turn" else real(r, seam))
    landed = P.settle_pending(c)
    assert landed and landed["ok"], landed
    assert rs.exists() and soul_chat.subscription("wuwu", "vera")["pending"] is False
