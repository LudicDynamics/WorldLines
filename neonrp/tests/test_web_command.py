"""Tests for the `neonrp web` runtime (server plumbing, no LLM)."""

from __future__ import annotations

import json
import queue
import urllib.request
from pathlib import Path
from unittest.mock import patch

from neonrp.commands.web import WebRuntime, make_server
from neonrp.core.conversation import ConversationTurnResult
from neonrp.core.manifest import Manifest


def _init_project(root: Path) -> None:
    neon = root / ".neonrp"
    (neon / "sessions").mkdir(parents=True)
    (neon / "events").mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (neon / "manifest.json").write_text(
        json.dumps(m.model_dump(), default=str), encoding="utf-8"
    )
    (root / "game").mkdir()


def _serve(tmp_path: Path):
    server = make_server(tmp_path, "world-agent", "127.0.0.1", 0)
    import threading

    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_index_and_state_served(tmp_path: Path) -> None:
    """`/` belongs to the shell now (形态 B): with no SPA resolved it 404s
    with the WorldLines hint; `/state` is the engine's and always answers."""
    _init_project(tmp_path)
    server, base = _serve(tmp_path)
    try:
        with patch("neonrp.commands.web._spa_root", lambda: None):
            try:
                urllib.request.urlopen(f"{base}/", timeout=5)
                raise AssertionError("expected 404 without a shell")
            except urllib.error.HTTPError as e:
                assert e.code == 404
                assert "WorldLines" in e.read().decode("utf-8")
        state = json.loads(
            urllib.request.urlopen(f"{base}/state", timeout=5).read()
        )
        assert state["kind"] == "hello"
        assert state["agent_id"] == "world-agent"
        assert isinstance(state["souls"], list)
    finally:
        server.shutdown()


def test_replay_endpoints(tmp_path: Path) -> None:
    """M18 §7: past turns are listable and fetchable for the web replay."""
    from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace

    _init_project(tmp_path)
    t = TurnTrace(turn_seq=0, player_input="我环顾四周。", world_location="north-gate")
    t.world_commit_id = "wc-replay01"
    t.landed_ok = True
    append_turn_trace(tmp_path, "main", t)
    append_turn_trace(tmp_path, "main", TurnTrace(turn_seq=1, player_input="再看一眼。"))

    server, base = _serve(tmp_path)
    try:
        listing = json.loads(
            urllib.request.urlopen(f"{base}/traces", timeout=5).read()
        )
        assert len(listing["turns"]) == 2
        assert listing["turns"][0]["input"] == "我环顾四周。"
        assert listing["turns"][0]["commit"] == "wc-replay01"

        one = json.loads(
            urllib.request.urlopen(f"{base}/trace?i=0", timeout=5).read()
        )
        assert one["turn_seq"] == 0
        assert one["world_location"] == "north-gate"

        # out of range → 404
        try:
            urllib.request.urlopen(f"{base}/trace?i=99", timeout=5)
            raise AssertionError("expected 404")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        server.shutdown()


class _BusFakeSession:
    """Fake session with a REAL bus — the web runtime subscribes to it (M18
    §6 pure-subscriber contract), and send() emits engine events the way the
    real session boundary does."""

    branch = "main"

    def __init__(self, *args, **kwargs):
        from neonrp.core.message_bus import InProcessBus

        self._bus = InProcessBus()

    def bus(self):
        return self._bus

    def send(self, text, **kwargs):
        assert not kwargs, "M18 §6: the web frontend must pass NO callbacks"
        self._bus.publish("engine/stream", {"kind": "chunk", "text": "雾还没散。"})
        self._bus.publish(
            "engine/event",
            {"kind": "soul_status", "statuses": {"si-a1": {"state": "running"}}},
        )
        # A soul publishes its per-turn report on soul/<iid>/response — the web
        # frontend forwards the psyche fields as a soul_psyche SSE event.
        self._bus.publish(
            "soul/si-a1/response",
            {
                "sid": "elena",
                "instance_id": "si-a1",
                "state": "completed",
                "structured": True,
                "digest": "- 艾琳娜: …",
                "inner_voice": "雾太重了，我得小心。",
                "confidence": 0.8,
                "urgency": 0.3,
                "memory_delta": "玩家从北门进入。",
            },
        )
        # A degraded soul: empty voice/memory + zeroed meters.
        self._bus.publish(
            "soul/si-b2/response",
            {
                "sid": "guard",
                "instance_id": "si-b2",
                "state": "degraded",
                "structured": False,
                "digest": "- 守卫: state=degraded",
                "inner_voice": "",
                "confidence": 0.0,
                "urgency": 0.0,
                "memory_delta": "",
            },
        )
        return ConversationTurnResult(
            success=True, run_id="r1", assistant_message="雾还没散。"
        )


def test_submit_turn_broadcasts_done(tmp_path: Path) -> None:
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        rt = WebRuntime(tmp_path, "world-agent")
        q = rt.broadcast.register()
        assert rt.submit("环顾四周") is True
        kinds = []
        while True:
            ev = q.get(timeout=5)
            kinds.append(ev["kind"])
            if ev["kind"] == "turn_done":
                assert ev["success"] is True
                assert "雾还没散" in ev["narration"]
                break
        assert "turn_start" in kinds
        # chunk + soul_status arrived VIA BUS SUBSCRIPTION, not callbacks
        assert "chunk" in kinds
        assert "soul_status" in kinds
        # the map graph gets fresh agent positions every turn
        assert "positions" in kinds


