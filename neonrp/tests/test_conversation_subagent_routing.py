from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from neonrp.core.active_agent import get_active_agent_id, write_active_agent
from neonrp.core.conversation import ConversationSession, ConversationTurnResult
from neonrp.core.llm import LLMTurnResult, Message, ToolCall
from neonrp.core.manifest import Manifest


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "m12" / "minimal-routing-world"


def _load_fixture_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE_ROOT, root)
    neonrp_dir = root / ".neonrp"
    (neonrp_dir / "events").mkdir(parents=True, exist_ok=True)
    (neonrp_dir / "sessions").mkdir(parents=True, exist_ok=True)
    manifest = Manifest()
    manifest.branches["main"].head_event = -1
    (neonrp_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(), default=str), encoding="utf-8")
    return root


def _set_player_location(root: Path, location_id: str) -> None:
    player_path = root / "game" / "player" / "player.json"
    payload = json.loads(player_path.read_text(encoding="utf-8"))
    payload["location"] = location_id
    player_path.write_text(json.dumps(payload), encoding="utf-8")


def _set_router_execution_mode(root: Path, execution_mode: str) -> None:
    path = root / ".neonrp" / "runtime_contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("router", {})["execution_mode"] = execution_mode
    path.write_text(json.dumps(payload), encoding="utf-8")


def _routing_metrics(results: list[ConversationTurnResult]) -> dict[str, float | int]:
    delegation_total = sum(1 for result in results if result.delegated_to)
    delegation_correct = sum(1 for result in results if result.delegated_to and result.assistant_speaker == result.delegated_to)
    wrong_owner = sum(1 for result in results if result.delegated_to and result.assistant_speaker != result.delegated_to)
    return {
        "delegation_correctness_rate": (delegation_correct / delegation_total) if delegation_total else 1.0,
        "wrong_owner_op_count": wrong_owner,
    }


class _TaskThenNarrateAdapter:
    def __init__(self, target_agent: str, final_text: str):
        self.target_agent = target_agent
        self.final_text = final_text
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(id=f"task-{self.target_agent}", name="task", arguments={"agent_id": self.target_agent, "prompt": f"Handle via {self.target_agent}"})
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content=self.final_text), finished=True)


class _NarrateOnlyAdapter:
    def chat(self, messages, tools=None):
        return LLMTurnResult(
            message=Message(role="assistant", content="The narrator handles this directly."),
            finished=True,
        )


def test_fast_router_without_specialists_falls_back_to_narrator(tmp_path: Path) -> None:
    root = tmp_path / "project"
    neonrp_dir = root / ".neonrp"
    (neonrp_dir / "events").mkdir(parents=True)
    (neonrp_dir / "sessions").mkdir(parents=True)
    (root / "game").mkdir(parents=True)
    manifest = Manifest()
    manifest.branches["main"].head_event = -1
    (neonrp_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(), default=str),
        encoding="utf-8",
    )
    (neonrp_dir / "config.json").write_text(
        json.dumps({"llm": {"provider": "stub", "max_context_chars": 100000}}),
        encoding="utf-8",
    )
    (neonrp_dir / "runtime_contract.json").write_text(
        json.dumps({"router": {"agent_id": "narrator", "execution_mode": "fast"}}),
        encoding="utf-8",
    )
    narrator_dir = root / "agents" / "narrator"
    narrator_dir.mkdir(parents=True)
    (narrator_dir / "agent.json").write_text(
        json.dumps(
            {
                "id": "narrator",
                "name": "Narrator",
                "policy": {"role": "router", "disallow_direct_game_tools": False},
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        ),
        encoding="utf-8",
    )

    session = ConversationSession(root=root, agent_id="narrator", mode="play")
    with (
        patch("neonrp.core.conversation.get_adapter_from_config", return_value=_NarrateOnlyAdapter()),
        patch("neonrp.core.conversation._dispatch_sub_agent") as mock_dispatch,
    ):
        result = session.send("Handle this scene.")

    assert result.success is True
    assert result.assistant_message == "The narrator handles this directly."
    assert result.route_decision == "self"
    mock_dispatch.assert_not_called()


def test_orchestrator_mode_keeps_router_as_speaker_with_locked_active_agent(tmp_path: Path) -> None:
    root = _load_fixture_project(tmp_path)
    _set_router_execution_mode(root, "orchestrator")
    write_active_agent(root, "town-agent", reason="in town", exit_condition="leave town", updated_by="narrator")
    session = ConversationSession(root=root, agent_id="narrator", mode="play")

    payload = json.dumps(
        {
            "status": "success",
            "data": {
                "run_id": "orch-town-1",
                "agent_id": "town-agent",
                "assistant_text": "The clerk answers from behind the counter.",
                "files_modified": [],
                "turns_used": 1,
                "route_decision": "active_agent_lock",
                "active_agent": "town-agent",
                "delegated_to": "town-agent",
            },
        }
    )

    with (
        patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TaskThenNarrateAdapter("town-agent", "Narrator presents the guild fees clearly.")),
        patch("neonrp.core.conversation._dispatch_sub_agent", return_value=payload),
    ):
        result = session.send("Ask about guild fees")

    assert result.success is True
    assert result.assistant_speaker == "narrator"
    assert result.delegated_to == "town-agent"
    assert result.route_decision == "self"


def test_orchestrator_mode_does_not_roll_same_turn_between_specialists(tmp_path: Path) -> None:
    root = _load_fixture_project(tmp_path)
    _set_router_execution_mode(root, "orchestrator")
    session = ConversationSession(root=root, agent_id="narrator", mode="play")

    calls: list[str] = []

    def _dispatch(*args, **kwargs):
        task_data = kwargs.get("task_data") or args[0]
        agent_id = task_data["agent_id"]
        calls.append(agent_id)
        if agent_id == "town-agent":
            _set_player_location(root, "moss-catacomb")
            write_active_agent(root, "narrator", reason="left town", updated_by="town-agent")
            return json.dumps(
                {
                    "status": "success",
                    "data": {
                        "run_id": "orch-town-exit",
                        "agent_id": "town-agent",
                        "assistant_text": "You step out of town toward the catacombs.",
                        "files_modified": ["game/player/player.json"],
                        "turns_used": 1,
                        "route_decision": "router_selected_specialist",
                        "active_agent": "narrator",
                        "delegated_to": "town-agent",
                        "handoff_to": "narrator",
                    },
                }
            )
        return json.dumps(
            {
                "status": "success",
                "data": {
                    "run_id": "orch-dungeon-1",
                    "agent_id": "dungeon-agent",
                    "assistant_text": "The dungeon mouth waits in silence.",
                    "files_modified": [],
                    "turns_used": 1,
                    "route_decision": "router_selected_specialist",
                    "active_agent": "narrator",
                    "delegated_to": "dungeon-agent",
                },
            }
        )

    with (
        patch("neonrp.core.conversation.get_adapter_from_config", side_effect=[
            _TaskThenNarrateAdapter("town-agent", "Narrator ends the turn at the dungeon entrance."),
            _TaskThenNarrateAdapter("dungeon-agent", "Narrator describes the dungeon mouth in detail."),
        ]),
        patch("neonrp.core.conversation._dispatch_sub_agent", side_effect=_dispatch),
    ):
        first = session.send("Leave town")
        second = session.send("Look around carefully")

    assert calls == ["town-agent", "dungeon-agent"]
    assert first.assistant_speaker == "narrator"
    assert first.delegated_to == "town-agent"
    assert second.assistant_speaker == "narrator"
    assert second.delegated_to == "dungeon-agent"


