"""Seats and invites (NET-MULTIPLAYER-1009 §九, 10-10): the host invites, approves once, the seat reconnects by itself;
each seat sees only its share of the bus and may call only what its kind may (three-party isolation)."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from test_e2e_stub_play import _install

from neonrp.commands.serve import make_engine_server
from neonrp.net import protocol as P
from neonrp.net.client import RemoteClient, saved_credential
from neonrp.net.host import hub_of


@pytest.fixture
def host(tmp_path: Path):
    root = _install(tmp_path)
    server = make_engine_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    owner = RemoteClient(url, hub_of(server).token)
    yield server, url, owner, root
    owner.close()
    server.shutdown()
    server.server_close()


def _wait(cond, t=10.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_invite_approve_once_then_reconnect_by_itself(host, tmp_path):
    server, url, owner, root = host
    inv = owner.call("room.invite", {"kind": "player", "target": "p2", "label": "小林"})
    assert inv["link"].startswith("worldlines://join?") and f"room={hub_of(server).room.id}" in inv["link"] and inv["code"]
    asked: list[str] = []
    joined: dict = {}

    def _join():
        joined["c"] = RemoteClient.join(url, inv["token"], who="小林", store=tmp_path / "creds.json", on_pending=asked.append)

    th = threading.Thread(target=_join)
    th.start()
    assert _wait(lambda: bool(asked))  # the host hears the request
    assert owner.call("room.pending")[0]["seat"] == "player:p2"
    owner.call("room.approve", {"request": asked[0]})
    th.join(15)
    c = joined["c"]
    try:
        assert c.call("session.whoami") == {"seat": "player:p2", "kind": "player", "target": "p2"}
        with pytest.raises(P.RpcError):  # an invite works once
            RemoteClient.join(url, inv["token"], wait=1)
        cred = saved_credential(tmp_path / "creds.json", url)
        again = RemoteClient(url, cred)  # next time: no link, no approval
        assert again.call("session.whoami")["seat"] == "player:p2"
        again.close()
        seats = {s["seat"]: s for s in owner.call("room.seats")["seats"]}
        assert seats["player:p2"]["label"] == "小林" and seats["player:p2"]["connected"] >= 1
    finally:
        c.close()


def test_short_code_and_auto_approve(host):
    server, url, owner, _root = host
    owner.call("room.auto_approve", {"on": True})
    inv = owner.call("room.invite", {"kind": "soul", "target": "si-elena0001"})
    c = RemoteClient.join(url, inv["code"])
    try:
        assert c.call("session.whoami")["kind"] == "soul"
    finally:
        c.close()


def test_a_character_sees_only_its_own_share(host):
    server, url, owner, _root = host
    owner.call("room.auto_approve", {"on": True})
    soul = RemoteClient.join(url, owner.call("room.invite", {"kind": "soul", "target": "si-elena0001"})["token"])
    player = RemoteClient.join(url, owner.call("room.invite", {"kind": "player", "target": "player"})["token"])
    got: dict[str, list[str]] = {"soul": [], "player": [], "owner": []}
    soul.bus().subscribe("#", lambda m: got["soul"].append(m.topic))
    player.bus().subscribe("#", lambda m: got["player"].append(m.topic))
    owner.bus().subscribe("#", lambda m: got["owner"].append(m.topic))
    try:
        bus = server.runtime.session().bus()
        hub_of(server).bridge(server.runtime.session())
        for t in ("engine/stream", "soul/si-elena0001/request", "soul/si-other/request", "player/player/output", "player/p9/output"):
            bus.publish(t, {"kind": "probe"})
        assert _wait(lambda: len(got["owner"]) >= 5)
        time.sleep(0.3)
        assert got["soul"] == ["soul/si-elena0001/request"]  # never the scene's narration, never another soul
        assert sorted(got["player"]) == ["engine/stream", "player/player/output"]
    finally:
        soul.close()
        player.close()


def test_what_each_seat_may_call_and_revoke(host):
    server, url, owner, _root = host
    owner.call("room.auto_approve", {"on": True})
    soul = RemoteClient.join(url, owner.call("room.invite", {"kind": "soul", "target": "si-elena0001"})["token"])
    try:
        with pytest.raises(P.RpcError) as e:
            soul.call("turn.send", {"text": "我来替玩家说话"})
        assert e.value.code == P.FORBIDDEN  # a character does not take the player's turn
        with pytest.raises(P.RpcError) as e2:
            soul.call("room.invite", {"kind": "player", "target": "x"})
        assert e2.value.code == P.FORBIDDEN
        assert owner.call("room.revoke", {"seat": "soul:si-elena0001"})["revoked"] == 1
        with pytest.raises(P.RpcError) as e3:
            soul.call("session.whoami")
        assert e3.value.code == P.UNAUTHORIZED  # out of the room
    finally:
        soul.close()


def test_room_survives_a_host_restart(host, tmp_path):
    server, url, owner, root = host
    owner.call("room.auto_approve", {"on": True})
    cred = None
    c = RemoteClient.join(url, owner.call("room.invite", {"kind": "player", "target": "p3"})["token"])
    cred = c.token
    c.close()
    server2 = make_engine_server(root, "world-agent", "127.0.0.1", 0)  # a new host process on the same world
    hub_of(server2).room.__init__(root, hub_of(server).token)  # same host token (as if printed again)
    threading.Thread(target=server2.serve_forever, daemon=True).start()
    try:
        c2 = RemoteClient(f"http://127.0.0.1:{server2.server_address[1]}", cred)
        assert c2.call("session.whoami")["seat"] == "player:p3"
        c2.close()
    finally:
        server2.shutdown()
        server2.server_close()
