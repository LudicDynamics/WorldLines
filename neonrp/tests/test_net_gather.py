"""凑齐 (NET-MULTIPLAYER-1009 §十一, 10-10): a second person plays a character in the world. Before the turn settles, the
engine asks every human-played character in the scene what they do; their words reach the narrator as that character's
intent; silence is hesitation — never a stand-in."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from test_engine_v3 import _install

from neonrp.commands.serve import make_engine_server
from neonrp.core import soul_remote, turn_v3
from neonrp.core.playthrough import read_playthrough
from neonrp.net.client import RemoteClient
from neonrp.net.host import hub_of


@pytest.fixture
def table(tmp_path: Path, monkeypatch):
    for k, v in {"NEONRP_TURN_V3": "1", "NEONRP_S1_BACKEND": "off"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("NEONRP_PLAN_LOOP", raising=False)
    root = _install(tmp_path)
    (root / ".neonrp" / "config.json").write_text('{"llm": {"provider": "stub", "model": "stub-model"}}', encoding="utf-8")
    iid = read_playthrough(root).souls[0].instance_id
    server = make_engine_server(root, "world-agent", "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    host = RemoteClient(url, hub_of(server).token)
    host.call("room.auto_approve", {"on": True})
    seen: list[list[dict]] = []
    real = turn_v3.solve_turn

    def spy(*a, **k):
        seen.append(list(k.get("soul_reports") or []))
        return real(*a, **k)

    monkeypatch.setattr(turn_v3, "solve_turn", spy)
    yield root, iid, url, host, seen
    host.close()
    server.shutdown()
    server.server_close()


def _sit(url, host, iid, answer):
    c = RemoteClient.join(url, host.call("room.invite", {"kind": "character", "target": iid})["token"])
    c.on("soul.ask", answer)
    end = time.time() + 5
    while soul_remote.route(iid) is None and time.time() < end:
        time.sleep(0.05)
    assert soul_remote.is_human(iid)
    return c


@pytest.mark.timeout(300)
def test_the_second_player_says_what_her_character_does(table):
    root, iid, url, host, seen = table
    asked: list[str] = []
    friend = _sit(url, host, iid, lambda p: (asked.append(p["question"]), "我跟在你后面,手按着剑柄。")[1])
    try:
        r = host.send("我推开北门旁边的小门")
        assert r.success, r.error
        assert asked and "我推开北门旁边的小门" in asked[0]  # she was asked, with what the player just did
        mine = [x for x in seen[-1] if x.get("iid") == iid and x.get("kind") == "intent"]
        assert mine and mine[0]["text"] == "我跟在你后面,手按着剑柄。"
        # and the host's model never voiced her (no engine-made line for a character a person is playing)
        assert [x["kind"] for x in seen[-1] if x.get("iid") == iid] == ["intent"]
    finally:
        friend.close()


@pytest.mark.timeout(300)
def test_silence_is_hesitation_not_a_stand_in(table, monkeypatch):
    root, iid, url, host, seen = table
    monkeypatch.setattr(soul_remote, "HUMAN_TIMEOUT", 0.5)
    friend = _sit(url, host, iid, lambda p: (time.sleep(3), "太晚了")[1])
    try:
        r = host.send("我推开北门旁边的小门")
        assert r.success, r.error
        mine = [x for x in seen[-1] if x.get("iid") == iid]
        assert len(mine) == 1 and mine[0].get("hesitated") and "太晚了" not in mine[0]["text"]
    finally:
        friend.close()


def test_a_character_seat_sees_the_story_and_her_own_channel(table):
    root, iid, url, host, seen = table
    friend = _sit(url, host, iid, lambda p: "在")
    try:
        assert friend.call("session.whoami")["kind"] == "character"
        from neonrp.net.seats import Principal

        p = Principal("character:x", "character", iid)
        assert p.sees("engine/stream") and p.sees(f"soul/{iid}/request") and not p.sees("soul/other/request")
        assert not p.may_call("turn.send")  # she speaks when the table turns to her
    finally:
        friend.close()


@pytest.mark.timeout(300)
def test_a_tui_at_a_character_seat_answers_the_table(table, monkeypatch):
    """The real TUI holding a character's seat: the table turns to it, the question shows, the next line typed is the
    answer (not a new turn)."""
    import asyncio

    from neonrp.core import light_chat
    from neonrp.tui.app import ConversationView, NeonRPApp

    root, iid, url, host, seen = table
    seat = RemoteClient.join(url, host.call("room.invite", {"kind": "character", "target": iid})["token"])
    cred = seat.token
    seat.close()
    monkeypatch.setenv("NEONRP_CONNECT_URL", url)
    monkeypatch.setenv("NEONRP_CONNECT_TOKEN", cred)
    app = NeonRPApp(root=root, mode="play")
    got: dict = {}

    async def scenario() -> None:
        async with app.run_test(size=(140, 44)) as pilot:
            end = time.time() + 5
            while soul_remote.route(iid) is None and time.time() < end:
                await pilot.pause(0.1)
            th = threading.Thread(target=lambda: got.update(light_chat.ask_soul_deliver(root, iid, "这一回合你做什么?")))
            th.start()
            for _ in range(50):
                await pilot.pause(0.1)
                if getattr(app, "_net_pending_ask", None):
                    break
            assert app._net_pending_ask, "the question never reached the TUI"
            rows = " ".join(str(w.content) for w in app.query_one("#conversation-view", ConversationView).query(".pc-status"))
            assert "这一回合你做什么" in rows
            app._send_message("我拔出剑,挡在门口。")
            for _ in range(50):
                await pilot.pause(0.1)
                if got:
                    break
            th.join(5)

    asyncio.run(scenario())
    assert got.get("ok") and got.get("remote") and got["answer"] == "我拔出剑,挡在门口。"


@pytest.mark.timeout(300)
def test_the_host_tui_invites_from_status_room(table, monkeypatch):
    import asyncio

    from neonrp.tui.app import ConversationView, NeonRPApp

    root, iid, url, host, seen = table
    monkeypatch.setenv("NEONRP_CONNECT_URL", url)
    monkeypatch.setenv("NEONRP_CONNECT_TOKEN", host.token)
    app = NeonRPApp(root=root, mode="play")

    async def scenario() -> None:
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause(0.3)
            from neonrp.tui import net_room

            net_room.cmd_room(app, ["invite", "character", iid, "小林"])
            for _ in range(40):
                await pilot.pause(0.1)
                text = " ".join(str(w.content) for w in app.query_one("#conversation-view", ConversationView).query(".pc-out"))
                if "worldlines://join?" in text:
                    break
            assert "worldlines://join?" in text and f"character:{iid}" in text

    asyncio.run(scenario())
