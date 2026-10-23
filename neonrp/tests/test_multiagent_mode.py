"""M18 live-wiring — "multi-agent" as a third router execution mode.

These tests pin the ONLY new behaviour added to
``ConversationSession.send`` and assert the additive contract:

  * mode == "fast"        → legacy path, unchanged (run_conversation_turn
    seam called; commit_turn NEVER touched).
  * mode == "orchestrator" → legacy path, unchanged (same seam).
  * mode == "multi-agent" WITHOUT a playthrough.json → legacy fallback
    (no commit_turn).
  * mode == "multi-agent" WITH a playthrough.json (>=1 soul) → the
    committed ``WorldAgent.commit_turn`` is driven EXACTLY ONCE and the
    turn result is coherent.

Every test mocks the LLM seam + the world-agent's commit internals; no
network, no real commit IO.
"""

from __future__ import annotations

import pytest

import json
from pathlib import Path
from unittest.mock import patch

from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.orchestration_trace import read_turn_traces
from neonrp.core.runtime_contract import set_router_execution_mode

from test_conversation import _setup_project


@pytest.fixture(autouse=True)
def _pin_v2b_loop(monkeypatch):
    """These tests cover the v2b world-agent loop; the rpg pack's own loop is v3 since 09-30 (Pack.loop)."""
    monkeypatch.setenv("NEONRP_TURN_V3", "0")


def _write_playthrough(root: Path, *, souls: list[dict] | None = None) -> None:
    """Write a schema_version 2 playthrough.json with >=1 soul by default."""
    payload = {
        "schema_version": 2,
        "playthrough_id": "pt-ma-0001",
        "world": {
            "wid": "dark-train",
            "instance_id": "wi-1",
            "version_hash": "abc",
            "head_commit": "c1",
        },
        "world_agent_team": {
            "seeded_from": "game/agents/manifest.json@abc",
            "agents": [{"id": "world-agent", "role": "orchestrator", "singleton": True}],
        },
        "souls": souls
        if souls is not None
        else [
            {
                "sid": "elena",
                "instance_id": "si-a1",
                "version_hash": "v",
                "head_commit": "s1",
                "role": "player",
            }
        ],
        "created_at": "2026-05-16T13:00:00Z",
    }
    (root / ".neonrp" / "playthrough.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _make_soul_dir(root: Path, sid: str, instance_id: str) -> None:
    """Minimal on-disk soul folder so CharacterAgent construction works."""
    soul_dir = root / "souls" / f"{sid}-{instance_id}"
    (soul_dir / "agents").mkdir(parents=True)
    (soul_dir / "short-term-memo").mkdir(parents=True)
    (soul_dir / "soul.json").write_text(
        json.dumps({"schema_version": 1, "sid": sid, "name": sid.title()}),
        encoding="utf-8",
    )
    (soul_dir / "agents" / "manifest.json").write_text(
        json.dumps({"agents": [{"id": "soul-action", "write_globs": ["*.json"]}]}),
        encoding="utf-8",
    )
    (soul_dir / "short-term-memo" / "recent_events.json").write_text(
        json.dumps({"events": []}),
        encoding="utf-8",
    )


# --- fast / orchestrator: byte-identical legacy path ---------------------


class TestNonMultiAgentUnchanged:
    def test_orchestrator_without_souls_uses_legacy_seam_no_commit(
        self, tmp_path: Path
    ) -> None:
        """Stage 2 contract: orchestrator + NO soul playthrough (the
        stoneford-orch case) is the unchanged legacy orchestrator path —
        no soul-team wrapper, no land. (orchestrator + a soul playthrough
        DOES enter the wrapper now; that path is covered by the
        commit-turn / failed-narrator tests below.)
        """
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "orchestrator")
        # Deliberately NO _write_playthrough / _make_soul_dir.

        session = ConversationSession(root, "test-agent", mode="play")
        expected = ConversationTurnResult(
            success=True, run_id="r-orch", turns_used=1
        )
        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=expected,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn"
            ) as mock_commit,
        ):
            result = session.send("hello")

        assert result.run_id == "r-orch"
        mock_run.assert_called_once()
        mock_commit.assert_not_called()

    def test_build_mode_never_enters_soul_team_wrapper(self, tmp_path: Path) -> None:
        """创作(build)会话必须 solo —— 白模板带 soul 位时,工坊每句话都把
        空白 soul 拉进并行推演(「在场灵魂(并行)」出现在创作聊天)。
        wrapper 只属于 play;build 走 legacy 单 agent 路径。"""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "orchestrator")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="build")
        expected = ConversationTurnResult(
            success=True, run_id="r-build", turns_used=1
        )
        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=expected,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn"
            ) as mock_commit,
        ):
            result = session.send("加一个新地点")

        assert result.run_id == "r-build"
        mock_run.assert_called_once()  # 只有 world-agent 一跑,无 soul 并行
        mock_commit.assert_not_called()

    def test_orchestrator_with_souls_enters_soul_team_wrapper(
        self, tmp_path: Path
    ) -> None:
        """Stage 2: orchestrator + a soul playthrough now runs the
        parallel+sticky soul-team wrapper (kagura's exact config) and
        lands the turn — the world-agent turn inside is the orchestrator.
        """
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "orchestrator")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        ok = ConversationTurnResult(
            success=True, run_id="r-orc-soul", assistant_message="hi",
            turns_used=1,
        )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-orc-souls"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=ok,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ) as mock_land,
        ):
            result = session.send("look")

        # wrapper fired: souls + world-agent ran, turn landed.
        assert result.success is True
        assert mock_land.call_count == 1
        assert mock_run.call_count == 1  # V2b 点名制:引擎只跑 world-agent(souls 经 engage 工具)
        assert result.route_decision == "multi_agent_commit:wc-orc-souls"


