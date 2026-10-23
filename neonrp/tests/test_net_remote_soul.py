"""A character played from elsewhere (NET-MULTIPLAYER-1009 §七, 10-10): while her seat is connected, the questions put
to her mid-beat go to her player and come back in her own words; no answer in time — or no one there — the host stands
in for her and the answer is marked proxy (「代」). The turn never waits on someone who is not there."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from test_e2e_stub_play import _install

from neonrp.commands.serve import make_engine_server
from neonrp.core import light_chat, soul_remote
from neonrp.core.playthrough import read_playthrough
from neonrp.net.client import RemoteClient
from neonrp.net.host import hub_of


@pytest.fixture
def world(tmp_path: Path):
    root = _install(tmp_path)
    iid = read_playthrough(root).souls[0].instance_id
    server = make_engine_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    owner = RemoteClient(url, hub_of(server).token)
    owner.call("room.auto_approve", {"on": True})
    yield root, iid, url, owner
    owner.close()
    server.shutdown()
    server.server_close()


def _seat(url: str, owner: RemoteClient, iid: str, answer) -> RemoteClient:
    c = RemoteClient.join(url, owner.call("room.invite", {"kind": "soul", "target": iid})["token"])
    c.on("soul.ask", answer)
    end = time.time() + 5
    while soul_remote.route(iid) is None and time.time() < end:
        time.sleep(0.05)
    assert soul_remote.route(iid) is not None
    return c


def test_she_answers_herself_over_the_network(world):
    root, iid, url, owner = world
    seen: list[dict] = []
    c = _seat(url, owner, iid, lambda p: (seen.append(p), "「我在码头,你过来吧。」")[1])
    try:
        r = light_chat.ask_soul_deliver(root, iid, "你在哪?")
        assert r["ok"] and r.get("remote") and r["answer"] == "「我在码头,你过来吧。」" and not r.get("proxy")
        assert seen and seen[0]["iid"] == iid and seen[0]["question"] == "你在哪?"
        # her memory lives with her player — the host's copy is not written
        inbox = (root / ".neonrp").rglob("*.jsonl")
        assert any('"remote": true' in f.read_text(encoding="utf-8") for f in inbox)
    finally:
        c.close()


def test_too_slow_and_the_host_stands_in(world, monkeypatch):
    root, iid, url, owner = world
    monkeypatch.setattr(soul_remote, "ASK_TIMEOUT", 0.5)
    c = _seat(url, owner, iid, lambda p: (time.sleep(3), "太晚了")[1])
    try:
        t0 = time.time()
        r = light_chat.ask_soul_deliver(root, iid, "你在哪?")
        assert time.time() - t0 < 3, "the turn waited on her"
        assert r["ok"] and r.get("proxy") and r["answer"] != "太晚了"  # the host's stand-in (stub model here)
    finally:
        c.close()


def test_when_she_leaves_the_route_goes(world):
    root, iid, url, owner = world
    c = _seat(url, owner, iid, lambda p: "在")
    c.close()
    end = time.time() + 5  # a client that leaves says so (session.bye): the host drops her route at once
    while soul_remote.route(iid) is not None and time.time() < end:
        time.sleep(0.2)
    assert soul_remote.route(iid) is None
    r = light_chat.ask_soul_deliver(root, iid, "你在哪?")
    assert r["ok"] and not r.get("remote") and not r.get("proxy")  # nobody's seat: she is the host's own character again
