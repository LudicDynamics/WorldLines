"""The network layer, step ⓪/① (10-10): headless = the host; a client plays a
world through JSON-RPC + SSE exactly as the in-process session would."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from test_e2e_stub_play import _install

from neonrp.commands.serve import make_engine_server
from neonrp.net import protocol as P
from neonrp.net.client import InProcessClient, RemoteClient, connect
from neonrp.net.host import hub_of


@pytest.fixture
def host(tmp_path: Path):
    root = _install(tmp_path)
    server = make_engine_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    yield server, url, hub_of(server).token
    server.shutdown()
    server.server_close()


def _wait(cond, t=10.0):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.mark.timeout(300)
def test_a_remote_client_plays_turns_and_gets_the_stream(host):
    server, url, token = host
    c = RemoteClient(url, token)
    try:
        assert c.hello["protocol"] == P.PROTOCOL
        seen: list[tuple[str, dict]] = []
        c.bus().subscribe("engine/#", lambda m: seen.append((m.topic, dict(m.payload))))
        r = c.send("我环顾北门")
        assert r.success, r.error
        assert _wait(lambda: any(t == "engine/beat" for t, _ in seen)), seen[:5]  # the beats arrive over the wire
        assert any(t == "engine/stream" and p.get("kind") == "chunk" for t, p in seen)
        assert c.mode == "play" and c.total_turns >= 0
        assert any(m.role == "user" and "北门" in str(m.content) for m in c.get_messages())
    finally:
        c.close()


def test_wrong_token_and_wrong_version_are_refused(host):
    server, url, token = host
    with pytest.raises(P.RpcError) as e:
        RemoteClient(url, "nope")
    assert e.value.code == P.UNAUTHORIZED
    c = RemoteClient(url, token)
    try:
        with pytest.raises(P.RpcError) as e2:
            c.call("session.hello", {"protocol": "worldlines.net/0"})
        assert e2.value.code == P.VERSION_MISMATCH
        with pytest.raises(P.RpcError) as e3:
            c.call("no.such")
        assert e3.value.code == P.METHOD_NOT_FOUND
    finally:
        c.close()


def test_host_asks_the_client_and_a_late_reply_is_dropped(host):
    server, url, token = host
    hub = hub_of(server)
    c = RemoteClient(url, token)
    try:
        c._ask = lambda q, opts: f"答:{q}|{','.join(opts)}"
        assert hub.ask(c.client_id, "ask_user", {"question": "走哪条路", "options": ["东", "西"]}, timeout=10) == "答:走哪条路|东,西"
        assert hub.ask("nobody", "ask_user", {"question": "?"}, timeout=0.2) is None  # no such client: never hangs
        assert hub.reply("h-unknown", "x") is False  # late / unknown answers are dropped
    finally:
        c.close()


def test_a_reconnecting_client_gets_what_it_missed(host):
    """Bus notifications carry the host's seq; a stream opened with ``since`` replays everything after it."""
    server, _url, _token = host
    hub = hub_of(server)
    session = server.runtime.session()
    hub.bridge(session)
    before = session.bus().seq
    session.bus().publish("engine/event", {"kind": "probe", "n": 1})
    session.bus().publish("engine/event", {"kind": "probe", "n": 2})
    q = hub.open_stream("came-back", since=before)
    got = []
    while not q.empty():
        p = q.get()["params"]["payload"]
        if p.get("kind") == "probe":
            got.append(p["n"])
    assert got == [1, 2]


def test_connect_picks_in_process_without_a_url(tmp_path: Path):
    root = _install(tmp_path)
    c = connect(root)
    assert isinstance(c, InProcessClient) and not c.remote and c.session.root == root and c.mode == "play"


@pytest.mark.timeout(300)
def test_the_tui_plays_through_a_headless_host(tmp_path: Path, monkeypatch):
    """Step ⓪ acceptance (10-10: the TUI is a client): the same TUI, on the network client, against a headless host on
    this machine — the turn runs in the host, the TUI draws the beats it receives over the wire."""
    import asyncio

    from test_engine_v3 import _install as _install_v3

    from neonrp.tui.app import ConversationView, NeonRPApp

    for k, v in {"NEONRP_PLAN_LOOP": "1", "NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "off"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NEONRP_SHOW_BEATS", raising=False)
    root = _install_v3(tmp_path)
    (root / ".neonrp" / "config.json").write_text('{"llm": {"provider": "stub", "model": "stub-model"}}', encoding="utf-8")
    server = make_engine_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("NEONRP_CONNECT_URL", f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setenv("NEONRP_CONNECT_TOKEN", hub_of(server).token)
    app = NeonRPApp(root=root, mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 44)) as pilot:
            assert getattr(app.session, "remote", False)  # the TUI holds a remote client: no engine in this process

            async def say(line: str):
                app._current_run_result = None
                app._send_message(line)
                for _ in range(120):
                    await pilot.pause(0.5)
                    if app._current_run_result is not None:
                        break
                await pilot.pause(0.5)
                r = app._current_run_result
                assert r is not None and r.success, r
                return r

            r = await say("我去主街看看")
            if str(r.route_decision or "").startswith("plan_loop:plan"):
                await say("@DM 就这么办")
            view = app.query_one("#conversation-view", ConversationView)
            bands = [str(w.content) for w in view.query(".beat-marker")]
            assert bands and app._beat_state.node == "resolve", bands  # the beats came over the wire
            # the turn really ran in the host: its session holds the player's words
            assert any("主街" in str(m.content) for m in server.runtime.session().messages if m.role == "user")

    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
