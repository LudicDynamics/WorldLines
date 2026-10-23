"""Edge and branch tests for core/conversation.py."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from neonrp.core.active_agent import get_active_agent_id, write_active_agent
from neonrp.core.conversation import (
    ConversationSession,
    ConversationTurnResult,
    _chat_stream,
    _dispatch_sub_agent,
    _finalize_turn,
    _handle_skill_tool,
    _should_release_active_agent_lock,
    _handle_todo_tool,
    _merge_usage,
    _normalize_tool_call,
    _select_router_target_agent,
    _track_modified_files,
    _trim_broken_tail,
    _truncate_messages_for_budget,
    run_conversation_turn,
)
from neonrp.core.llm import LLMTurnResult, Message, StreamChunk, ToolCall
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path
from neonrp.core.todo import TodoManager


def _init_project(root: Path, *, agent_json: str | None = None, manifest_json: str | None = None) -> None:
    neonrp_dir = root / ".neonrp"
    (neonrp_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (neonrp_dir / "events").mkdir(parents=True, exist_ok=True)
    (root / "game").mkdir(parents=True, exist_ok=True)

    (neonrp_dir / "config.json").write_text(
        json.dumps({"llm": {"provider": "stub", "max_context_chars": 1000}, "tui": {"session_max_turns": 50}}),
        encoding="utf-8",
    )

    if manifest_json is None:
        manifest = Manifest()
        manifest.branches["main"].head_event = -1
        manifest_json = json.dumps(manifest.model_dump(), default=str)
    get_manifest_path(root).write_text(manifest_json, encoding="utf-8")

    if agent_json is not None:
        agent_dir = root / "agents" / "test-agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "agent.json").write_text(agent_json, encoding="utf-8")


def _default_agent_json() -> str:
    return json.dumps(
        {
            "id": "test-agent",
            "name": "Test Agent",
            "permissions": {
                "read_globs": ["**"],
                "deny_globs": [],
                "write_globs": ["**"],
                "direct_write_globs": [],
            },
        }
    )


class _TextAdapter:
    def chat(self, messages, tools=None):
        return LLMTurnResult(message=Message(role="assistant", content="ok"), finished=True)


class _CaptureSystemPromptAdapter:
    def __init__(self):
        self.system_prompt = ""

    def chat(self, messages, tools=None):
        self.system_prompt = messages[0].content if messages else ""
        return LLMTurnResult(message=Message(role="assistant", content="ok"), finished=True)



class _FailAdapter:
    def chat(self, messages, tools=None):
        return LLMTurnResult(error="boom", finished=True)


class _AskUserThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(id="ask-1", name="ask_user", arguments={"question": "Q?", "options": ["A", "B"]})
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content="done"), finished=True)


class _TaskThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(id="task-1", name="task", arguments={"agent_id": "other", "prompt": "do thing"})
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content="done"), finished=True)


class _TaskToAdapter:
    def __init__(self, target_agent: str, final_text: str):
        self.target_agent = target_agent
        self.final_text = final_text
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(id=f"task-{self.target_agent}", name="task", arguments={"agent_id": self.target_agent, "prompt": f"handle via {self.target_agent}"})
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content=self.final_text), finished=True)


class _SelfTaskThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(id="task-self", name="task", arguments={"agent_id": "test-agent", "prompt": "self"})
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content="done"), finished=True)


class _LoopToolAdapter:
    def chat(self, messages, tools=None):
        tool = ToolCall(
            id="todo-1",
            name="TodoWrite",
            arguments={"todos": [{"content": "X", "status": "in_progress", "activeForm": "Doing X"}]},
        )
        return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)


class _RepeatedReadFileAdapter:
    def chat(self, messages, tools=None):
        tool = ToolCall(
            id="read-1",
            name="read_file",
            arguments={"path": "game/meta/active-agent.json", "max_chars": 2000},
        )
        return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)


class _NarratorWriteThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool = ToolCall(
                id="write-1",
                name="write_file",
                arguments={"path": "game/player/player.json", "content": '{"id":"player"}'},
            )
            return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
        return LLMTurnResult(message=Message(role="assistant", content="narrated"), finished=True)


class _StreamAdapter:
    def chat_stream(self, messages, tools=None):
        yield StreamChunk(delta="A")
        yield StreamChunk(thinking="T")
        yield StreamChunk(delta="B", usage={"total_tokens": 3}, finished=True)


class _StreamErrorAdapter:
    def chat_stream(self, messages, tools=None):
        yield StreamChunk(delta="partial")
        yield StreamChunk(error="stream fail", finished=True)


class _RetryableStreamErrorAdapter:
    def chat_stream(self, messages, tools=None):
        yield StreamChunk(delta="partial")
        yield StreamChunk(error="Network connection lost.", finished=True, retryable=True)


class _ExplodingStreamAdapter:
    def chat_stream(self, messages, tools=None):
        raise RuntimeError("stream exploded")


class TestRunConversationTurnGuards:
    def test_rejects_invalid_mode(self, tmp_path: Path):
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], mode="invalid")  # type: ignore[arg-type]
        assert result.success is False
        assert "Unsupported mode" in (result.error or "")

    def test_missing_agent_directory(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=None)
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "not found" in (result.error or "")

    def test_missing_agent_json(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=None)
        (tmp_path / "agents" / "test-agent").mkdir(parents=True, exist_ok=True)
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "agent.json" in (result.error or "")

    def test_invalid_agent_json(self, tmp_path: Path):
        _init_project(tmp_path, agent_json="{bad json")
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "Cannot read agent.json" in (result.error or "")

    def test_missing_manifest(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        get_manifest_path(tmp_path).unlink()
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "not initialized" in (result.error or "")

    def test_invalid_manifest_json(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json(), manifest_json="{bad json")
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "Failed to load manifest" in (result.error or "")

    def test_branch_missing_from_manifest(self, tmp_path: Path):
        manifest = Manifest()
        manifest.current_branch = "ghost"
        _init_project(
            tmp_path,
            agent_json=_default_agent_json(),
            manifest_json=json.dumps(manifest.model_dump(), default=str),
        )
        result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "Branch 'ghost' not found" in (result.error or "")

    def test_adapter_initialization_failure(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        with patch("neonrp.core.conversation.get_adapter_from_config", side_effect=RuntimeError("init fail")):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], fixture_path="f")
        assert result.success is False
        assert "Failed to initialize LLM adapter" in (result.error or "")

    def test_build_mode_falls_back_to_default_narrator_agent_after_init(self, tmp_path: Path):
        """Init-only projects should still work conversationally in build mode."""
        _init_project(tmp_path, agent_json=None)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextAdapter()):
            result = run_conversation_turn(tmp_path, "narrator", [Message(role="user", content="x")], mode="build")
        assert result.success is True
        assert result.assistant_message == "ok"

    def test_init_only_build_prompt_includes_builtin_skill_catalog(self, tmp_path: Path):
        """Fresh init-only projects should advertise packaged builtin skills."""
        _init_project(tmp_path, agent_json=None)
        adapter = _CaptureSystemPromptAdapter()
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(tmp_path, "narrator", [Message(role="user", content="x")], mode="build")
        assert result.success is True
        assert "entity-authoring: " in adapter.system_prompt
        assert 'Skill(skill="entity-authoring")' in adapter.system_prompt


class TestRunConversationTurnToolAndLoopPaths:
    def test_llm_error_is_returned_with_turn_number(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_FailAdapter()):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "LLM call failed on turn 1" in (result.error or "")

    def test_ask_user_without_callback_returns_tool_error(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        tool_results: list[str] = []

        def on_tool_result(name: str, args: dict[str, object], result_text: str) -> None:
            tool_results.append(result_text)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_AskUserThenTextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_tool_result=on_tool_result,
            )
        assert result.success is True
        assert any("ask_user not available" in payload for payload in tool_results)

    def test_task_tool_path_dispatches_sub_agent(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        tool_results: list[str] = []

        def on_tool_result(name: str, args: dict[str, object], result_text: str) -> None:
            tool_results.append(result_text)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TaskThenTextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_tool_result=on_tool_result,
            )
        assert result.success is True
        # Task tool now attempts execution; target agent "other" doesn't exist,
        # so it should return an error from the sub-agent dispatch.
        assert any("error" in payload.lower() for payload in tool_results)
        parsed = [json.loads(payload) for payload in tool_results if payload.strip().startswith("{")]
        assert any(p.get("status") == "error" and isinstance(p.get("error"), str) and p.get("error") for p in parsed)

    def test_task_dispatch_uses_full_subagent_turn_budget(self, tmp_path: Path):
        """Sub-agent should use the configured turn cap, not parent's remaining turns."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        dispatch_calls: list[dict[str, object]] = []

        def _fake_dispatch(*, task_data, root, mode, max_turns, **kwargs):  # type: ignore[no-untyped-def]
            dispatch_calls.append({"task_data": task_data, "max_turns": max_turns, "mode": mode})
            return json.dumps({"status": "success", "data": {"ok": True}})

        with (
            patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TaskThenTextAdapter()),
            patch("neonrp.core.conversation._dispatch_sub_agent", side_effect=_fake_dispatch),
        ):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                max_turns=2,
            )

        assert result.success is True
        assert dispatch_calls
        assert dispatch_calls[0]["max_turns"] == 2

    def test_task_cancelled_result_stops_parent_turn(self, tmp_path: Path):
        """When sub-agent task returns cancelled, parent turn should stop immediately."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        adapter = _TaskThenTextAdapter()
        tool_results: list[str] = []

        def on_tool_result(_name: str, _args: dict[str, object], result_text: str) -> None:
            tool_results.append(result_text)

        with (
            patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter),
            patch(
                "neonrp.core.conversation._dispatch_sub_agent",
                return_value=json.dumps({"status": "cancelled", "error": "Sub-agent canceled by user"}),
            ),
        ):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_tool_result=on_tool_result,
            )

        assert result.success is True
        assert result.cancelled is True
        # Should not continue to the adapter's second turn ("done").
        assert adapter.calls == 1
        parsed = [json.loads(payload) for payload in tool_results if payload.strip().startswith("{")]
        assert any(p.get("status") == "cancelled" for p in parsed)

    def test_task_self_delegation_is_blocked(self, tmp_path: Path):
        _init_project(
            tmp_path,
            agent_json=json.dumps(
                {
                    "id": "test-agent",
                    "name": "Test Agent",
                    "tools": ["task"],
                    "permissions": {
                        "read_globs": ["**"],
                        "deny_globs": [],
                        "write_globs": ["**"],
                        "direct_write_globs": ["**"],
                    },
                }
            ),
        )
        tool_results: list[str] = []
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_SelfTaskThenTextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="loop")],
                on_tool_result=lambda _n, _a, payload: tool_results.append(payload),
            )
        assert result.success is True
        parsed = [json.loads(payload) for payload in tool_results if payload.strip().startswith("{")]
        assert any(
            p.get("status") == "error" and "cannot delegate to itself" in str(p.get("error", "")).lower()
            for p in parsed
        )

    def test_agent_tools_allowlist_blocks_unconfigured_tool_calls(self, tmp_path: Path):
        _init_project(
            tmp_path,
            agent_json=json.dumps(
                {
                    "id": "test-agent",
                    "name": "Test Agent",
                    "tools": ["read_file"],
                    "permissions": {
                        "read_globs": ["**"],
                        "deny_globs": [],
                        "write_globs": ["**"],
                        "direct_write_globs": ["**"],
                    },
                }
            ),
        )
        tool_results: list[str] = []
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_AskUserThenTextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_tool_result=lambda _n, _a, payload: tool_results.append(payload),
            )
        assert result.success is True
        parsed = [json.loads(payload) for payload in tool_results if payload.strip().startswith("{")]
        assert any(
            p.get("status") == "error" and "not enabled for agent" in str(p.get("error", "")).lower()
            for p in parsed
        )

    def test_play_mode_uses_write_globs_when_direct_write_globs_is_empty(self, tmp_path: Path):
        _init_project(
            tmp_path,
            agent_json=json.dumps(
                {
                    "id": "test-agent",
                    "name": "Test Agent",
                    "tools": ["write_file"],
                    "permissions": {
                        "read_globs": ["**"],
                        "deny_globs": [],
                        "write_globs": ["game/**"],
                        "direct_write_globs": [],
                    },
                }
            ),
        )
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_NarratorWriteThenTextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="write in play")],
                mode="play",
            )
        assert result.success is True
        assert (tmp_path / "game" / "player" / "player.json").exists()

    def test_world_agent_in_multi_agent_mode_may_write_game_entities(self, tmp_path: Path):
        """M18: in multi-agent mode the router id IS the world-agent, which
        owns world truth — the narrator guardrail must NOT block its game/**
        writes (e.g. the mandatory run_state.json location update)."""
        from neonrp.core.runtime_contract import set_router_execution_mode

        world_json = json.dumps(
            {
                "id": "world-agent",
                "name": "World Agent",
                "must_not_do": ["directly handle town/dungeon operations"],
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        )
        _init_project(tmp_path, agent_json=world_json)
        wa_dir = tmp_path / "agents" / "world-agent"
        wa_dir.mkdir(parents=True, exist_ok=True)
        (wa_dir / "agent.json").write_text(world_json, encoding="utf-8")
        # narrator id resolves to world-agent (the stoneford shape)
        cfg_path = tmp_path / ".neonrp" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg.setdefault("tui", {})["narrator_agent_id"] = "world-agent"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        set_router_execution_mode(tmp_path, "multi-agent")

        messages = [Message(role="user", content="update the player state")]
        with patch(
            "neonrp.core.conversation.get_adapter_from_config",
            return_value=_NarratorWriteThenTextAdapter(),
        ):
            result = run_conversation_turn(
                tmp_path, "world-agent", messages, mode="build", current_depth=1
            )

        assert result.success is True
        # The write went THROUGH — no guardrail block.
        tool_msgs = [m for m in messages if m.role == "tool" and m.name == "write_file"]
        assert len(tool_msgs) == 1
        payload = json.loads(tool_msgs[0].content or "{}")
        assert payload.get("status") != "error", payload

    def test_orchestrator_mode_does_not_auto_route_from_active_agent(self, tmp_path: Path):
        narrator_json = json.dumps(
            {
                "id": "narrator",
                "name": "Narrator",
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        )
        _init_project(tmp_path, agent_json=narrator_json)
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(
                {
                    "router": {
                        "agent_id": "narrator",
                        "state_file": "meta/active-agent.json",
                        "startup_file": "meta/game-start.json",
                        "execution_mode": "orchestrator",
                    }
                }
            ),
            encoding="utf-8",
        )
        write_active_agent(tmp_path, "town-agent", reason="stale hint", exit_condition="leave town", updated_by="narrator")

        narrator_adapter = _TextAdapter()
        with (
            patch("neonrp.core.conversation.get_adapter_from_config", return_value=narrator_adapter),
            patch("neonrp.core.conversation._dispatch_sub_agent") as dispatch_mock,
        ):
            result = run_conversation_turn(
                tmp_path,
                "narrator",
                [Message(role="user", content="Just narrate the room")],
                mode="play",
            )

        assert result.success is True
        assert result.assistant_speaker == "narrator"
        dispatch_mock.assert_not_called()

    def test_orchestrator_mode_allows_specialist_to_call_one_more_specialist(self, tmp_path: Path):
        narrator_json = json.dumps(
            {
                "id": "narrator",
                "name": "Narrator",
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        )
        _init_project(tmp_path, agent_json=narrator_json)
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(
                {
                    "router": {
                        "agent_id": "narrator",
                        "state_file": "meta/active-agent.json",
                        "startup_file": "meta/game-start.json",
                        "execution_mode": "orchestrator",
                    }
                }
            ),
            encoding="utf-8",
        )

        for agent_id in ("town-agent", "combat-referee"):
            agent_dir = tmp_path / "agents" / agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "agent.json").write_text(
                json.dumps(
                    {
                        "id": agent_id,
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

        adapters = [
            _TaskToAdapter("town-agent", "Narrator final response."),
            _TaskToAdapter("combat-referee", "Town specialist summary."),
            _TextAdapter(),
        ]
        with patch("neonrp.core.conversation.get_adapter_from_config", side_effect=adapters):
            result = run_conversation_turn(
                tmp_path,
                "narrator",
                [Message(role="user", content="Attack the goblin in the tavern")],
                mode="play",
            )

        assert result.success is True
        assert result.assistant_speaker == "narrator"

    def test_orchestrator_mode_blocks_fourth_agent_layer(self, tmp_path: Path):
        narrator_json = json.dumps(
            {
                "id": "narrator",
                "name": "Narrator",
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        )
        _init_project(tmp_path, agent_json=narrator_json)
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(
                {
                    "router": {
                        "agent_id": "narrator",
                        "state_file": "meta/active-agent.json",
                        "startup_file": "meta/game-start.json",
                        "execution_mode": "orchestrator",
                    }
                }
            ),
            encoding="utf-8",
        )

        for agent_id in ("town-agent", "combat-referee", "healer-agent"):
            agent_dir = tmp_path / "agents" / agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            (agent_dir / "agent.json").write_text(
                json.dumps(
                    {
                        "id": agent_id,
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

        class _Depth2TaskAdapter:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    tool = ToolCall(id="task-healer", name="task", arguments={"agent_id": "healer-agent", "prompt": "heal now"})
                    return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool]), tool_calls=[tool], finished=False)
                return LLMTurnResult(message=Message(role="assistant", content="combat result"), finished=True)

        adapters = [
            _TaskToAdapter("town-agent", "Narrator final response."),
            _TaskToAdapter("combat-referee", "Town specialist summary."),
            _Depth2TaskAdapter(),
        ]
        with patch("neonrp.core.conversation.get_adapter_from_config", side_effect=adapters):
            result = run_conversation_turn(
                tmp_path,
                "narrator",
                [Message(role="user", content="Start a very deep chain")],
                mode="play",
            )

        assert result.success is True
        assert result.assistant_speaker == "narrator"

    def test_orchestrator_mode_falls_back_to_builtin_orchestrator_when_missing(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        shutil.rmtree(tmp_path / "agents" / "test-agent")
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(
                {
                    "router": {
                        "agent_id": "narrator",
                        "state_file": "meta/active-agent.json",
                        "startup_file": "meta/game-start.json",
                        "execution_mode": "orchestrator",
                    }
                }
            ),
            encoding="utf-8",
        )

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "narrator",
                [Message(role="user", content="Begin adventure")],
                mode="play",
            )

        assert result.success is True
        assert result.assistant_speaker == "narrator"

    def test_orchestrator_mode_router_can_see_ask_user_tool(self, tmp_path: Path):
        narrator_json = json.dumps(
            {
                "id": "narrator",
                "name": "Narrator",
                "permissions": {
                    "read_globs": ["**"],
                    "deny_globs": [],
                    "write_globs": ["**"],
                    "direct_write_globs": ["**"],
                },
            }
        )
        _init_project(tmp_path, agent_json=narrator_json)
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.parent.mkdir(parents=True, exist_ok=True)
        contract_path.write_text(
            json.dumps(
                {
                    "router": {
                        "agent_id": "narrator",
                        "state_file": "meta/active-agent.json",
                        "startup_file": "meta/game-start.json",
                        "execution_mode": "orchestrator",
                    }
                }
            ),
            encoding="utf-8",
        )

        adapter = _CaptureSystemPromptAdapter()
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                tmp_path,
                "narrator",
                [Message(role="user", content="开始游戏")],
                mode="play",
            )

        assert result.success is True
        assert "ask_user" in adapter.system_prompt

    def test_max_turns_exceeded(self, tmp_path: Path):
        # Hitting the tool-round cap is a graceful safety stop, not a failure:
        # the turn ends cleanly (no error), flagged via max_turns_reached.
        _init_project(tmp_path, agent_json=_default_agent_json())
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_LoopToolAdapter()):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], max_turns=1)
        assert result.success is True
        assert result.max_turns_reached is True
        assert "exceeded max turns" not in (result.error or "")

    def test_repeated_identical_readonly_tool_calls_abort_loop_early(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        (tmp_path / "game" / "meta").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "meta" / "active-agent.json").write_text(
            '{"active_agent":"narrator"}',
            encoding="utf-8",
        )
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_RepeatedReadFileAdapter()):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")], max_turns=12)
        assert result.success is False
        assert "repeated identical read-only tool calls" in (result.error or "")

    def test_streaming_branch_is_used_when_chunk_callback_provided(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        chunks: list[str] = []
        thinking: list[str] = []

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_StreamAdapter()):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_chunk=chunks.append,
                on_thinking=thinking.append,
            )
        assert result.success is True
        assert chunks == ["A", "B"]
        assert thinking == ["T"]
        assert result.usage.get("total_tokens") == 3
        assert result.assistant_message == "AB"


class TestConversationSessionAndHelpers:
    def test_recent_files_deduplicates_and_get_messages_returns_list(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        session = ConversationSession(tmp_path, "test-agent")
        with patch(
            "neonrp.core.conversation.run_conversation_turn",
            return_value=ConversationTurnResult(
                success=True,
                run_id="r1",
                turns_used=1,
                files_modified=["game/a.json", "game/a.json"],
            ),
        ):
            session.send("hello")

        assert session.recent_files == ["game/a.json"]
        assert session.get_messages() == session.messages

    def test_router_selects_explicit_location_mapping_before_directory_fallback(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        contract_path = tmp_path / ".neonrp" / "runtime_contract.json"
        contract_path.write_text(
            json.dumps(
                {
                    "data_dir": "game",
                    "router": {"agent_id": "narrator", "state_file": "meta/active-agent.json", "startup_file": "meta/game-start.json"},
                    "routing": {
                        "location_source": {"entity_id": "player", "field": "location"},
                        "domain_agent_map": {
                            "town": "town-agent",
                            "location": "dungeon-agent",
                        },
                        "fallback_agent": "narrator",
                    },
                }
            ),
            encoding="utf-8",
        )
        town_dir = tmp_path / "agents" / "town-agent"
        dungeon_dir = tmp_path / "agents" / "dungeon-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        dungeon_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(json.dumps({"id": "town-agent", "sticky_domain_kinds": ["town"]}), encoding="utf-8")
        (dungeon_dir / "agent.json").write_text(
            json.dumps({"id": "dungeon-agent", "sticky_domain_kinds": ["location", "dungeon"]}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "player").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "location").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "player" / "player.json").write_text(
            json.dumps({"id": "player", "kind": "player", "name": "Player", "location": "forest-path"}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "location" / "forest-path.json").write_text(
            json.dumps({"id": "forest-path", "kind": "location", "name": "Forest Path"}),
            encoding="utf-8",
        )

        selected = _select_router_target_agent(tmp_path, "game", "narrator")

        assert selected == "dungeon-agent"

    def test_select_router_target_agent_excludes_orchestrator_alias_from_specialists(self, tmp_path: Path):
        (tmp_path / "agents").mkdir(parents=True, exist_ok=True)
        for agent_id in ("narrator", "orchestrator", "town-agent"):
            agent_dir = tmp_path / "agents" / agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            payload = {"id": agent_id}
            if agent_id == "town-agent":
                payload["sticky_domain_kinds"] = ["town"]
            (agent_dir / "agent.json").write_text(json.dumps(payload), encoding="utf-8")

        (tmp_path / "game" / "player").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "player" / "player.json").write_text(
            json.dumps({"id": "player", "kind": "player", "name": "Player", "location": "unknown-place"}),
            encoding="utf-8",
        )

        selected = _select_router_target_agent(tmp_path, "game", "narrator")

        assert selected == "town-agent"

    def test_set_mode_rejects_invalid_value(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        session = ConversationSession(tmp_path, "test-agent")
        with pytest.raises(ValueError):
            session.set_mode("invalid")  # type: ignore[arg-type]

    def test_current_branch_defaults_to_main_without_or_with_broken_manifest(self, tmp_path: Path):
        (tmp_path / ".neonrp").mkdir(parents=True, exist_ok=True)
        session_no_manifest = ConversationSession(tmp_path, "test-agent")
        assert session_no_manifest.branch == "main"

        _init_project(tmp_path, agent_json=_default_agent_json(), manifest_json="{bad json")
        session_bad_manifest = ConversationSession(tmp_path, "test-agent")
        assert session_bad_manifest.branch == "main"

    def test_chat_stream_collects_error_and_exception_paths(self):
        result_error = _chat_stream(_StreamErrorAdapter(), [], [], None, None)
        assert result_error.error == "stream fail"
        assert result_error.message is not None
        assert result_error.message.content == "partial"
        assert result_error.retryable is False

        result_retryable = _chat_stream(_RetryableStreamErrorAdapter(), [], [], None, None)
        assert result_retryable.error == "Network connection lost."
        assert result_retryable.retryable is True

        result_exception = _chat_stream(_ExplodingStreamAdapter(), [], [], None, None)
        assert "stream exploded" in (result_exception.error or "")
        assert result_exception.finished is True

    def test_chat_stream_returns_raw_chunks_and_final_message(self):
        streamed: list[str] = []
        result = _chat_stream(_StreamAdapter(), [], [], streamed.append, None)
        assert "".join(streamed) == "AB"
        assert result.message is not None
        assert (result.message.content or "") == "AB"

    def test_truncate_messages_for_budget_keeps_system_and_last_two(self):
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="x" * 300),
            Message(role="assistant", content="y" * 300),
            Message(role="user", content="z" * 300),
        ]
        _truncate_messages_for_budget(messages, max_context_chars=400)
        assert len(messages) == 3
        assert messages[0].role == "system"

    def test_todo_and_skill_handlers_error_paths(self):
        todo_error = json.loads(_handle_todo_tool(TodoManager(), {"items": "not-list"}))
        assert todo_error["status"] == "error"

        class _Loader:
            def get_content(self, name: str):
                return None

        skill_empty = json.loads(_handle_skill_tool(_Loader(), {"skill": "  "}))
        assert skill_empty["status"] == "error"

        skill_missing = json.loads(_handle_skill_tool(_Loader(), {"skill": "missing"}))
        assert skill_missing["status"] == "error"

    def test_track_modified_files_and_merge_usage_edge_cases(self):
        files: list[str] = []
        _track_modified_files("write_file", "{bad json", files)
        assert files == []

        _track_modified_files("write_file", json.dumps({"status": "error"}), files)
        assert files == []

        _track_modified_files(
            "write_file",
            json.dumps({"status": "success", "data": {"path": "game/hero.json"}}),
            files,
        )
        _track_modified_files(
            "import_sillytavern_card",
            json.dumps({"status": "success", "data": {"path": "game/character/august.json"}}),
            files,
        )
        _track_modified_files(
            "ensure_playable_scaffold",
            json.dumps(
                {
                    "status": "success",
                    "data": {
                        "path": "game/meta/active-agent.json",
                        "files": ["agents/narrator/agent.json", ".neonrp/runtime_contract.json"],
                    },
                }
            ),
            files,
        )
        assert files == [
            "game/hero.json",
            "game/character/august.json",
            "agents/narrator/agent.json",
            ".neonrp/runtime_contract.json",
            "game/meta/active-agent.json",
        ]

        usage = {"prompt_tokens": 10, "model": "a"}
        _merge_usage(usage, {"prompt_tokens": 5, "model": "b"})
        assert usage["prompt_tokens"] == 15
        assert usage["model"] == "b"

    def test_finalize_turn_rebases_on_moved_head(self, tmp_path: Path):
        """Mid-turn applies (e.g. a sub-agent's submit_proposal) advance the
        head while the turn runs — the engine mandates that workflow, so the
        journal append REBASES onto the fresh head instead of failing the
        finished turn (the writes already landed; nothing to roll back)."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        manifest = Manifest(**json.loads(get_manifest_path(tmp_path).read_text(encoding="utf-8")))
        manifest.branches["main"].head_event = 3
        get_manifest_path(tmp_path).write_text(json.dumps(manifest.model_dump(), default=str), encoding="utf-8")

        result = _finalize_turn(
            root=tmp_path,
            run_id="r",
            branch="main",
            base_head_event=1,
            mode="build",
            agent_id="test-agent",
            assistant_chunks=["done"],
            files_modified=["game/hero.json"],
            tool_calls_made=["write_file"],
            turns_used=1,
            todo_manager=TodoManager(),
            usage={},
            proposal=None,
        )
        assert result.success is True
        # journal event appended at fresh head + 1
        reread = Manifest(**json.loads(get_manifest_path(tmp_path).read_text(encoding="utf-8")))
        assert reread.branches["main"].head_event == 4

    def test_dispatch_sub_agent_forwards_stream_callbacks_with_subagent_tags(self, tmp_path: Path):
        """Nested sub-agent output should stream through with explicit speaker tags."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        captured: dict[str, object] = {}
        cancel_event = threading.Event()
        parent_chunks: list[str] = []
        parent_thinking: list[str] = []
        parent_tool_uses: list[tuple[str, dict[str, object]]] = []
        parent_tool_results: list[tuple[str, dict[str, object], str]] = []

        def _fake_nested_run(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ConversationTurnResult(
                success=True,
                run_id="sub-1",
                assistant_message="sub done",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "test-agent", "prompt": "hello"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_chunk=parent_chunks.append,
                on_thinking=parent_thinking.append,
                on_tool_use=lambda name, args: parent_tool_uses.append((name, args)),
                on_tool_result=lambda name, args, result: parent_tool_results.append((name, args, result)),
                on_ask_user=None,
                cancel_event=cancel_event,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert payload["data"]["assistant_text"] == "sub done"
        assert captured.get("max_turns") == 42
        assert captured.get("on_ask_user") is None
        assert captured.get("cancel_event") is cancel_event
        assert captured.get("disabled_tools") == {"ask_user"}
        on_chunk = captured.get("on_chunk")
        on_thinking = captured.get("on_thinking")
        on_tool_use = captured.get("on_tool_use")
        on_tool_result = captured.get("on_tool_result")
        assert callable(on_chunk)
        assert callable(on_thinking)
        assert callable(on_tool_use)
        assert callable(on_tool_result)

        on_chunk("hello")  # type: ignore[misc]
        on_thinking("plan")  # type: ignore[misc]
        on_tool_use("read_file", {"path": "game/a.json"})  # type: ignore[misc]
        on_tool_result("read_file", {"path": "game/a.json"}, '{"status":"success"}')  # type: ignore[misc]

        assert parent_chunks == ["[[subagent:test-agent]]hello"]
        assert parent_thinking == ["[[subagent:test-agent]]plan"]
        assert parent_tool_uses == [("[[subagent:test-agent]]read_file", {"path": "game/a.json"})]
        assert parent_tool_results == [
            ("[[subagent:test-agent]]read_file", {"path": "game/a.json"}, '{"status":"success"}')
        ]

    def test_dispatch_sub_agent_injects_parent_language_context(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        captured: dict[str, object] = {}

        def _fake_nested_run(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ConversationTurnResult(
                success=True,
                run_id="sub-lang-1",
                assistant_message="处理完成",
                turns_used=1,
            )

        parent_messages = [
            Message(role="system", content="system"),
            Message(role="user", content="请先用中文告诉我这个任务要去哪接。"),
        ]

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "test-agent", "prompt": "Handle the quest handoff."},
                root=tmp_path,
                mode="build",
                max_turns=8,
                parent_messages=parent_messages,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        nested_messages = captured.get("messages")
        assert isinstance(nested_messages, list)
        assert nested_messages
        delegated_prompt = nested_messages[0].content
        assert delegated_prompt is not None
        assert "Parent conversation language context" in delegated_prompt
        assert "请先用中文告诉我这个任务要去哪接。" in delegated_prompt
        assert "Handle the quest handoff." in delegated_prompt

    def test_dispatch_sub_agent_sticky_allows_ask_user_when_callback_provided(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps({"id": "town-agent", "name": "Town Agent", "delegation_mode": "sticky"}),
            encoding="utf-8",
        )
        captured: dict[str, object] = {}

        def _fake_nested_run(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ConversationTurnResult(
                success=True,
                run_id="sub-sticky-ask",
                assistant_message="ok",
                turns_used=1,
            )

        on_ask_user = lambda _q, _opts: "A"  # noqa: E731
        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "town-agent", "prompt": "hello"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=on_ask_user,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert captured.get("on_ask_user") is on_ask_user
        assert captured.get("disabled_tools") is None

    def test_dispatch_sub_agent_ignores_agent_level_max_task_turns(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps(
                {
                    "id": "town-agent",
                    "name": "Town Agent",
                    "delegation_mode": "sticky",
                    "max_task_turns": 1,
                }
            ),
            encoding="utf-8",
        )
        captured: dict[str, object] = {}

        def _fake_nested_run(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ConversationTurnResult(
                success=True,
                run_id="sub-sticky-max-turns",
                assistant_message="ok",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "town-agent", "prompt": "hello"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert captured.get("max_turns") == 42

    def test_dispatch_sub_agent_sticky_requires_ask_user_tool_when_callback_provided(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps(
                {
                    "id": "town-agent",
                    "name": "Town Agent",
                    "delegation_mode": "sticky",
                    "tools": ["read_file", "edit_file"],
                }
            ),
            encoding="utf-8",
        )
        on_ask_user = lambda _q, _opts: "A"  # noqa: E731
        result_json = _dispatch_sub_agent(
            task_data={"agent_id": "town-agent", "prompt": "hello"},
            root=tmp_path,
            mode="build",
            max_turns=42,
            on_ask_user=on_ask_user,
        )

        payload = json.loads(result_json)
        assert payload["status"] == "error"
        assert "sticky but cannot call ask_user" in payload["error"]
        assert payload["data"]["required_tool"] == "ask_user"

    def test_dispatch_sub_agent_injects_context_pack_registry_and_snapshots(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        (tmp_path / "game" / "player").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "town").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "npc").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "meta").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "player" / "player.json").write_text(
            json.dumps(
                {
                    "id": "player",
                    "kind": "player",
                    "name": "Player",
                    "location": "start-town",
                    "inventory": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (tmp_path / "game" / "town" / "start-town.json").write_text(
            json.dumps(
                {
                    "id": "start-town",
                    "kind": "town",
                    "name": "Start Town",
                    "npcs": ["old-sage"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (tmp_path / "game" / "npc" / "old-sage.json").write_text(
            json.dumps(
                {"id": "old-sage", "kind": "npc", "name": "Old Sage"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (tmp_path / "game" / "meta" / "active-agent.json").write_text(
            json.dumps(
                {"id": "active-agent", "kind": "meta", "name": "Active Agent", "active_agent": "narrator"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        captured: dict[str, object] = {}

        def _fake_nested_run(**kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return ConversationTurnResult(
                success=True,
                run_id="sub-ctx",
                assistant_message="ok",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "test-agent", "prompt": "talk to old-sage in start-town"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        messages = captured.get("messages")
        assert isinstance(messages, list)
        assert messages
        first = messages[0]
        assert isinstance(first, Message)
        prompt = first.content or ""
        assert "Context Pack (preloaded canonical paths + entity snapshots)" in prompt
        assert "- player -> game/player/player.json" in prompt
        assert "- start-town -> game/town/start-town.json" in prompt
        assert "### old-sage (npc)" in prompt

    def test_dispatch_sub_agent_returns_cancelled_when_nested_run_is_cancelled(self, tmp_path: Path):
        """Cancelled nested runs should surface as cancelled task results."""
        _init_project(tmp_path, agent_json=_default_agent_json())

        def _fake_nested_run(**_kwargs):  # type: ignore[no-untyped-def]
            return ConversationTurnResult(
                success=True,
                run_id="sub-cancel",
                assistant_message="",
                turns_used=1,
                cancelled=True,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "test-agent", "prompt": "hello"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "cancelled"
        assert payload["data"]["agent_id"] == "test-agent"

    def test_dispatch_sub_agent_one_shot_does_not_update_active_agent_state(self, tmp_path: Path):
        """One-shot delegation should not persist active-agent lock."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        scout_dir = tmp_path / "agents" / "scout-agent"
        scout_dir.mkdir(parents=True, exist_ok=True)
        (scout_dir / "agent.json").write_text(
            json.dumps({"id": "scout-agent", "name": "Scout Agent", "delegation_mode": "one-shot"}),
            encoding="utf-8",
        )

        def _fake_nested_run(**_kwargs):  # type: ignore[no-untyped-def]
            return ConversationTurnResult(
                success=True,
                run_id="sub-ok",
                assistant_message="ok",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "scout-agent", "prompt": "hello"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert get_active_agent_id(tmp_path) == "narrator"

    def test_dispatch_sub_agent_sticky_respects_agent_requested_exit(self, tmp_path: Path):
        """Sticky agents may explicitly release lock; parent should not overwrite it."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps({"id": "town-agent", "name": "Town Agent", "delegation_mode": "sticky"}),
            encoding="utf-8",
        )

        def _fake_nested_run(**_kwargs):  # type: ignore[no-untyped-def]
            write_active_agent(
                tmp_path,
                "narrator",
                reason="left domain",
                exit_condition="",
                updated_by="town-agent",
            )
            return ConversationTurnResult(
                success=True,
                run_id="sub-ok",
                assistant_message="transition",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "town-agent", "prompt": "leave town"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert get_active_agent_id(tmp_path) == "narrator"

    def test_dispatch_sub_agent_sticky_explicit_handoff_field_releases_lock(self, tmp_path: Path):
        """Sticky agent can release lock via explicit handoff tool result field."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps({"id": "town-agent", "name": "Town Agent", "delegation_mode": "sticky"}),
            encoding="utf-8",
        )

        def _fake_nested_run(**_kwargs):  # type: ignore[no-untyped-def]
            return ConversationTurnResult(
                success=True,
                run_id="sub-ok",
                assistant_message="cross-domain done",
                handoff_to="narrator",
                turns_used=1,
            )

        with patch("neonrp.core.conversation.run_conversation_turn", side_effect=_fake_nested_run):
            result_json = _dispatch_sub_agent(
                task_data={"agent_id": "town-agent", "prompt": "leave town"},
                root=tmp_path,
                mode="build",
                max_turns=42,
                on_ask_user=None,
            )

        payload = json.loads(result_json)
        assert payload["status"] == "success"
        assert get_active_agent_id(tmp_path) == "narrator"
        assert payload["data"]["assistant_text"] == "cross-domain done"
        assert payload["data"]["handoff_to"] == "narrator"

    def test_should_release_active_agent_lock_on_sticky_domain_mismatch(self, tmp_path: Path):
        """Sticky lock should auto-release when player location kind leaves configured domain."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        town_dir = tmp_path / "agents" / "town-agent"
        town_dir.mkdir(parents=True, exist_ok=True)
        (town_dir / "agent.json").write_text(
            json.dumps(
                {
                    "id": "town-agent",
                    "name": "Town Agent",
                    "delegation_mode": "sticky",
                    "sticky_domain_kinds": ["town"],
                }
            ),
            encoding="utf-8",
        )

        (tmp_path / "game" / "player").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "location").mkdir(parents=True, exist_ok=True)
        (tmp_path / "game" / "player" / "player.json").write_text(
            json.dumps({"id": "player", "kind": "player", "name": "Player", "location": "forest-path"}),
            encoding="utf-8",
        )
        (tmp_path / "game" / "location" / "forest-path.json").write_text(
            json.dumps({"id": "forest-path", "kind": "location", "name": "Forest Path"}),
            encoding="utf-8",
        )

        should_release = _should_release_active_agent_lock(
            tmp_path,
            "game",
            "继续前进",
            "town-agent",
            narrator_agent_id="narrator",
        )
        assert should_release is True


class _RetryableFailThenTextAdapter:
    """Adapter that fails with a retryable error on first call, then succeeds."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return LLMTurnResult(error="Bad Request: invalid tool_use", finished=True, retryable=True)
        return LLMTurnResult(message=Message(role="assistant", content="recovered"), finished=True)


class _PermanentRetryableFailAdapter:
    """Adapter that always fails with retryable errors."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return LLMTurnResult(error="Bad Request: always broken", finished=True, retryable=True)


class _RetryableStreamFailThenTextAdapter:
    """Adapter that fails once in streaming mode, then succeeds."""

    def __init__(self):
        self.calls = 0

    def chat_stream(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            yield StreamChunk(error="OpenAI API streaming error: Network connection lost.", finished=True, retryable=True)
            return
        yield StreamChunk(delta="ok", finished=True)


class TestTrimBrokenTail:
    """Tests for _trim_broken_tail helper."""

    def test_trims_trailing_tool_and_assistant_messages(self):
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(role="assistant", content="let me check",
                    tool_calls=[ToolCall(id="t1", name="read_context", arguments={"path": "x"})]),
            Message(role="tool", content='{"status": "error"}', tool_call_id="t1", name="read_context"),
        ]
        _trim_broken_tail(messages)
        assert len(messages) == 2
        assert messages[-1].role == "user"

    def test_trims_multiple_tool_results(self):
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
            Message(role="assistant", content=None,
                    tool_calls=[
                        ToolCall(id="t1", name="read_context", arguments={"path": "a"}),
                        ToolCall(id="t2", name="glob", arguments={"pattern": "*.json"}),
                    ]),
            Message(role="tool", content='{"status": "success"}', tool_call_id="t1", name="read_context"),
            Message(role="tool", content='{"status": "success"}', tool_call_id="t2", name="glob"),
        ]
        _trim_broken_tail(messages)
        assert len(messages) == 2
        assert messages[-1].role == "user"

    def test_preserves_system_message_only(self):
        messages = [
            Message(role="system", content="sys"),
            Message(role="assistant", content="bad"),
        ]
        _trim_broken_tail(messages)
        assert len(messages) == 1
        assert messages[0].role == "system"

    def test_no_op_when_tail_is_user_message(self):
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hello"),
        ]
        _trim_broken_tail(messages)
        assert len(messages) == 2


class TestConversationRetryOnApiError:
    """Tests for conversation loop retry on retryable API errors."""

    @patch("neonrp.core.conversation.time.sleep")
    def test_retryable_error_recovers_on_second_attempt(self, _mock_sleep, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        adapter = _RetryableFailThenTextAdapter()
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is True
        assert result.assistant_message == "recovered"
        assert adapter.calls == 2

    @patch("neonrp.core.conversation.time.sleep")
    def test_permanent_retryable_error_terminates_after_max_retries(self, mock_sleep, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        adapter = _PermanentRetryableFailAdapter()
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "LLM call failed" in (result.error or "")
        # Should have tried original + 4 retries with fixed delays.
        assert adapter.calls == 5
        assert [c.args[0] for c in mock_sleep.call_args_list] == [2, 7, 15, 30]

    @patch("neonrp.core.conversation.time.sleep")
    def test_stream_retryable_error_recovers_on_second_attempt(self, mock_sleep, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        adapter = _RetryableStreamFailThenTextAdapter()
        chunks: list[str] = []
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_chunk=chunks.append,
            )
        assert result.success is True
        assert result.assistant_message == "ok"
        assert adapter.calls == 2
        assert [c.args[0] for c in mock_sleep.call_args_list] == [2]

    def test_non_retryable_error_terminates_immediately(self, tmp_path: Path):
        _init_project(tmp_path, agent_json=_default_agent_json())
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_FailAdapter()):
            result = run_conversation_turn(tmp_path, "test-agent", [Message(role="user", content="x")])
        assert result.success is False
        assert "LLM call failed on turn 1" in (result.error or "")


# --- Tool schemas for _normalize_tool_call tests ---
_SAMPLE_SCHEMAS = [
    {
        "name": "glob",
        "parameters": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        },
    },
]


class TestNormalizeToolCall:
    """Tests for _normalize_tool_call fixing malformed tool names from non-Anthropic models."""

    def test_glob_with_args_in_name(self):
        tc = ToolCall(id="t1", name='glob("**/*.json")', arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "**/*.json"}

    def test_read_file_with_args_in_name(self):
        tc = ToolCall(id="t2", name='read_file("game/hero.json")', arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "game/hero.json"}

    def test_single_quotes(self):
        tc = ToolCall(id="t3", name="glob('*.md')", arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "*.md"}

    def test_no_quotes(self):
        tc = ToolCall(id="t4", name="glob(world)", arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "world"}

    def test_preserves_existing_arguments(self):
        tc = ToolCall(id="t5", name='glob("**/*.json")', arguments={"path": "world"})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "**/*.json", "path": "world"}

    def test_existing_first_param_not_overwritten(self):
        tc = ToolCall(id="t6", name='glob("**/*.json")', arguments={"pattern": "*.md"})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "*.md"}  # keep original

    def test_clean_name_unchanged(self):
        tc = ToolCall(id="t7", name="glob", arguments={"pattern": "*.json"})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "glob"
        assert tc.arguments == {"pattern": "*.json"}

    def test_unknown_tool_in_parens_still_extracts_name(self):
        tc = ToolCall(id="t8", name='unknown_tool("arg")', arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "unknown_tool"
        # No schema found, so no param merging, but name is still cleaned
        assert tc.arguments == {}

    def test_empty_parens(self):
        tc = ToolCall(id="t9", name="list_entities()", arguments={})
        _normalize_tool_call(tc, _SAMPLE_SCHEMAS)
        assert tc.name == "list_entities"
        assert tc.arguments == {}


class _SlowStreamAdapter:
    """Adapter that yields multiple chunks; a cancel_event can be set externally."""

    def chat_stream(self, messages, tools=None):
        for i in range(5):
            yield StreamChunk(delta=f"chunk{i} ")
        yield StreamChunk(delta="end", finished=True, usage={"total_tokens": 10})


class _CancelDuringStreamAdapter:
    """Adapter whose chat_stream sets a cancel_event after the first chunk."""

    def __init__(self, cancel_event: threading.Event):
        self._cancel_event = cancel_event

    def chat_stream(self, messages, tools=None):
        yield StreamChunk(delta="first ")
        self._cancel_event.set()  # simulate ESC press after first chunk
        yield StreamChunk(delta="second ")
        yield StreamChunk(delta="third ", finished=True)


class TestChatStreamCancelEvent:
    """Tests that _chat_stream respects cancel_event during streaming."""

    def test_cancel_event_stops_stream_early(self):
        cancel_event = threading.Event()
        adapter = _CancelDuringStreamAdapter(cancel_event)
        chunks: list[str] = []
        result = _chat_stream(adapter, [], [], chunks.append, None, cancel_event)
        # Should have received only the first chunk; the cancel fires before the second
        # chunk is processed.
        assert result.message is not None
        assert "first" in (result.message.content or "")
        assert "third" not in (result.message.content or "")

    def test_no_cancel_event_streams_all_chunks(self):
        adapter = _SlowStreamAdapter()
        chunks: list[str] = []
        result = _chat_stream(adapter, [], [], chunks.append, None, None)
        assert result.message is not None
        assert "end" in (result.message.content or "")
        assert len(chunks) == 6  # 5 + "end"

    def test_run_conversation_turn_cancel_during_streaming(self, tmp_path: Path):
        """Integration: run_conversation_turn returns cancelled when cancel fires mid-stream."""
        _init_project(tmp_path, agent_json=_default_agent_json())
        cancel_event = threading.Event()
        adapter = _CancelDuringStreamAdapter(cancel_event)
        chunks: list[str] = []

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                tmp_path,
                "test-agent",
                [Message(role="user", content="x")],
                on_chunk=chunks.append,
                cancel_event=cancel_event,
            )
        assert result.cancelled is True
        assert result.success is True