def test_submit_turn_broadcasts_soul_psyche(tmp_path: Path) -> None:
    """Feature A 双栏灵魂心象 — each soul's per-turn report on
    soul/<iid>/response is forwarded to the browser as a soul_psyche SSE event
    carrying exactly the frontend contract fields."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        rt = WebRuntime(tmp_path, "world-agent")
        q = rt.broadcast.register()
        assert rt.submit("环顾四周") is True
        psyches: dict[str, dict] = {}
        while True:
            ev = q.get(timeout=5)
            if ev["kind"] == "soul_psyche":
                psyches[ev["instance_id"]] = ev
            if ev["kind"] == "turn_done":
                break

    # one soul_psyche per active soul, contract fields present
    assert set(psyches) == {"si-a1", "si-b2"}
    a = psyches["si-a1"]
    assert set(a) == {
        "kind",
        "instance_id",
        "inner_voice",
        "confidence",
        "urgency",
        "memory_delta",
        "state",
    }
    assert a["inner_voice"] == "雾太重了，我得小心。"
    assert a["confidence"] == 0.8
    assert a["urgency"] == 0.3
    assert a["memory_delta"] == "玩家从北门进入。"
    assert a["state"] == "completed"
    assert isinstance(a["confidence"], float)

    # degraded soul: empty voice/memory, zeroed meters, state "degraded"
    b = psyches["si-b2"]
    assert b["inner_voice"] == ""
    assert b["memory_delta"] == ""
    assert b["confidence"] == 0.0
    assert b["urgency"] == 0.0
    assert b["state"] == "degraded"


def test_second_submit_rejected_while_busy(tmp_path: Path) -> None:
    _init_project(tmp_path)
    rt = WebRuntime(tmp_path, "world-agent")
    started = queue.Queue()
    release = queue.Queue()

    class _SlowSession:
        branch = "main"

        def send(self, text, **kwargs):
            started.put(True)
            release.get(timeout=5)  # hold the turn open
            return ConversationTurnResult(success=True, run_id="r1")

    with patch.object(rt, "session", return_value=_SlowSession()):
        assert rt.submit("a") is True
        started.get(timeout=5)  # the turn is genuinely running
        assert rt.submit("b") is False  # busy → rejected
        release.put(True)


def test_tool_error_severity_classifies_guardrails_as_warnings():
    """Guardrail/recoverable tool feedback is a warning (amber), not a red error."""
    from neonrp.commands.web import _tool_error_severity as sev

    # Recoverable guardrail feedback → warning
    assert sev("Path 'game/towns/T001/npcs.json' is not in direct_write_globs. "
               "Use submit_proposal for game/ changes.") == "warning"
    assert sev("read_file: File not found: game/meta/playthrough.json") == "warning"
    assert sev("edit_file: Text found 2 times, must be unique for safe replacement") == "warning"
    # Genuine failures → error
    assert sev("Agent 'narrator' not found") == "error"
    assert sev("LLM backend timed out") == "error"
    assert sev("") == "error"


def test_place_labels_resolve_node_ids(tmp_path: Path) -> None:
    """Map/labels must show 碧石镇, not T004 — and canonical aliases
    (north-gate ↔ gate_north) resolve to the same name."""
    _init_project(tmp_path)
    game = tmp_path / "game"
    (game / "world").mkdir(parents=True)
    (game / "world" / "world_map.json").write_text(
        json.dumps({"nodes": [
            {"id": "T004", "name_local": "碧石镇"},
            {"id": "T001", "name_local": "石津镇"},
        ]}),
        encoding="utf-8",
    )
    (game / "locations").mkdir()
    # file is north-gate, but the engine canonicalises to gate_north
    (game / "locations" / "north-gate.json").write_text(
        json.dumps({"name_local": "石津镇·北门"}), encoding="utf-8"
    )

    rt = WebRuntime(tmp_path, "world-agent")
    assert rt._location_label("T004") == "碧石镇"
    assert rt._location_label("T001") == "石津镇"
    assert rt._location_label("north-gate") == "石津镇·北门"
    assert rt._location_label("gate_north") == "石津镇·北门"  # canonical alias
    assert rt._location_label("unknown_x") == "unknown_x"     # graceful fallback

    places = rt._places_map(["T004", "gate_north", ""])
    assert places == {"T004": "碧石镇", "gate_north": "石津镇·北门"}


def test_world_map_payload(tmp_path: Path) -> None:
    """hello() ships the real world graph: town nodes + route edges +
    sub-location→town grouping (WOR-47)."""
    _init_project(tmp_path)
    game = tmp_path / "game"
    (game / "world").mkdir(parents=True)
    (game / "world" / "world_map.json").write_text(json.dumps({
        "nodes": [
            {"id": "T001", "name": "石津镇", "pos": [12, 7]},
            {"id": "T004", "name": "碧石镇", "pos": [18, 4]},
        ],
        "routes": [{"id": "R004", "from": "T001", "to": "T004"}],
    }), encoding="utf-8")
    (game / "towns" / "T001").mkdir(parents=True)
    (game / "towns" / "T001" / "town_map.json").write_text(json.dumps({
        "town_id": "T001", "nodes": [{"id": "gate_north", "name": "北门"}],
    }), encoding="utf-8")

    wm = WebRuntime(tmp_path, "world-agent").hello()["world_map"]
    assert {n["id"] for n in wm["nodes"]} == {"T001", "T004"}
    assert [n["pos"] for n in wm["nodes"] if n["id"] == "T004"][0] == [18, 4]
    assert wm["edges"] == [["T001", "T004"]]
    assert wm["subloc_to_town"]["gate_north"] == "T001"


# ── gateway facade (docs/WEBUI-UNIFICATION.md P0) ────────────────────────


def test_gateway_health_and_session(tmp_path: Path) -> None:
    """Local /api/v1/play/* mirrors the hosted gateway's shapes."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        server, base = _serve(tmp_path)
        try:
            with urllib.request.urlopen(f"{base}/api/v1/play/health") as r:
                health = json.loads(r.read())
            assert health["ok"] is True and health["service"] == "play"

            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"kind": "worlds", "slug": "ignored"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            # StartResponse contract fields the shared playClient consumes.
            assert start["session_id"] == "local"
            assert start["kind"] == "worlds"
            assert start["slug"] == tmp_path.name
            assert start["engine_mode"] in ("orchestrator", "multi-agent")
        finally:
            server.shutdown()


def test_gateway_blocking_turn(tmp_path: Path) -> None:
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        server, base = _serve(tmp_path)
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session/local/turn",
                data=json.dumps({"input": "环顾四周"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                turn = json.loads(r.read())
            # TurnResponse contract (same keys the hosted gateway returns).
            assert turn["success"] is True
            assert "雾还没散" in turn["assistant_message"]
            for key in (
                "session_id",
                "turn_tokens",
                "session_tokens",
                "session_token_cap",
                "daily_tokens",
                "daily_token_cap",
                "elapsed_ms",
            ):
                assert key in turn
        finally:
            server.shutdown()


def test_gateway_turn_stream_sse(tmp_path: Path) -> None:
    """SSE stream speaks the hosted gateway's event names (chunk/…/done)."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        server, base = _serve(tmp_path)
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session/local/turn/stream",
                data=json.dumps({"input": "环顾四周"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            events: list[tuple[str, dict]] = []
            with urllib.request.urlopen(req, timeout=10) as r:
                assert r.headers["Content-Type"].startswith("text/event-stream")
                name = None
                for raw in r:
                    line = raw.decode("utf-8").rstrip("\n")
                    if line.startswith("event: "):
                        name = line[len("event: "):]
                    elif line.startswith("data: ") and name:
                        events.append((name, json.loads(line[len("data: "):])))
                        if name == "done":
                            break
            names = [n for n, _ in events]
            assert "chunk" in names          # gateway event name, not local kind
            assert "soul_status" in names
            assert names[-1] == "done"
            done = events[-1][1]
            assert done["success"] is True
            assert "雾还没散" in done["assistant_message"]
        finally:
            server.shutdown()


def test_gateway_cors_preflight(tmp_path: Path) -> None:
    """A local SPA dev origin gets CORS; the API answers OPTIONS."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        server, base = _serve(tmp_path)
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                headers={"Origin": "http://localhost:5173"},
                method="OPTIONS",
            )
            with urllib.request.urlopen(req) as r:
                assert r.status == 204
                assert (
                    r.headers["Access-Control-Allow-Origin"]
                    == "http://localhost:5173"
                )
        finally:
            server.shutdown()


# ── launcher API (docs/WEBUI-UNIFICATION.md T0.2) ────────────────────────


def _fake_library(tmp_path: Path):
    """WORLDS_HOME with one owned world + PLAYS_HOME with two runs."""
    worlds_home = tmp_path / "lib" / "worlds"
    plays_home = tmp_path / "lib" / "plays"
    src = worlds_home / "mist-harbor"
    _init_project_at = src / ".neonrp"
    _init_project_at.mkdir(parents=True)
    m = Manifest()
    m.branches["main"].head_event = -1
    (_init_project_at / "manifest.json").write_text(
        json.dumps(m.model_dump(), default=str), encoding="utf-8"
    )
    (src / "game").mkdir()
    for run in ("mist-harbor-20260101-000000", "mist-harbor-20260102-000000"):
        d = plays_home / run
        (d / ".neonrp").mkdir(parents=True)
        (d / ".neonrp" / "manifest.json").write_text(
            json.dumps(m.model_dump(), default=str), encoding="utf-8"
        )
        (d / "game").mkdir()
    return worlds_home, plays_home


def test_launcher_saves_and_worlds(tmp_path: Path) -> None:
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            with urllib.request.urlopen(f"{base}/api/v1/play/saves") as r:
                saves = json.loads(r.read())
            assert saves["uid"] == "local"
            ids = {s["session_id"] for s in saves["saves"]}
            assert ids == {
                "mist-harbor-20260101-000000",
                "mist-harbor-20260102-000000",
            }
            # slug derived by stripping the run timestamp
            assert {s["slug"] for s in saves["saves"]} == {"mist-harbor"}
            assert all(s["in_memory"] is False for s in saves["saves"])

            with urllib.request.urlopen(f"{base}/api/v1/local/worlds") as r:
                worlds = json.loads(r.read())
            owned = {w["id"] for w in worlds["worlds"]}
            assert "mist-harbor" in owned
        finally:
            server.shutdown()


def test_launcher_session_switch_to_existing_run(tmp_path: Path) -> None:
    """POST /session {slug: <run dir>} re-points the server at that run."""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor-20260101-000000"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            assert start["slug"] == "mist-harbor-20260101-000000"
            assert server.runtime.root == plays_home / "mist-harbor-20260101-000000"

            # unknown slug stays forgiving (hosted-client semantics): attach
            # to the ACTIVE session instead of failing — the P1 zero-change
            # recipe posts whatever slug the PlayPage URL carries.
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "no-such-thing"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            assert start["slug"] == "mist-harbor-20260101-000000"  # unchanged
        finally:
            server.shutdown()


def test_launcher_session_switch_instantiates_owned_world(tmp_path: Path) -> None:
    """POST /session {slug: <owned world id>} starts a NEW run (copy)."""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            # a fresh run dir was created under PLAYS_HOME and is now active
            assert start["slug"].startswith("mist-harbor-")
            assert (plays_home / start["slug"]).is_dir()
            assert server.runtime.root == plays_home / start["slug"]
        finally:
            server.shutdown()


def test_launcher_delete_save_guards_active_run(tmp_path: Path) -> None:
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            # switch onto run A, then deleting A must 409, deleting B works
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor-20260101-000000"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req).read()

            req = urllib.request.Request(
                f"{base}/api/v1/play/saves/mist-harbor-20260101-000000",
                method="DELETE",
            )
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 409")
            except urllib.error.HTTPError as e:
                assert e.code == 409

            req = urllib.request.Request(
                f"{base}/api/v1/play/saves/mist-harbor-20260102-000000",
                method="DELETE",
            )
            with urllib.request.urlopen(req) as r:
                assert json.loads(r.read())["ok"] is True
            assert not (plays_home / "mist-harbor-20260102-000000").exists()
        finally:
            server.shutdown()



# ── launcher mode: TUI-free full loop (docs/WEBUI-UNIFICATION.md 验收2) ──


def test_launcher_mode_no_session(tmp_path: Path) -> None:
    """make_server(None): / serves the status page (no SPA build synced);
    API lists; turn 409s."""
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.commands.web._spa_root", lambda: None),  # hermetic: no synced build
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            # unbound root serves the minimal status page (the vanilla
            # /launcher page is deleted — /local owns launching)
            with urllib.request.urlopen(f"{base}/") as r:
                html = r.read().decode("utf-8")
            assert "/local" in html and "npm run build" in html

            with urllib.request.urlopen(f"{base}/api/v1/play/health") as r:
                assert json.loads(r.read())["sessions"] == 0
            with urllib.request.urlopen(f"{base}/api/v1/play/saves") as r:
                assert len(json.loads(r.read())["saves"]) == 2

            # a turn without a bound session → 409
            req = urllib.request.Request(
                f"{base}/api/v1/play/session/local/turn",
                data=json.dumps({"input": "hi"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 409")
            except urllib.error.HTTPError as e:
                assert e.code == 409

            # binding the first session from the launcher works
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor-20260101-000000"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            assert start["slug"] == "mist-harbor-20260101-000000"
            assert server.runtime is not None
        finally:
            server.shutdown()


def test_launcher_mode_builtin_scaffold(tmp_path: Path) -> None:
    """A built-in world id scaffolds a REAL run from its packaged template
    (soul-talk) and binds it — the TUI-free 'new game' path."""
    worlds_home = tmp_path / "lib" / "worlds"
    plays_home = tmp_path / "lib" / "plays"
    worlds_home.mkdir(parents=True)
    plays_home.mkdir(parents=True)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "soul-talk"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            assert start["slug"].startswith("soul-talk-")
            run_dir = plays_home / start["slug"]
            # a real, initialized, playable scaffold landed
            assert (run_dir / ".neonrp" / "manifest.json").is_file()
            assert (run_dir / "game" / "meta" / "game-start.json").is_file()
            assert (run_dir / "agents" / "world-agent" / "agent.json").is_file()
            assert server.runtime is not None
            assert server.runtime.root == run_dir
        finally:
            server.shutdown()


def test_launcher_mode_resume_alias(tmp_path: Path) -> None:
    """POST /session/<sid>/resume (shared PlayPage continue path) binds the
    save locally — resume is switch+start because sid == run-dir name."""
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session/mist-harbor-20260102-000000/resume",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as r:
                start = json.loads(r.read())
            assert start["slug"] == "mist-harbor-20260102-000000"
            assert server.runtime is not None
        finally:
            server.shutdown()


def test_meta_capability_discovery(tmp_path: Path) -> None:
    """GET /api/v1/meta — the shared UI's backend discovery (L0.0). Works in
    both bound and launcher (unbound) modes."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web.ConversationSession", _BusFakeSession):
        for root in (tmp_path, None):
            server = make_server(root, "world-agent", "127.0.0.1", 0)
            import threading

            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urllib.request.urlopen(f"{base}/api/v1/meta") as r:
                    meta = json.loads(r.read())
                assert meta["implementation"] == "local-engine"
                assert meta["auth"] == "none"
                caps = meta["capabilities"]
                assert caps["play"] is True
                assert caps["rollback"] is True
                assert caps["quotas"] is False
            finally:
                server.shutdown()


def test_white_blank_template_scaffolds_playable(tmp_path: Path) -> None:
    """L0.4: the white template materializes into a playable multi-agent world
    (manifest + playthrough + agents + its one place; 10-26: no characters — the cast comes from the library)."""
    from neonrp.worlds import scaffold_template_into

    dest = tmp_path / "wb"
    scaffold_template_into("white-blank", dest)
    for rel in (
        ".neonrp/manifest.json",
        ".neonrp/playthrough.json",
        ".neonrp/runtime_contract.json",
        "game/meta/game-start.json",
        "game/locations/T001/location.json",
        "agents/world-agent/agent.json",
    ):
        assert (dest / rel).is_file(), rel
    pt = json.loads((dest / ".neonrp/playthrough.json").read_text(encoding="utf-8"))
    assert pt["souls"] == [] and pt["active_souls"] == [] and not (dest / "souls").exists()
    # blankness: no stoneford leakage in the world content
    leaked = []
    for f in dest.rglob("*.json"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        if "石津" in text or "Stoneford" in text or "elena" in text:
            leaked.append(str(f.relative_to(dest)))
    assert not leaked, leaked


# ── CREATE contract, local end (docs/WEBUI-UNIFICATION.md L0.1) ──────────


class _EditFakeSession:
    """Fake build-mode session: emits tool callbacks and actually writes a
    file into the world dir — the create contract's acceptance shape."""

    def __init__(self, root, agent_id, mode="play", **kwargs):
        assert mode == "build", "create sessions must be build-mode"
        self.root = Path(root)

    def send(self, text, on_thinking=None, on_chunk=None,
             on_tool_use=None, on_tool_result=None, **kwargs):
        target = self.root / "game" / "lore" / "story.md"
        if on_tool_use:
            on_tool_use("write_file", {"path": "game/lore/story.md", "content": "…"})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# 创作\n\n{text}\n", encoding="utf-8")
        if on_tool_result:
            on_tool_result("write_file", {"path": "game/lore/story.md"}, "ok")
        if on_chunk:
            on_chunk("已把设定写进 story.md。")
        return ConversationTurnResult(
            success=True, run_id="r-edit", assistant_message="已写入 story.md"
        )


def _post_json(base: str, path: str, body: dict):
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req)


def _sse_events(resp) -> list[tuple[str, dict]]:
    events, name = [], None
    for raw in resp:
        line = raw.decode("utf-8").rstrip("\n")
        if line.startswith("event: "):
            name = line[len("event: "):]
        elif line.startswith("data: ") and name:
            events.append((name, json.loads(line[len("data: "):])))
            if name == "done" or name == "error":
                break
    return events


def test_create_contract_full_loop(tmp_path: Path) -> None:
    """L0.1 验收: scaffold 白模 → 对话一轮 agent 真改库源文件 → tree/file →
    playtest 落一个可玩 run。"""
    worlds_home = tmp_path / "lib" / "worlds"
    plays_home = tmp_path / "lib" / "plays"
    worlds_home.mkdir(parents=True)
    plays_home.mkdir(parents=True)
    with (
        patch("neonrp.commands.web.ConversationSession", _EditFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            # meta declares the create capability
            with urllib.request.urlopen(f"{base}/api/v1/meta") as r:
                assert json.loads(r.read())["capabilities"]["create"] is True

            # 1) scaffold the white template into the library
            with _post_json(base, "/api/v1/create/session",
                            {"template": "white-blank", "name": "misty-isle"}) as r:
                start = json.loads(r.read())
            assert start["session_id"] == "edit-local"
            assert start["world_id"] == "misty-isle"
            assert (worlds_home / "misty-isle" / ".neonrp" / "playthrough.json").is_file()
            paths = {f["path"] for f in start["files"]}
            assert "game/meta/game-start.json" in paths
            assert ".neonrp/sessions" not in " ".join(paths)  # internals excluded

            # 2) one edit message → agent writes a real file, SSE shows it
            with _post_json(base, "/api/v1/create/session/edit-local/message",
                            {"input": "这是一座常年起雾的海岛"}) as r:
                events = _sse_events(r)
            names = [n for n, _ in events]
            assert "tool_use" in names and "tool_result" in names
            assert names[-1] == "done" and events[-1][1]["success"] is True
            story = worlds_home / "misty-isle" / "game" / "lore" / "story.md"
            assert "常年起雾的海岛" in story.read_text(encoding="utf-8")

            # 3) tree + file read
            with urllib.request.urlopen(
                f"{base}/api/v1/create/session/edit-local/tree"
            ) as r:
                tree = json.loads(r.read())
            assert any(f["path"] == "game/lore/story.md" for f in tree["files"])
            with urllib.request.urlopen(
                f"{base}/api/v1/create/session/edit-local/file?path=game/lore/story.md"
            ) as r:
                assert "常年起雾" in json.loads(r.read())["content"]
            # traversal guarded
            try:
                urllib.request.urlopen(
                    f"{base}/api/v1/create/session/edit-local/file?path=../../etc/passwd"
                )
                raise AssertionError("expected 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400

            # 4) playtest: instantiate a run + bind the play runtime
            with _post_json(base, "/api/v1/create/session/edit-local/playtest", {}) as r:
                play = json.loads(r.read())
            assert play["slug"].startswith("misty-isle-")
            assert (plays_home / play["slug"]).is_dir()
            assert server.runtime is not None
            # the library source keeps the edit; the run carries a copy
            run_story = plays_home / play["slug"] / "game" / "lore" / "story.md"
            assert "常年起雾" in run_story.read_text(encoding="utf-8")
        finally:
            server.shutdown()


def test_create_session_opens_existing_owned_world(tmp_path: Path) -> None:
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _EditFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with _post_json(base, "/api/v1/create/session",
                            {"world_id": "mist-harbor"}) as r:
                start = json.loads(r.read())
            assert start["world_id"] == "mist-harbor"
            assert start["template"] is None
            # unknown world 404s
            try:
                _post_json(base, "/api/v1/create/session", {"world_id": "nope"})
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()


# ── local shell APIs: settings + souls (docs/WEBUI-UNIFICATION.md L0.2) ──


def test_local_settings_and_souls(tmp_path: Path) -> None:
    souls_home = tmp_path / "lib" / "souls"
    soul_dir = souls_home / "mira-20260101-000000"
    soul_dir.mkdir(parents=True)
    (soul_dir / "soul.json").write_text(
        json.dumps({"schema_version": 1, "sid": "mira", "name": "Mira",
                    "name_local": "米拉", "version": "1.0"}),
        encoding="utf-8",
    )
    saved: list[tuple] = []
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.core.souls.SOUL_HOME", souls_home),
        patch("neonrp.presets._save_key_to_user_config",
              lambda pid, key, model_override=None: saved.append((pid, key, model_override))),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            # settings: presets listed (read-only, real list_presets)
            with urllib.request.urlopen(f"{base}/api/v1/local/settings") as r:
                settings = json.loads(r.read())
            assert isinstance(settings["presets"], list) and settings["presets"]
            assert {"id", "display", "available"} <= set(settings["presets"][0])

            # key save routes through the TUI's persistence function
            req = urllib.request.Request(
                f"{base}/api/v1/local/settings/key",
                data=json.dumps({"preset_id": "deepseek", "api_key": "sk-test-123"}).encode(),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req) as r:
                assert json.loads(r.read())["ok"] is True
            assert saved == [("deepseek", "sk-test-123", None)]

            # souls library lists + deletes
            with urllib.request.urlopen(f"{base}/api/v1/local/souls") as r:
                lib = json.loads(r.read())
            assert any(s["sid"] == "mira" for s in lib["souls"])
            req = urllib.request.Request(
                f"{base}/api/v1/local/souls/mira-20260101-000000", method="DELETE"
            )
            with urllib.request.urlopen(req) as r:
                assert json.loads(r.read())["ok"] is True
            assert not soul_dir.exists()
        finally:
            server.shutdown()


def test_saves_carry_feed_tease_and_cover_route(tmp_path: Path) -> None:
    worlds_home, plays_home = _fake_library(tmp_path)
    run = plays_home / "mist-harbor-20260101-000000"
    (run / "feed.jsonl").write_text(
        json.dumps({"turn_seq": 3, "world_time": "Day2 09:00",
                    "summary": "米拉在码头等你,雾散了。"}) + "\n",
        encoding="utf-8",
    )
    (run / "feed.md").write_text("# 今日动态\n\n**正在等你回应：** mira\n", encoding="utf-8")
    (worlds_home / "mist-harbor" / "assets").mkdir(parents=True)
    (worlds_home / "mist-harbor" / "assets" / "cover.png").write_bytes(b"\x89PNGfake")
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base}/api/v1/play/saves") as r:
                saves = {s["session_id"]: s for s in json.loads(r.read())["saves"]}
            s1 = saves["mist-harbor-20260101-000000"]
            assert "米拉在码头等你" in s1["feed_tease"]
            assert s1["waiting"] == ["mira"]
            assert saves["mist-harbor-20260102-000000"]["feed_tease"] == ""

            with urllib.request.urlopen(f"{base}/api/v1/local/worlds/mist-harbor/cover") as r:
                assert r.read().startswith(b"\x89PNG")
            try:
                urllib.request.urlopen(f"{base}/api/v1/local/worlds/nope/cover")
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            server.shutdown()


# ── LocalShell SPA serving (docs/WEBUI-UNIFICATION.md §7.5 LP1) ──────────


def _fake_spa(tmp_path: Path) -> Path:
    """A minimal vite-build-shaped SPA dir; tests monkeypatch _spa_root to it
    (writing into the real src/neonrp/webui/spa would pollute the source tree)."""
    spa = tmp_path / "spa-build"
    (spa / "assets").mkdir(parents=True)
    (spa / "index.html").write_text(
        "<!doctype html><div id='root'>LocalShell SPA</div>", encoding="utf-8"
    )
    (spa / "assets" / "app.js").write_text("console.log('shell')", encoding="utf-8")
    (spa / "vite.svg").write_text("<svg></svg>", encoding="utf-8")
    return spa


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None  # surface 3xx as HTTPError instead of following


def test_spa_served_with_history_fallback(tmp_path: Path) -> None:
    """/local (and any /local/* route — history fallback) serve index.html;
    /assets/* serve the bundles with real content types; traversal is refused."""
    _init_project(tmp_path / "cur")
    spa = _fake_spa(tmp_path)
    with patch("neonrp.commands.web._spa_root", lambda: spa):
        server, base = _serve(tmp_path / "cur")
        try:
            for path in ("/local", "/local/create/studio", "/local/play/x?y=1"):
                with urllib.request.urlopen(f"{base}{path}", timeout=5) as r:
                    assert r.status == 200
                    assert r.headers["Content-Type"].startswith("text/html")
                    assert "LocalShell SPA" in r.read().decode("utf-8")

            with urllib.request.urlopen(f"{base}/assets/app.js", timeout=5) as r:
                assert r.headers["Content-Type"].startswith("application/javascript")
                assert "shell" in r.read().decode("utf-8")

            # other top-level build files resolve by path
            with urllib.request.urlopen(f"{base}/vite.svg", timeout=5) as r:
                assert r.headers["Content-Type"] == "image/svg+xml"

            # path traversal out of the build dir is refused
            try:
                urllib.request.urlopen(f"{base}/assets/../secret", timeout=5)
                raise AssertionError("expected 400/404")
            except urllib.error.HTTPError as e:
                assert e.code in (400, 404)

            # unknown asset → clean 404
            try:
                urllib.request.urlopen(f"{base}/assets/nope.js", timeout=5)
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404

            # "/" is the shell's too (the vanilla play page retired with 29ddc02)
            html = urllib.request.urlopen(f"{base}/", timeout=5).read().decode()
            assert "LocalShell SPA" in html
        finally:
            server.shutdown()


def test_spa_missing_local_404s_with_hint(tmp_path: Path) -> None:
    """No shell resolved → /local 404s and points at the WorldLines shell
    (install the shell / set NEONRP_SPA_DIR — not sync_play_ui)."""
    _init_project(tmp_path)
    with patch("neonrp.commands.web._spa_root", lambda: None):
        server, base = _serve(tmp_path)
        try:
            try:
                urllib.request.urlopen(f"{base}/local", timeout=5)
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404
                body = e.read().decode("utf-8")
                assert "NEONRP_SPA_DIR" in body
                assert "WorldLines" in body
        finally:
            server.shutdown()


def test_launcher_mode_root_redirects_to_spa(tmp_path: Path) -> None:
    """Launcher mode + packaged SPA: / 302s into /local (which serves it)."""
    worlds_home, plays_home = _fake_library(tmp_path)
    spa = _fake_spa(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.commands.web._spa_root", lambda: spa),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            opener = urllib.request.build_opener(_NoRedirect)
            try:
                opener.open(f"{base}/", timeout=5)
                raise AssertionError("expected 302")
            except urllib.error.HTTPError as e:
                assert e.code == 302
                assert e.headers["Location"] == "/local"

            # and the redirect target actually serves the shell
            with urllib.request.urlopen(f"{base}/local", timeout=5) as r:
                assert "LocalShell SPA" in r.read().decode("utf-8")
        finally:
            server.shutdown()


def test_session_bind_applies_preset(tmp_path: Path) -> None:
    """PrePlay 模型接入: POST /session {slug, preset} 把 provider 写进 run 的
    config 并重建 runtime(visionrp 式进场界面的后端)。"""
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.presets.build_config_dict",
              lambda pid: {"preset": pid, "models": {}}),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with _post_json(base, "/api/v1/play/session",
                            {"slug": "mist-harbor-20260101-000000",
                             "preset": "deepseek"}) as r:
                start = json.loads(r.read())
            assert start["slug"] == "mist-harbor-20260101-000000"
            cfg = json.loads(
                (plays_home / "mist-harbor-20260101-000000" / ".neonrp" / "config.json")
                .read_text(encoding="utf-8")
            )
            assert cfg["preset"] == "deepseek"
        finally:
            server.shutdown()


def test_parent_watchdog_exits_when_parent_dies(monkeypatch) -> None:
    """--parent-pid 看门狗:父进程(桌面壳)消失后引擎自杀(os._exit)。

    desktop/electron 与 desktop/tauri 都靠这个兜底 —— 壳被 SIGKILL 也不留
    孤儿引擎占端口。
    """
    import threading as _threading

    from neonrp.commands import web as web_mod

    exited = _threading.Event()

    def fake_kill(pid: int, sig: int) -> None:
        raise OSError("no such process")  # 父进程已死

    monkeypatch.setattr(web_mod.os, "kill", fake_kill)
    monkeypatch.setattr(web_mod.os, "_exit", lambda code: exited.set())

    web_mod.start_parent_watchdog(999999, interval=0.01)
    assert exited.wait(timeout=2.0), "watchdog should exit after parent death"


def test_parent_alive_live_process_probe() -> None:
    """_parent_alive:活进程 → True,不存在的 pid → False,两平台实测。

    Windows 上 os.kill(pid, 0) == CTRL_C_EVENT,对别的 pid 必抛 OSError,
    旧看门狗把活着的桌面壳当死了 → 引擎启动 2 秒后自杀(Tauri 里 Welcome
    渲染后 API 全灭的根因)。win32 分支走 OpenProcess —— 本用例在 Windows
    CI 上就是对那个分支的实测。"""
    import os

    from neonrp.commands import web as web_mod

    assert web_mod._parent_alive(os.getpid()) is True
    # pid 回收窗口极小的大值;两平台上都应判死
    assert web_mod._parent_alive(2 ** 22 + 12345) is False


def test_parent_alive_posix_kill_semantics(monkeypatch) -> None:
    """POSIX 分支:os.kill(pid, 0) 成功 → 活;OSError → 死。"""
    import sys as _sys

    if _sys.platform == "win32":
        import pytest as _pytest

        _pytest.skip("posix-only branch")
    from neonrp.commands import web as web_mod

    monkeypatch.setattr(web_mod.os, "kill", lambda pid, sig: None)
    assert web_mod._parent_alive(4242) is True

    def raise_oserror(pid: int, sig: int) -> None:
        raise OSError("gone")

    monkeypatch.setattr(web_mod.os, "kill", raise_oserror)
    assert web_mod._parent_alive(4242) is False


def test_cover_route_decodes_unicode_world_id(tmp_path: Path) -> None:
    """中文世界名(如「猫岛」)的封面路由:URL 编码段必须先 unquote,
    否则 %E7%8C%AB%E5%B2%9B 被 _safe_name 里的 % 判非法 → 400(实机踩过)。"""
    from urllib.parse import quote

    worlds_home, plays_home = _fake_library(tmp_path)
    cat = worlds_home / "猫岛"
    (cat / "assets").mkdir(parents=True)
    (cat / "assets" / "cover.png").write_bytes(b"\x89PNGcat")
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            url = f"{base}/api/v1/local/worlds/{quote('猫岛')}/cover"
            with urllib.request.urlopen(url) as r:
                assert r.read().startswith(b"\x89PNG")
        finally:
            server.shutdown()


# ── LOCAL-PARITY-CHECKLIST B1-B9 backend routes ──────────────────────────


def test_world_export_and_import_roundtrip(tmp_path: Path) -> None:
    """B3+B2:导出 owned 世界 → zip 下载;再把同一 zip 导入回库(改名落地)。"""
    worlds_home, plays_home = _fake_library(tmp_path)
    (worlds_home / "mist-harbor" / "game" / "town.json").write_text(
        '{"id": "T001"}', encoding="utf-8"
    )
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.core.world_export.GAME_HOME", worlds_home, create=True),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base}/api/v1/local/worlds/mist-harbor/export") as r:
                assert r.headers["Content-Type"] == "application/zip"
                zip_bytes = r.read()
            assert zip_bytes[:2] == b"PK"

            # 未知 / 非 owned → 404
            try:
                urllib.request.urlopen(f"{base}/api/v1/local/worlds/nope/export")
                raise AssertionError("expected 404")
            except urllib.error.HTTPError as e:
                assert e.code == 404

            # 导入回库:同名已存在 → 带时间戳后缀落地
            req = urllib.request.Request(
                f"{base}/api/v1/local/import/world",
                data=zip_bytes,
                method="POST",
                headers={"Content-Type": "application/zip"},
            )
            with urllib.request.urlopen(req) as r:
                out = json.loads(r.read())
            assert out["ok"] is True
            assert out["world_id"].startswith("mist-harbor")
            assert (worlds_home / out["world_id"] / "game" / "town.json").exists()
        finally:
            server.shutdown()


def test_session_save_undo_redo_routes(tmp_path: Path) -> None:
    """B5:save/undo/redo 路由把请求转给核心函数并回传结果。"""
    _init_project(tmp_path / "cur")
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch(
            "neonrp.commands.save.create_save_snapshot",
            return_value={"save_id": "s1", "branch": "main", "head_event": 3, "game_hash": "x" * 24},
        ) as snap,
        patch(
            "neonrp.commands.branch.perform_undo",
            return_value={"ok": True, "message": "undone", "head_event": 2},
        ),
        patch(
            "neonrp.commands.branch.perform_redo",
            return_value={"ok": False, "message": "Nothing to redo.", "head_event": 2},
        ),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session/local/save",
                data=json.dumps({"name": "before-boss"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                out = json.loads(r.read())
            assert out["ok"] is True and out["save_id"] == "s1"
            assert snap.call_args.args[1] == "before-boss"

            for route, expect_ok in (("undo", True), ("redo", False)):
                req = urllib.request.Request(
                    f"{base}/api/v1/play/session/local/{route}",
                    data=b"{}",
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req) as r:
                    out = json.loads(r.read())
                assert out["ok"] is expect_ok
        finally:
            server.shutdown()


def test_session_bind_casts_souls_on_fresh_run(tmp_path: Path) -> None:
    """B4/B6:bind 带 souls 时只对新建 run 投放(resolve_soul_dir + cast)。"""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    soul_dir = tmp_path / "lib" / "souls" / "elena-x1"
    soul_dir.mkdir(parents=True)
    (soul_dir / "soul.json").write_text("{}", encoding="utf-8")
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.core.placement.SOUL_HOME", soul_dir.parent),
        patch("neonrp.cli._cast_bring_in_souls") as cast,
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            # owned world id → instantiate_run 新 run → 投放执行
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor", "souls": ["elena-x1"]}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                json.loads(r.read())
            assert cast.called
            dirs = cast.call_args.args[1]
            assert dirs == (str(soul_dir),)

            # 已有 run(resume 语义)带 souls → 不投放
            cast.reset_mock()
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps(
                    {"slug": "mist-harbor-20260101-000000", "souls": ["elena-x1"]}
                ).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                json.loads(r.read())
            assert not cast.called
        finally:
            server.shutdown()


def test_settings_image_and_create_provider_routes(tmp_path: Path) -> None:
    """B7/B8:settings GET 带 image 段;PUT image / create-provider 落到 config。"""
    _init_project(tmp_path / "cur")
    fake_cfg: dict = {}
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.core.imagegen.load_user_config", lambda: fake_cfg),
        patch("neonrp.core.imagegen.save_user_config", lambda d: fake_cfg.update(d)),
        patch("neonrp.presets.set_create_provider") as scp,
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/local/settings/image",
                data=json.dumps(
                    {"backend": "comfyui", "comfyui_url": "http://127.0.0.1:8188"}
                ).encode(),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                out = json.loads(r.read())
            assert out["ok"] is True and out["configured"] is True
            assert fake_cfg["image"]["comfyui_url"] == "http://127.0.0.1:8188"

            with urllib.request.urlopen(f"{base}/api/v1/local/settings") as r:
                st = json.loads(r.read())
            assert st["image"]["backend"] == "comfyui"
            assert "openai_key" not in st["image"]  # 只写不读

            req = urllib.request.Request(
                f"{base}/api/v1/local/settings/create-provider",
                data=json.dumps({"preset_id": "deepseek"}).encode(),
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                assert json.loads(r.read())["ok"] is True
            scp.assert_called_once_with("deepseek")
        finally:
            server.shutdown()


def test_soul_create_requires_creation_llm(tmp_path: Path) -> None:
    """B1:解析链 显式 preset→create_provider→第一个可用;全空 → 400 引导。"""
    _init_project(tmp_path / "cur")
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.presets.get_create_provider", return_value=None),
        patch("neonrp.presets.list_presets", return_value=[
            {"id": "anthropic", "display": "Claude", "available": False},
        ]),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/local/souls",
                data=json.dumps({"name": "艾琳娜", "seed": "一位治愈师"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400
                assert "no usable LLM" in e.read().decode()
        finally:
            server.shutdown()


def test_switch_away_from_busy_run_abandons_it(tmp_path: Path) -> None:
    """离开正在生成回合的游戏去开别的游戏必须立刻成功(实机踩过:
    409 a turn is in progress 把 launcher 卡死)。旧回合线程被放弃,
    只有回到同一个忙碌 run 才 409。"""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def bind(slug: str) -> int:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": slug}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req) as r:
                    r.read()
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code

        try:
            assert bind("mist-harbor-20260101-000000") == 200
            # 模拟在途回合:占住 busy 锁(新绑的局先自己跑开场那一拍、拿着锁几百毫秒,等它放手再占)
            assert server.runtime._busy.acquire(timeout=5)
            # 换另一个 run → 立刻成功,旧 runtime 被放弃
            assert bind("mist-harbor-20260102-000000") == 200
            assert server.runtime.root.name == "mist-harbor-20260102-000000"
        finally:
            server.shutdown()


# ── STUDIO-CANVAS-PLAN C1-C3 backend ─────────────────────────────────────


def _canvas_env(tmp_path: Path):
    """一个带 world_map 的 owned 世界 + 指到 tmp 的 STUDIO_HOME。"""
    worlds_home, plays_home = _fake_library(tmp_path)
    src = worlds_home / "mist-harbor"
    (src / "game" / "world").mkdir(parents=True)
    (src / "game" / "world" / "world_map.json").write_text(json.dumps({
        "world_id": "mist-harbor", "seed": 7,
        "nodes": [
            {"id": "T001", "type": "town", "name": "石津镇", "pos": [12, 7],
             "state": {"discovered": True}},
            {"id": "T002", "type": "town", "name": "北岭", "pos": [20, 3]},
        ],
        "routes": [{"id": "R001", "from": "T001", "to": "T002", "kind": "road",
                    "distance": 18, "tags": ["trade"]},
                   # 悬空 route(白模板裁剪残留的真实形态)— GET 不投影
                   {"id": "R099", "from": "T001", "to": "GONE"}],
    }, ensure_ascii=False), encoding="utf-8")
    (src / "game" / "player").mkdir(parents=True)
    (src / "game" / "player" / "flags.json").write_text(
        json.dumps({"met_elena": False, "gold_paid": 0}), encoding="utf-8")
    studio_home = tmp_path / "lib" / "studio"
    return worlds_home, plays_home, studio_home


def _put_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{base}{path}", data=json.dumps(payload).encode(), method="PUT",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa: BLE001
            return e.code, {}


def test_canvas_map_roundtrip_preserves_unknown_fields(tmp_path: Path) -> None:
    """C1:世界图 GET 投影 nodes/routes;PUT 改 pos/加节点/删路线,
    world_map 的其它字段(seed/state/tags)原样保留。"""
    worlds_home, plays_home, studio_home = _canvas_env(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.worlds.STUDIO_HOME", studio_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/create/session",
                data=json.dumps({"world_id": "mist-harbor"}).encode(),
                method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                r.read()
            with urllib.request.urlopen(
                f"{base}/api/v1/create/session/edit-local/canvas/map"
            ) as r:
                cv = json.loads(r.read())
            assert {n["id"] for n in cv["nodes"]} == {"T001", "T002"}
            assert [e["id"] for e in cv["edges"]] == ["R001"]  # R099 悬空被滤
            assert cv["edges"][0]["source"] == "T001"

            # 拖动 T001、新增 T003、删掉 R001、连 T002→T003
            cv["nodes"][0]["pos"] = [14.5, 8.25]
            cv["nodes"].append({"id": "T003", "pos": [30, 10],
                                "data": {"label": "苔墓", "summary": "会说话的棺木"}})
            cv["edges"] = [{"id": "R002", "source": "T002", "target": "T003",
                            "data": {"kind": "trail"}}]
            status, saved = _put_json(
                base, "/api/v1/create/session/edit-local/canvas/map", cv)
            assert status == 200
            wm = json.loads((worlds_home / "mist-harbor" / "game" / "world" /
                             "world_map.json").read_text(encoding="utf-8"))
            byid = {n["id"]: n for n in wm["nodes"]}
            assert byid["T001"]["pos"] == [14.5, 8.25]
            assert byid["T001"]["state"] == {"discovered": True}  # 未投影字段保留
            assert byid["T003"]["name"] == "苔墓"
            assert wm["seed"] == 7
            assert [r["id"] for r in wm["routes"]] == ["R002"]

            # 自环 route → 400
            bad = dict(saved)
            bad["edges"] = [{"id": "RX", "source": "T001", "target": "T001", "data": {}}]
            status, _ = _put_json(
                base, "/api/v1/create/session/edit-local/canvas/map", bad)
            assert status == 400
        finally:
            server.shutdown()


def test_canvas_story_and_relation_studio_files(tmp_path: Path) -> None:
    """C2/C3:story/relation 画布落 STUDIO_HOME(世界目录零污染);
    校验去重/端点存在;GET 空态给默认画布。entities 端点给引用目录。"""
    worlds_home, plays_home, studio_home = _canvas_env(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.worlds.STUDIO_HOME", studio_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/create/session",
                data=json.dumps({"world_id": "mist-harbor"}).encode(),
                method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                r.read()
            # 空态默认
            with urllib.request.urlopen(
                f"{base}/api/v1/create/session/edit-local/canvas/story"
            ) as r:
                assert json.loads(r.read()) == {"nodes": [], "edges": [], "viewport": {}}
            # 存一版剧情(重复节点 id 去重;边端点校验)
            status, saved = _put_json(
                base, "/api/v1/create/session/edit-local/canvas/story",
                {"nodes": [
                    {"id": "sf-1", "pos": [10, 10], "data": {"label": "入镇", "node_type": "scene"}},
                    {"id": "sf-1", "pos": [0, 0], "data": {"label": "重复"}},
                    {"id": "sf-2", "pos": [200, 10], "data": {"label": "苔墓", "node_type": "clue"}},
                ], "edges": [
                    {"id": "se-1", "source": "sf-1", "target": "sf-2",
                     "data": {"flag_key": "met_elena", "operator": "is_true"}},
                ], "viewport": {"x": 1, "y": 2, "zoom": 1.5}})
            assert status == 200 and len(saved["nodes"]) == 2
            flow_file = studio_home / "mist-harbor" / "flow.json"
            assert flow_file.exists()
            # 世界目录零污染
            assert not (worlds_home / "mist-harbor" / "authoring").exists()

            status, _ = _put_json(
                base, "/api/v1/create/session/edit-local/canvas/story",
                {"nodes": [{"id": "a", "pos": [0, 0], "data": {}}],
                 "edges": [{"id": "e", "source": "a", "target": "missing", "data": {}}]})
            assert status == 400

            # relation:去重 + 拒自环
            status, saved = _put_json(
                base, "/api/v1/create/session/edit-local/canvas/relation",
                {"relationships": [
                    {"source": "NPC001", "target": "NPC002", "relation_type": "债务",
                     "description": "欠 50 金", "strength": 9},
                    {"source": "NPC001", "target": "NPC002", "relation_type": "债务"},
                    {"source": "NPC001", "target": "NPC001", "relation_type": "自环"},
                ], "layout": {"positions": {"NPC001": [80, 80]}}})
            assert status == 200
            assert len(saved["relationships"]) == 1
            assert saved["relationships"][0]["strength"] == 5  # clamp 1-5

            # entities 目录
            with urllib.request.urlopen(
                f"{base}/api/v1/create/session/edit-local/entities"
            ) as r:
                ents = json.loads(r.read())
            assert {loc["id"] for loc in ents["locations"]} >= {"T001", "T002"}
            assert {f["key"] for f in ents["flags"]} == {"met_elena", "gold_paid"}
            assert {f["type"] for f in ents["flags"]} == {"boolean", "number"}
        finally:
            server.shutdown()


def test_fresh_bind_injects_localized_opening(tmp_path: Path) -> None:
    """新开 run 的 bind 必须注入开场指令(kickoff 进页即开演)——
    实测的「进入世界不立即开始」bug;resume 已有回合的存档则不注入。
    续一局一个回合都没有的存档(开场那一拍当时没跑完,sessions/ 已经写了)= 再给开场,kickoff 照常开演(10-16 浏览器版续档空舞台)。"""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def bind(slug: str) -> None:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": slug}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                r.read()

        played = plays_home / "mist-harbor-20260101-000000" / ".neonrp"
        (played / "orchestration").mkdir()
        (played / "orchestration" / "main.jsonl").write_text('{"turn_seq": 0}\n', encoding="utf-8")
        empty = plays_home / "mist-harbor-20260102-000000" / ".neonrp"
        (empty / "sessions").mkdir()
        (empty / "sessions" / "main.jsonl").write_text('{"role":"user"}\n', encoding="utf-8")
        try:
            bind("mist-harbor")  # owned world id → 新 run
            assert server.runtime._startup_commands, "fresh run must carry opening"
            bind("mist-harbor-20260101-000000")  # 已有回合的存档 → 不注入
            assert not server.runtime._startup_commands
            sent: list[str] = []
            with patch("neonrp.commands.web.WebRuntime.submit", lambda self, text: sent.append(text) or True):
                bind("mist-harbor-20260101-000000")
                assert sent == []
                bind("mist-harbor-20260102-000000")  # 一个回合都没有的存档 → 再给开场,bind 当场开演(sessions/ 有东西也开)
            assert server.runtime._startup_commands, "a save with no turns must get its opening again"
            assert sent == server.runtime._startup_commands[:1], "the bind kicked the opening off"
        finally:
            server.shutdown()


def test_create_session_inherits_creation_llm_and_rename(tmp_path: Path) -> None:
    """工坊三矛盾修复:①开创作会话把解析的创作 LLM 写进世界 config;
    ②PUT name 改显示名;③PUT llm 换 provider 并重建会话。"""
    worlds_home, plays_home = _fake_library(tmp_path)
    fake_cfg = {"provider": "openai", "model": "stub"}
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.presets.get_create_provider", return_value="deepseek"),
        patch("neonrp.presets.build_config_dict", return_value=fake_cfg),
        patch("neonrp.presets.set_create_provider"),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def req(method: str, path: str, payload: dict) -> tuple[int, dict]:
            r = urllib.request.Request(
                f"{base}{path}", data=json.dumps(payload).encode(), method=method,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(r) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                return e.code, {}

        try:
            status, _ = req("POST", "/api/v1/create/session", {"world_id": "mist-harbor"})
            assert status == 200
            # ① 创作 LLM 已写进世界 config
            cfg = json.loads((worlds_home / "mist-harbor" / ".neonrp" / "config.json").read_text(encoding="utf-8"))
            assert cfg == fake_cfg
            # ② 改名落到 game-start.json
            status, out = req("PUT", "/api/v1/create/session/edit-local/name", {"name": "雾汐港"})
            assert status == 200 and out["world_name"] == "雾汐港"
            gs = json.loads((worlds_home / "mist-harbor" / "game" / "meta" / "game-start.json").read_text(encoding="utf-8"))
            assert gs["name"] == "雾汐港"
            # ③ 换 LLM ok
            status, out = req("PUT", "/api/v1/create/session/edit-local/llm", {"preset_id": "openai"})
            assert status == 200 and out["preset"] == "openai"
        finally:
            server.shutdown()


def test_bind_with_preset_keeps_opening(tmp_path: Path) -> None:
    """PrePlay 总是带 preset:应用 preset 会重建 runtime,开场指令必须
    随之继承(二次实测:进游戏不自动开演的回归)。"""
    _init_project(tmp_path / "cur")
    worlds_home, plays_home = _fake_library(tmp_path)
    fake_cfg = {"provider": "openai", "model": "stub"}
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
        patch("neonrp.presets.build_config_dict", return_value=fake_cfg),
    ):
        server = make_server(None, "world-agent", "127.0.0.1", 0)
        import threading

        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            req = urllib.request.Request(
                f"{base}/api/v1/play/session",
                data=json.dumps({"slug": "mist-harbor", "preset": "openai"}).encode(),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as r:
                r.read()
            assert server.runtime._startup_commands, (
                "preset rebuild must carry the opening handoff"
            )
        finally:
            server.shutdown()


def test_instantiate_run_strips_builder_sessions(tmp_path: Path) -> None:
    """工坊编辑污染的世界源(.neonrp/sessions 有 build 会话日志)开新 run
    时必须剥离 —— 否则 kickoff 误判已开局,玩家卡在「世界正在苏醒」。"""
    worlds_home, plays_home = _fake_library(tmp_path)
    src = worlds_home / "mist-harbor"
    (src / ".neonrp" / "sessions").mkdir(parents=True)
    (src / ".neonrp" / "sessions" / "main.jsonl").write_text('{"role":"user"}\n', encoding="utf-8")
    (src / ".neonrp" / "events").mkdir()
    (src / ".neonrp" / "events" / "e1.json").write_text("{}", encoding="utf-8")
    with (
        patch("neonrp.worlds.WORLDS_HOME", worlds_home),
        patch("neonrp.worlds.PLAYS_HOME", plays_home),
    ):
        from neonrp.worlds import _is_game_started, instantiate_run

        run = instantiate_run("mist-harbor")
        assert not (run / ".neonrp" / "sessions").exists()
        assert not (run / ".neonrp" / "events").exists()
        assert (run / ".neonrp" / "manifest.json").exists()  # 配置保留
        assert _is_game_started(run) is False  # 新 run 是新局 → 开场会发


def test_worldlines_web_is_the_player_entry(tmp_path: Path) -> None:
    """入口规范:worldlines web 是玩家词;neonrp web 标 internal。"""
    from click.testing import CliRunner

    from neonrp.cli import worldlines_cli
    from neonrp.commands.web import web as neonrp_web

    r = CliRunner().invoke(worldlines_cli, ["web", "--help"])
    assert r.exit_code == 0 and "/local" in r.output
    r2 = CliRunner().invoke(worldlines_cli, ["--help"])
    assert "worldlines web" in r2.output
    assert "[internal]" in (neonrp_web.__doc__ or "")


def test_settings_judge_routes(tmp_path: Path, monkeypatch) -> None:
    """判断器(Jev)设置(10-25):GET settings 带 judge 段(不回 key);PUT judge 写 config;POST judge/test 走当前后端。"""
    _init_project(tmp_path / "cur")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr("neonrp.core.user_config.USER_CONFIG_PATH", tmp_path / "home" / ".neonrp" / "config.json")
    for k in ("TYPESAFE_API_KEY", "HUB_API_TOKEN", "NEONRP_S1_LLM_PRESET", "WORLDLINES_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("NEONRP_S1_BACKEND", raising=False)
    with (
        patch("neonrp.commands.web.ConversationSession", _BusFakeSession),
        patch("neonrp.core.worldlines_auth.access_token", return_value=None),
        patch("neonrp.core.judge_settings.preset_choices", return_value=["deepseek"]),
    ):
        server, base = _serve(tmp_path / "cur")
        try:
            def put(body: dict) -> dict:
                req = urllib.request.Request(f"{base}/api/v1/local/settings/judge", data=json.dumps(body).encode(), method="PUT", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())

            out = put({"mode": "off", "api_key": "ts-abcdefghijkl"})
            assert out["ok"] and out["judge"]["mode"] == "off" and out["judge"]["key_set"] and out["judge"]["key_masked"] == "ts-a…ijkl"
            assert "ts-abcdefghijkl" not in json.dumps(out)
            cfg = json.loads((tmp_path / "home" / ".neonrp" / "config.json").read_text())
            assert cfg["judge"]["mode"] == "off" and cfg["models"]["typesafe"]["api_key"] == "ts-abcdefghijkl"

            with urllib.request.urlopen(f"{base}/api/v1/local/settings") as r:
                st = json.loads(r.read())
            assert st["judge"]["mode"] == "off" and st["judge"]["effective"] == "off" and st["judge"]["presets"] == ["deepseek"]
            assert "ts-abcdefghijkl" not in json.dumps(st)

            out = put({"clear_key": True, "llm_preset": "deepseek", "mode": "auto"})
            assert not out["judge"]["key_set"] and out["judge"]["llm_preset"] == "deepseek" and out["judge"]["effective"] == "llm"

            req = urllib.request.Request(f"{base}/api/v1/local/settings/judge", data=json.dumps({"mode": "nope"}).encode(), method="PUT", headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req)
                raise AssertionError("expected 400")
            except urllib.error.HTTPError as e:
                assert e.code == 400

            put({"mode": "off"})
            req = urllib.request.Request(f"{base}/api/v1/local/settings/judge/test", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                t = json.loads(r.read())
            assert t["ok"] is False and t["error"] == "off"
        finally:
            server.shutdown()