# --- multi-agent WITHOUT a playthrough → legacy fallback -----------------


class TestMultiAgentNoPlaythroughFallsBack:
    def test_no_playthrough_falls_back_to_legacy(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        # No playthrough.json on disk → must fall through to legacy.

        session = ConversationSession(root, "test-agent", mode="play")
        expected = ConversationTurnResult(
            success=True, run_id="r-legacy", turns_used=1
        )
        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=expected,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn"
            ) as mock_commit,
        ):
            result = session.send("hello")

        assert result.run_id == "r-legacy"
        mock_run.assert_called_once()
        mock_commit.assert_not_called()

    def test_empty_souls_falls_back_to_legacy(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        # Valid manifest but ZERO souls → not a multi-agent turn.
        _write_playthrough(root, souls=[])

        session = ConversationSession(root, "test-agent", mode="play")
        expected = ConversationTurnResult(
            success=True, run_id="r-legacy2", turns_used=1
        )
        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=expected,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn"
            ) as mock_commit,
        ):
            result = session.send("hello")

        assert result.run_id == "r-legacy2"
        mock_run.assert_called_once()
        mock_commit.assert_not_called()


# --- multi-agent WITH a playthrough → drives commit_turn once ------------


class TestMultiAgentDrivesCommitTurn:
    def test_commit_turn_called_exactly_once_and_result_coherent(
        self, tmp_path: Path
    ) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(
            root,
            souls=[
                {
                    "sid": "elena",
                    "instance_id": "si-a1",
                    "version_hash": "v",
                    "head_commit": "s1",
                    "role": "player",
                },
                {
                    "sid": "conductor",
                    "instance_id": "si-b7",
                    "version_hash": "v",
                    "head_commit": "s2",
                    "role": "npc",
                },
            ],
        )
        _make_soul_dir(root, "elena", "si-a1")
        _make_soul_dir(root, "conductor", "si-b7")

        session = ConversationSession(root, "test-agent", mode="play")
        narrator = ConversationTurnResult(
            success=True,
            run_id="r-ma",
            assistant_message="The train shudders.",
            turns_used=1,
        )

        async def _fake_land_turn(
            deltas, *, turn_seq: int, branch: str = "main"
        ) -> str:
            # Unified path: souls run via run_conversation_turn; their
            # folder-hash-derived deltas land once through land_turn with
            # the run_state-derived turn_seq + session branch.
            assert isinstance(turn_seq, int)
            assert branch == session.branch
            # V2b:souls 未被点名 → 双双走 off-stage memo,delta 照 commit
            assert len(deltas) == 2
            assert sorted(d.sid for d in deltas) == ["conductor", "elena"]
            assert all(d.state == "completed" for d in deltas)
            return "wc-deadbeef1234"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=narrator,
            ) as mock_run,
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_fake_land_turn,
            ) as mock_land,
        ):
            result = session.send("look around")

        # V2b 点名制:引擎只驱动 world-agent 一次;souls 由 leader 经
        # engage_soul 工具按需点名(此处未点名 → 零 soul 调用)。
        assert mock_run.call_count == 1
        # The turn was landed EXACTLY ONCE via the shared M17 tail.
        assert mock_land.call_count == 1
        # Coherent turn result: narration preserved, success True, and the
        # landed world commit id surfaced for the TUI/telemetry.
        assert result.success is True
        assert result.assistant_message == "The train shudders."
        assert result.route_decision == "multi_agent_commit:wc-deadbeef1234"

    def test_failed_narrator_surfaces_error_but_souls_still_land(
        self, tmp_path: Path
    ) -> None:
        """New orchestration order: souls think FIRST, the narrator
        integrates LAST. So a failed narrator no longer "skips commit" —
        the souls already acted and their memory must still land
        (continuity), with the narration failure surfaced on the result.
        """
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        failed = ConversationTurnResult(
            success=False, run_id="r-fail", error="llm down"
        )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-after-souls"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=failed,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ) as mock_land,
        ):
            result = session.send("hello")

        # Narration failure is surfaced…
        assert result.success is False
        assert result.error == "llm down"
        # …but the souls' work still landed (narrator runs last now).
        mock_land.assert_called_once()

    def test_commit_failure_surfaces_error_not_crash(
        self, tmp_path: Path
    ) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        narrator = ConversationTurnResult(
            success=True, run_id="r-ma2", assistant_message="hi", turns_used=1
        )

        async def _boom(
            deltas, *, turn_seq: int, branch: str = "main"
        ) -> str:
            raise RuntimeError("land failed")

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=narrator,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_boom,
            ),
        ):
            result = session.send("hello")

        # land_turn raising must be reported, not crash the TUI.
        assert result.success is False
        assert result.error is not None
        assert "multi-agent commit failed" in result.error

    def test_inactive_soul_is_visible_as_background_action(
        self, tmp_path: Path
    ) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(
            root,
            souls=[
                {
                    "sid": "elena",
                    "instance_id": "si-a1",
                    "version_hash": "v",
                    "head_commit": "s1",
                    "role": "player",
                },
                {
                    "sid": "rowan",
                    "instance_id": "si-b2",
                    "version_hash": "v",
                    "head_commit": "s2",
                    "role": "npc",
                },
            ],
        )
        # Make only Elena active; Rowan should remain visible as background.
        playthrough_path = root / ".neonrp" / "playthrough.json"
        data = json.loads(playthrough_path.read_text(encoding="utf-8"))
        data["active_souls"] = ["si-a1"]
        playthrough_path.write_text(json.dumps(data), encoding="utf-8")
        _make_soul_dir(root, "elena", "si-a1")
        _make_soul_dir(root, "rowan", "si-b2")

        session = ConversationSession(root, "test-agent", mode="play")
        snapshots: list[dict[str, dict[str, str]]] = []
        chunks: list[str] = []

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                return ConversationTurnResult(
                    success=True,
                    run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.7,"urgency":0.2,'
                        '"intended_action":"listen","speech":"","inner_voice":"",'
                        '"memory_delta":"","needs_world_decision":false}'
                    ),
                    turns_used=1,
                )
            return ConversationTurnResult(
                success=True,
                run_id="r-world",
                assistant_message="The world continues.",
                turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            assert sorted(d.instance_id for d in deltas) == ["si-a1", "si-b2"]
            return "wc-background"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send(
                "hello",
                on_chunk=chunks.append,
                on_soul_status=lambda snap: snapshots.append(snap),
            )

        assert result.success is True
        assert any(
            snap.get("si-b2", {}).get("state") == "background"
            for snap in snapshots
        )
        rowan_events = json.loads(
            (root / "souls" / "rowan-si-b2" / "short-term-memo" / "recent_events.json")
            .read_text(encoding="utf-8")
        )
        assert rowan_events["events"][0]["kind"] == "off-stage"


# --- session-level broker + bootstrap (M18 §4.2) -------------------------


class TestSessionBus:
    @staticmethod
    def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
        if agent_id.startswith("soul:"):
            return ConversationTurnResult(
                success=True, run_id="r-soul",
                assistant_message=(
                    '{"state":"completed","confidence":0.5,"urgency":0.1}'
                ),
                turns_used=1,
            )
        return ConversationTurnResult(
            success=True, run_id="r-world",
            assistant_message="The fog holds.", turns_used=1,
        )

    def test_subscription_survives_across_turns(self, tmp_path: Path) -> None:
        """The broker is the SESSION's: an external subscriber registered once
        receives messages from EVERY turn (previously the bus was rebuilt per
        turn, so nothing could durably subscribe)."""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        narrations: list[int] = []
        session.bus().subscribe(
            "world/narration", lambda m: narrations.append(m.seq)
        )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-bus-life"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=self._fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            assert session.send("turn one").success is True
            assert session.send("turn two").success is True

        # one durable subscription saw BOTH turns' narrations
        assert len(narrations) == 2
        assert narrations[0] < narrations[1]  # same bus, monotonic seq

    def test_bootstrap_announced_once_in_first_turn_trace(self, tmp_path: Path) -> None:
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-boot"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=self._fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            session.send("first")
            session.send("second")

        traces = read_turn_traces(root, session.branch)
        assert len(traces) == 2
        boot_first = [
            m for m in traces[0]["bus_messages"]
            if m["payload"].get("kind") == "session_bootstrap"
        ]
        boot_second = [
            m for m in traces[1]["bus_messages"]
            if m["payload"].get("kind") == "session_bootstrap"
        ]
        assert len(boot_first) == 1
        assert boot_first[0]["payload"]["souls"] == ["si-a1"]
        assert boot_second == []
        # initial world/state broadcast rides the first window too
        assert any(
            m["topic"] == "world/state" and m["payload"].get("bootstrap")
            for m in traces[0]["bus_messages"]
        )


# --- typed EngineEvent stream (M18 Phase 1) -------------------------------


class TestEngineEventStream:
    def test_pure_subscriber_frontend_no_callbacks(self, tmp_path: Path) -> None:
        """A frontend that passes NO callbacks still gets everything by
        subscribing: lifecycle on engine/event (recorded) and token streams on
        engine/stream (dispatched, never recorded)."""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        events: list[dict] = []
        streams: list[dict] = []
        session.bus().subscribe("engine/event", lambda m: events.append(m.payload))
        session.bus().subscribe("engine/stream", lambda m: streams.append(m.payload))

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                return ConversationTurnResult(
                    success=True, run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.5,"urgency":0.1}'
                    ),
                    turns_used=1,
                )
            return ConversationTurnResult(
                success=True, run_id="r-world",
                assistant_message="The fog holds.", turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-events"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("look")  # ← NO callbacks passed

        assert result.success is True
        kinds = [e.get("kind") for e in events]
        assert kinds[0] == "turn_started"
        assert kinds[-1] == "turn_finished"
        assert "soul_status" in kinds
        # V2b:引擎不再发 soul-lane divider chunk;streams 可为空
        # token streams never reach the recorded trace; lifecycle does
        rec = read_turn_traces(root, session.branch)[-1]
        topics_in_trace = {m["topic"] for m in rec["bus_messages"]}
        assert "engine/stream" not in topics_in_trace
        assert "engine/event" in topics_in_trace


# --- bus drives soul execution (M18 §3) ---------------------------------


class TestBusDrivesSoulExecution:
    def test_active_soul_is_triggered_via_its_request_topic(
        self, tmp_path: Path
    ) -> None:
        """V2b:broadcast 仍把 ScenePacket 发布到 soul/<iid>/request(观察
        面 + inbox 双写),但**不再触发执行**——souls 只由 leader 的
        engage_soul 工具驱动。断言:请求在总线上、感知在收件箱里、
        引擎只跑了 world-agent 一次。"""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)  # one soul: si-a1
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                return ConversationTurnResult(
                    success=True,
                    run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.5,"urgency":0.1,'
                        '"speech":"","inner_voice":"","intended_action":"",'
                        '"memory_delta":"","needs_world_decision":false}'
                    ),
                    turns_used=1,
                )
            return ConversationTurnResult(
                success=True, run_id="r-world",
                assistant_message="The scene holds.", turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-bus"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("look")

        assert result.success is True

        rec = read_turn_traces(root, session.branch)[-1]
        topics = [m.get("topic") for m in rec.get("bus_messages", [])]
        # The bus carried the request that TRIGGERED the soul, and the soul's
        # response — i.e. execution flowed through the broker.
        assert "soul/si-a1/request" in topics
        # 未点名 → 无全档执行回包;在场保底心跳(state=heartbeat)是唯一
        # 允许的 response(M30 lifecycle,2026-08-14)。
        rec2 = read_turn_traces(root, session.branch)[-1]
        full_runs = [
            m for m in rec2["bus_messages"]
            if m.get("topic") == "soul/si-a1/response"
            and m["payload"].get("state") != "heartbeat"
        ]
        assert full_runs == []
        from neonrp.core.inbox import peek as _peek

        assert any(
            m.kind == "perception" for m in _peek(root, "si-a1")
        )  # T2c:感知包已投收件箱,等待 engage 时消费

    def test_world_agent_publishes_narration_and_state_as_a_node(
        self, tmp_path: Path
    ) -> None:
        """The world-agent is a bus node: it publishes its NarrativeMaterial to
        world/narration and the turn's state transition to world/state, each
        tagged with the producing world_agent_id (so future location/character
        world-agents are just more nodes on the same topics)."""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                return ConversationTurnResult(
                    success=True, run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.5,"urgency":0.1,'
                        '"speech":"","inner_voice":"","intended_action":"",'
                        '"memory_delta":"","needs_world_decision":false}'
                    ),
                    turns_used=1,
                )
            return ConversationTurnResult(
                success=True, run_id="r-world",
                assistant_message="The lamps gutter in the fog.", turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-node"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("look")

        assert result.success is True
        rec = read_turn_traces(root, session.branch)[-1]
        by_topic = {m["topic"]: m["payload"] for m in rec.get("bus_messages", [])}

        assert "world/narration" in by_topic
        narration = by_topic["world/narration"]
        assert narration["text"] == "The lamps gutter in the fog."
        assert narration["world_agent_id"] == "test-agent"

        assert "world/state" in by_topic
        state = by_topic["world/state"]
        assert state["commit_id"] == "wc-node"
        assert state["world_agent_id"] == "test-agent"
        assert state["active_souls"] == ["si-a1"]

        # the player-agent node published its render directives to
        # player/<pid>/output (N=1 default pid = "player").
        assert "player/player/output" in by_topic
        out = by_topic["player/player/output"]
        assert out["kind"] == "text"
        assert out["text"] == "The lamps gutter in the fog."
        assert out["pace"] == "typewriter"


# --- living routing state: souls move, the engine counts turns -------------


class TestLivingRoutingState:
    def test_soul_moved_to_updates_run_state_and_turn_count_bumps(
        self, tmp_path: Path
    ) -> None:
        """The WORLD-AGENT owns movement: it emits a soul's final position and
        the engine writes it to that soul's run_state.json, then bumps the world
        turn_count. The soul's own (now non-binding) moved_to is IGNORED — only
        the world-agent's emitted position lands."""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")
        (root / "souls" / "elena-si-a1" / "run_state.json").write_text(
            json.dumps(
                {"sid": "elena", "instance_id": "si-a1", "location": "north-gate"}
            ),
            encoding="utf-8",
        )
        meta = root / "game" / "meta"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "run_state.json").write_text(
            json.dumps({"location": {"node": "north-gate"}, "turn_count": 0}),
            encoding="utf-8",
        )

        session = ConversationSession(root, "test-agent", mode="play")

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                # Soul states an INTENT and even a (now-ignored) moved_to of its
                # own; neither is authoritative anymore.
                return ConversationTurnResult(
                    success=True,
                    run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.6,"urgency":0.2,'
                        '"speech":"","inner_voice":"","intended_action":"去旅店",'
                        '"memory_delta":"","needs_world_decision":false,'
                        '"moved_to":"market"}'
                    ),
                    turns_used=1,
                )
            # The world-agent authors the move via the mandatory block — to the
            # inn, NOT the soul's own "market". This is what lands.
            return ConversationTurnResult(
                success=True,
                run_id="r-world",
                assistant_message=(
                    "She heads for the inn.\n"
                    '⟦CORRECTIONS⟧{"si-a1": {"moved_to": "inn"}}⟦/CORRECTIONS⟧'
                ),
                turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-move"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("你先走吧，我在这里等人。")

        assert result.success is True
        # The world-agent's emitted position landed (inn), NOT the soul's own
        # proposal (market) — movement authority is the world-agent's.
        soul_state = json.loads(
            (root / "souls" / "elena-si-a1" / "run_state.json").read_text(
                encoding="utf-8"
            )
        )
        assert soul_state["location"] == "inn"
        # The engine counted the turn (pure code, no world-agent help).
        world_state = json.loads(
            (meta / "run_state.json").read_text(encoding="utf-8")
        )
        assert world_state["turn_count"] == 1

    def test_turn_count_bump_is_idempotent_vs_world_agent(
        self, tmp_path: Path
    ) -> None:
        """If the world-agent already advanced turn_count this turn, the
        engine's bump keeps it (max), never double-counts."""
        from neonrp.core.conversation import _bump_turn_count

        meta = tmp_path / "game" / "meta"
        meta.mkdir(parents=True)
        (meta / "run_state.json").write_text(
            json.dumps({"turn_count": 6}), encoding="utf-8"
        )
        # Turn started at 5; world-agent already wrote 6 — bump keeps 6.
        _bump_turn_count(tmp_path, 5)
        state = json.loads((meta / "run_state.json").read_text(encoding="utf-8"))
        assert state["turn_count"] == 6

    def test_apply_soul_move_creates_missing_run_state(self, tmp_path: Path) -> None:
        from neonrp.core.conversation import _apply_soul_move

        soul_dir = tmp_path / "souls" / "x-si-1"
        soul_dir.mkdir(parents=True)
        assert _apply_soul_move(soul_dir, "inn") is True
        state = json.loads(
            (soul_dir / "run_state.json").read_text(encoding="utf-8")
        )
        assert state["location"] == "inn"
        # Same-node move is a no-op.
        assert _apply_soul_move(soul_dir, "inn") is False

    def test_world_agent_integration_disables_ask_user(self, tmp_path: Path) -> None:
        """M18 §3.3 turn closure: ask_user mid-integration keeps ONE engine
        turn alive across many player exchanges — souls then run only once and
        the world-agent monologues the rest. The integration call must carry
        disabled_tools={'ask_user'}; souls are unaffected."""
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")
        world_disabled: list = []
        soul_disabled: list = []

        def _fake_run(*, agent_id: str, **kwargs) -> ConversationTurnResult:
            if agent_id.startswith("soul:"):
                soul_disabled.append(kwargs.get("disabled_tools"))
                return ConversationTurnResult(
                    success=True,
                    run_id="r-soul",
                    assistant_message=(
                        '{"state":"completed","confidence":0.5,"urgency":0.1}'
                    ),
                    turns_used=1,
                )
            world_disabled.append(kwargs.get("disabled_tools"))
            return ConversationTurnResult(
                success=True, run_id="r-world",
                assistant_message="The fog holds.", turns_used=1,
            )

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-noask"

        with (
            patch(
                "neonrp.core.conversation.run_conversation_turn",
                side_effect=_fake_run,
            ),
            patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("look")

        assert result.success is True
        assert world_disabled and "ask_user" in (world_disabled[0] or set())
        # V2b:souls 不再被引擎驱动;soul 侧 disabled_tools 无从谈起
        assert soul_disabled == []


class TestAwaySoulDoesNotPerceivePlayer:
    """An away soul must not receive the player-scene narration; a co-located
    soul may. This is a MECHANISM (narration selected by location tag), not a
    prompt instruction."""

    def test_away_soul_narration_excludes_player_scene(self, tmp_path: Path) -> None:
        from neonrp.core.orchestration_trace import TurnTrace, append_turn_trace
        from neonrp.core.player_controller import read_last_narration

        t = TurnTrace(turn_seq=0)
        t.bus_messages = [
            {  # primary world-agent: the player's scene
                "topic": "world/narration",
                "payload": {
                    "world_agent_id": "world-agent",
                    "location": "north-gate",
                    "text": "玩家推开木栅门走进北门。",
                },
                "seq": 1, "ts": "T1",
            },
            {  # location world-agent: the inn
                "topic": "world/narration",
                "payload": {
                    "world_agent_id": "loc:inn",
                    "location": "inn",
                    "text": "掌柜把鱼汤推过吧台。",
                },
                "seq": 2, "ts": "T2",
            },
        ]
        append_turn_trace(tmp_path, "main", t)

        # away soul (at the inn) sees ONLY the inn — never the player's scene
        away = read_last_narration(tmp_path, location_node="inn", accept_untagged=False)
        assert "鱼汤" in away
        assert "北门" not in away and "玩家" not in away

        # co-located soul (player's node) may perceive the player's scene
        same = read_last_narration(
            tmp_path, location_node="north-gate", accept_untagged=True
        )
        assert "北门" in same


class TestHeartbeat:
    def test_present_unengaged_soul_gets_heartbeat(self, tmp_path: Path) -> None:
        """M30 lifecycle 保底:在场未点名 soul 每回合一次轻心跳——
        总线 soul_response(state=heartbeat)+ 便签(下回合 preflight)
        + 她自己的 memo(kind=heartbeat, my_reaction)。"""
        from unittest.mock import patch as _patch

        from neonrp.core import light_chat
        from neonrp.core.notes import drain_notes

        import os as _os

        _os.environ["NEONRP_HEARTBEAT"] = "1"  # conftest 默认关,此处显式开
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)  # si-a1
        _make_soul_dir(root, "elena", "si-a1")

        session = ConversationSession(root, "test-agent", mode="play")

        class _R:
            class message:
                content = "她放下茶杯,朝声音的方向偏了偏头。"

        class _A:
            def chat(self, messages, tools=None):  # noqa: ANN001
                return _R()

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-hb"

        with (
            _patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=ConversationTurnResult(
                    success=True, run_id="r-world",
                    assistant_message="炉火噼啪。", turns_used=1,
                ),
            ),
            _patch.object(light_chat, "_adapter", lambda _root: _A()),
            _patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("环顾四周")

        assert result.success is True
        # 总线:heartbeat 回包进 trace
        rec = read_turn_traces(root, session.branch)[-1]
        hb = [
            m for m in rec["bus_messages"]
            if m["topic"] == "soul/si-a1/response"
            and m["payload"].get("state") == "heartbeat"
        ]
        assert hb and "偏了偏头" in hb[0]["payload"]["digest"]
        # 便签:下回合 leader 可见(deliver-once)
        lines = drain_notes(root, "heartbeat")
        assert lines and "偏了偏头" in lines[0]
        # memo:她记得自己的反应
        ev = json.loads(
            (root / "souls" / "elena-si-a1" / "short-term-memo" / "recent_events.json")
            .read_text(encoding="utf-8")
        )["events"][-1]
        assert ev["kind"] == "heartbeat" and "偏了偏头" in ev["my_reaction"]

    def test_heartbeat_failure_falls_back_to_memo(self, tmp_path: Path) -> None:
        from unittest.mock import patch as _patch

        from neonrp.core import light_chat

        import os as _os

        _os.environ["NEONRP_HEARTBEAT"] = "1"
        root = _setup_project(tmp_path)
        set_router_execution_mode(root, "multi-agent")
        _write_playthrough(root)
        _make_soul_dir(root, "elena", "si-a1")
        session = ConversationSession(root, "test-agent", mode="play")

        class _Boom:
            def chat(self, *a, **k):  # noqa: ANN002, ANN003
                raise RuntimeError("llm down")

        async def _land(deltas, *, turn_seq: int, branch: str = "main") -> str:
            return "wc-hb2"

        with (
            _patch(
                "neonrp.core.conversation.run_conversation_turn",
                return_value=ConversationTurnResult(
                    success=True, run_id="r-world",
                    assistant_message="风声。", turns_used=1,
                ),
            ),
            _patch.object(light_chat, "_adapter", lambda _root: _Boom()),
            _patch(
                "neonrp.core.world_agent.WorldAgent.land_turn",
                side_effect=_land,
            ),
        ):
            result = session.send("听风")

        assert result.success is True  # 心跳失败绝不破坏回合
        ev = json.loads(
            (root / "souls" / "elena-si-a1" / "short-term-memo" / "recent_events.json")
            .read_text(encoding="utf-8")
        )["events"][-1]
        assert ev["kind"] == "off-stage"  # 回落纯 memo
