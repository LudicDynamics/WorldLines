"""Tests for M9 conversation engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from neonrp.core.active_agent import NARRATOR_AGENT, get_active_agent_id, write_active_agent
from neonrp.core.conversation import (
    ASK_USER_CANCELLED_RESPONSE,
    TODO_TOOL_SCHEMA,
    ConversationSession,
    ConversationTurnResult,
    run_conversation_turn,
)
from neonrp.core.event_log import read_events
from neonrp.core.llm import LLMTurnResult, Message, ToolCall
from neonrp.core.manifest import Manifest
from neonrp.core.paths import get_manifest_path
from neonrp.core.session import read_session
from neonrp.core.todo import TodoManager


def _setup_project(tmp_path: Path) -> Path:
    neonrp_dir = tmp_path / ".neonrp"
    (neonrp_dir / "events").mkdir(parents=True)
    (neonrp_dir / "sessions").mkdir(parents=True)
    (tmp_path / "game").mkdir(parents=True)

    manifest = Manifest()
    manifest.branches["main"].head_event = -1
    (neonrp_dir / "manifest.json").write_text(json.dumps(manifest.model_dump(), default=str), encoding="utf-8")
    (neonrp_dir / "config.json").write_text(
        json.dumps(
            {
                "llm": {"provider": "stub", "max_context_chars": 100000},
                "tui": {"session_max_turns": 50},
            }
        ),
        encoding="utf-8",
    )

    agent_dir = tmp_path / "agents" / "test-agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.json").write_text(
        json.dumps(
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
        ),
        encoding="utf-8",
    )
    return tmp_path


class _WriteThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool_call = ToolCall(
                id="tc1",
                name="write_file",
                arguments={
                    "path": "game/character/hero.json",
                    "content": '{"id":"hero","kind":"character","name":"Hero"}',
                },
            )
            return LLMTurnResult(
                message=Message(role="assistant", tool_calls=[tool_call]),
                tool_calls=[tool_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="Done."), finished=True)


class _WriteProjectFileThenTextAdapter:
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            tool_call = ToolCall(
                id="tc_project_write",
                name="write_file",
                arguments={"path": self.target_path, "content": "hello"},
            )
            return LLMTurnResult(
                message=Message(role="assistant", tool_calls=[tool_call]),
                tool_calls=[tool_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="Done."), finished=True)


class _TextOnlyAdapter:
    def chat(self, messages, tools=None):
        return LLMTurnResult(message=Message(role="assistant", content="Narrative output."), finished=True)


class _SubmitProposalAdapter:
    def chat(self, messages, tools=None):
        tool_call = ToolCall(
            id="tc_proposal",
            name="submit_proposal",
            arguments={
                "proposal_version": "0.1",
                "run_id": "run_1",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "query": "sandbox",
                "ops": [],
            },
        )
        return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool_call]), tool_calls=[tool_call])


class _ToolCaptureSubmitProposalAdapter:
    def __init__(self):
        self.tools_seen = []

    def chat(self, messages, tools=None):
        self.tools_seen = list(tools or [])
        tool_call = ToolCall(
            id="tc_proposal",
            name="submit_proposal",
            arguments={
                "proposal_version": "0.1",
                "run_id": "run_tools",
                "agent_id": "test-agent",
                "branch": "main",
                "base_head_event": -1,
                "ops": [],
            },
        )
        return LLMTurnResult(message=Message(role="assistant", tool_calls=[tool_call]), tool_calls=[tool_call])


class _TodoSkillThenTextAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            todo_call = ToolCall(
                id="tc_todo",
                name="TodoWrite",
                arguments={
                    "todos": [
                        {"content": "Read", "status": "completed", "activeForm": "Reading files"},
                        {"content": "Write", "status": "in_progress", "activeForm": "Writing updates"},
                    ]
                },
            )
            skill_call = ToolCall(id="tc_skill", name="Skill", arguments={"skill": "combat"})
            return LLMTurnResult(
                message=Message(role="assistant", tool_calls=[todo_call, skill_call]),
                tool_calls=[todo_call, skill_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="Planned and loaded."), finished=True)


class _AskUserAdapter:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            ask_call = ToolCall(
                id="tc_ask",
                name="ask_user",
                arguments={"question": "Choose", "options": ["A", "B"]},
            )
            return LLMTurnResult(
                message=Message(role="assistant", tool_calls=[ask_call]),
                tool_calls=[ask_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="Acknowledged."), finished=True)


class _BadAskUserThenTextAdapter:
    """Adapter that emits malformed ask_user payload with control chars, then recovers."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            ask_call = ToolCall(
                id="tc_ask_bad",
                name="ask_user",
                arguments={
                    "questions": [
                        {
                            "question": "What should you do?\x7f",
                            "header": "Choice",
                            "options": [
                                {"label": "A", "description": "Option A"},
                                {"label": "B", "description": "Option B"},
                            ],
                            "multiSelect": False,
                        }
                    ]
                },
            )
            return LLMTurnResult(
                message=Message(role="assistant", tool_calls=[ask_call]),
                tool_calls=[ask_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="Recovered after invalid ask_user."), finished=True)


class _CaptureSystemPromptAdapter:
    def __init__(self):
        self.calls = 0
        self.system_prompt = ""

    def chat(self, messages, tools=None):
        self.calls += 1
        if messages and messages[0].role == "system":
            self.system_prompt = messages[0].content or ""
        return LLMTurnResult(message=Message(role="assistant", content="ok"), finished=True)


class _MultiTurnTextAdapter:
    """Adapter that emits assistant text across two turns with an intermediate tool call."""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            todo_call = ToolCall(
                id="tc_todo_join",
                name="TodoWrite",
                arguments={"todos": [{"content": "Plan", "status": "completed", "activeForm": "Planning"}]},
            )
            return LLMTurnResult(
                message=Message(role="assistant", content="Hello ", tool_calls=[todo_call]),
                tool_calls=[todo_call],
                finished=False,
            )
        return LLMTurnResult(message=Message(role="assistant", content="world"), finished=True)


class TestConversationTurn:
    def test_todo_tool_schema_uses_todos_key(self):
        """TodoWrite schema should use 'todos' as the parameter key (Claude Code convention)."""
        params = TODO_TOOL_SCHEMA.get("parameters", {})
        props = params.get("properties", {})
        assert "todos" in props, "Schema should use 'todos' key"
        assert props["todos"]["type"] == "array"
        item_schema = props["todos"].get("items", {})
        assert "content" in item_schema.get("properties", {}), "Item schema should define 'content'"
        assert "status" in item_schema.get("properties", {}), "Item schema should define 'status'"
        assert "activeForm" in item_schema.get("properties", {}), "Item schema should define 'activeForm'"

    def test_build_mode_write_creates_event_and_checkpoint(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        adapter = _WriteThenTextAdapter()
        tools_seen = []

        def on_tool_use(name: str, args: dict) -> None:
            tools_seen.append(name)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="Add hero")],
                mode="build",
                on_tool_use=on_tool_use,
            )

        assert result.success is True
        assert len(result.files_modified) == 1
        assert result.files_modified[0].replace("\\", "/").endswith("/game/character/hero.json")
        assert "write_file" in tools_seen
        assert (root / "game" / "character" / "hero.json").exists()

        manifest = Manifest(**json.loads(get_manifest_path(root).read_text(encoding="utf-8")))
        assert manifest.branches["main"].head_event == 0

        events = read_events(root, "main")
        assert len(events) == 1
        assert events[0].type == "build"
        assert len(events[0].payload["files_modified"]) == 1
        assert events[0].payload["files_modified"][0].replace("\\", "/").endswith("/game/character/hero.json")

        checkpoint_path = root / ".neonrp" / "checkpoints" / "main" / "-1"
        assert checkpoint_path.exists()

    def test_build_mode_allows_non_game_project_writes(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        adapter = _WriteProjectFileThenTextAdapter("src/demo.txt")
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="write demo file")],
                mode="build",
            )

        assert result.success is True
        assert (root / "src" / "demo.txt").read_text(encoding="utf-8") == "hello"

    def test_build_mode_allows_protected_directory_write(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        adapter = _WriteProjectFileThenTextAdapter(".neonrp/debug_note.txt")
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="write debug note")],
                mode="build",
            )

        assert result.success is True
        assert (root / ".neonrp" / "debug_note.txt").exists()

    def test_non_router_cannot_write_active_agent_by_default(self, tmp_path: Path):
        """Specialist agents should be denied from editing active-agent unless explicitly opted in."""
        root = _setup_project(tmp_path)
        active_agent_path = root / "game" / "meta" / "active-agent.json"
        active_agent_path.parent.mkdir(parents=True, exist_ok=True)
        original = '{"active_agent":"narrator","reason":"initial"}'
        active_agent_path.write_text(original, encoding="utf-8")

        adapter = _WriteProjectFileThenTextAdapter("game/meta/active-agent.json")
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="try to take routing ownership")],
                mode="play",
            )

        assert result.success is True
        assert active_agent_path.read_text(encoding="utf-8") == original
        assert not any(path.replace("\\", "/").endswith("/game/meta/active-agent.json") for path in result.files_modified)

    def test_sandbox_mode_requires_submit_proposal(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextOnlyAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="do sandbox")],
                mode="sandbox",
            )

        assert result.success is False
        assert "submit_proposal" in (result.error or "")

    def test_sandbox_mode_accepts_submit_proposal(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_SubmitProposalAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="sandbox turn")],
                mode="sandbox",
            )

        assert result.success is True
        assert result.proposal is not None
        manifest = Manifest(**json.loads(get_manifest_path(root).read_text(encoding="utf-8")))
        assert manifest.branches["main"].head_event == -1

    def test_sandbox_mode_hides_direct_write_tools(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        adapter = _ToolCaptureSubmitProposalAdapter()
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="sandbox tool list")],
                mode="sandbox",
            )

        assert result.success is True
        tool_names = {tool["name"] for tool in adapter.tools_seen}
        assert "submit_proposal" in tool_names
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names
        assert "ensure_playable_scaffold" not in tool_names

    def test_todowrite_and_skill_tools_update_state(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        (root / "skills" / "combat").mkdir(parents=True)
        (root / "skills" / "combat" / "SKILL.md").write_text(
            "---\nname: combat\ndescription: Combat skill\n---\nUse D20.", encoding="utf-8"
        )
        todo = TodoManager()

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TodoSkillThenTextAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="plan")],
                mode="build",
                todo_manager=todo,
            )

        assert result.success is True
        assert len(result.todo_snapshot) == 2
        assert result.todo_snapshot[1]["status"] == "in_progress"
        assert "TodoWrite" in result.tool_calls_made
        assert "Skill" in result.tool_calls_made

    def test_ask_user_callback_is_invoked(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        calls = []
        messages = [Message(role="user", content="ask me")]

        def on_ask_user(question: str, options: list[str]) -> str:
            calls.append((question, options))
            return "A"

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_AskUserAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=messages,
                mode="build",
                on_ask_user=on_ask_user,
            )

        assert result.success is True
        assert calls == [("Choose", ["A", "B"])]
        assert "ask_user" in result.tool_calls_made
        ask_tool_messages = [m for m in messages if m.role == "tool" and m.name == "ask_user"]
        assert len(ask_tool_messages) == 1
        payload = json.loads(ask_tool_messages[0].content or "{}")
        # Lean answers-only format (AskUserQuestion style)
        assert payload == {"answers": {"0": "A"}}

    def test_ask_user_cancel_stops_turn_without_error(self, tmp_path: Path):
        """If ask_user is canceled, the current run should stop cleanly without further LLM turns."""
        root = _setup_project(tmp_path)
        messages = [Message(role="user", content="ask me")]
        tool_results: list[str] = []

        def on_ask_user(_question: str, _options: list[str]) -> str:
            return ASK_USER_CANCELLED_RESPONSE

        def on_tool_result(_name: str, _args: dict[str, object], result_text: str) -> None:
            tool_results.append(result_text)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_AskUserAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=messages,
                mode="build",
                on_ask_user=on_ask_user,
                on_tool_result=on_tool_result,
            )

        assert result.success is True
        assert result.cancelled is True
        assert any('"status": "cancelled"' in payload for payload in tool_results)

    def test_ask_user_invalid_control_chars_returns_error_and_auto_recovers(self, tmp_path: Path):
        """Malformed ask_user payload should be rejected and model can recover next turn."""
        root = _setup_project(tmp_path)
        adapter = _BadAskUserThenTextAdapter()
        calls: list[tuple[str, list[str]]] = []
        tool_results: list[str] = []

        def on_ask_user(question: str, options: list[str]) -> str:
            calls.append((question, options))
            return "A"

        def on_tool_result(_name: str, _args: dict[str, object], result_text: str) -> None:
            tool_results.append(result_text)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="ask me")],
                mode="build",
                on_ask_user=on_ask_user,
                on_tool_result=on_tool_result,
            )

        assert result.success is True
        assert result.assistant_message == "Recovered after invalid ask_user."
        assert calls == []  # callback should not be invoked for invalid payload
        assert any("invalid control characters" in payload for payload in tool_results)

    def test_system_prompt_includes_agent_specific_system_md(self, tmp_path: Path):
        """Conversation system prompt should include agent-specific system.md content."""
        root = _setup_project(tmp_path)
        (root / "agents" / "test-agent" / "system.md").write_text(
            "SPECIAL_RULE: always delegate town operations via task().",
            encoding="utf-8",
        )
        agent_data = json.loads((root / "agents" / "test-agent" / "agent.json").read_text(encoding="utf-8"))
        agent_data["system_prompt"] = "system.md"
        (root / "agents" / "test-agent" / "agent.json").write_text(
            json.dumps(agent_data),
            encoding="utf-8",
        )
        adapter = _CaptureSystemPromptAdapter()

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="hello")],
                mode="build",
            )

        assert result.success is True
        assert "SPECIAL_RULE: always delegate town operations via task()." in adapter.system_prompt

    def test_system_prompt_treats_inline_text_with_slash_as_inline_policy(self, tmp_path: Path):
        """Inline policy text containing slash characters should not be treated as a missing file path."""
        root = _setup_project(tmp_path)
        agent_json_path = root / "agents" / "test-agent" / "agent.json"
        agent_data = json.loads(agent_json_path.read_text(encoding="utf-8"))
        agent_data["system_prompt"] = "你可以 buy/sell，但必须先 ask_user 再行动。"
        agent_json_path.write_text(json.dumps(agent_data), encoding="utf-8")
        adapter = _CaptureSystemPromptAdapter()

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=adapter):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="hello")],
                mode="build",
            )

        assert result.success is True
        assert "buy/sell" in adapter.system_prompt

    def test_multiturn_assistant_text_is_concatenated_without_forced_newlines(self, tmp_path: Path):
        """Assistant text from multiple turns should preserve inline flow."""
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_MultiTurnTextAdapter()):
            result = run_conversation_turn(
                root=root,
                agent_id="test-agent",
                messages=[Message(role="user", content="say hello world")],
                mode="build",
            )

        assert result.success is True
        assert result.assistant_message == "Hello world"


class TestConversationSession:
    def test_session_send_persists_and_resume_loads_history(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextOnlyAdapter()):
            session = ConversationSession(root=root, agent_id="test-agent", mode="build")
            first = session.send("hello")
            second = session.send("again")

        assert first.success is True
        assert second.success is True
        assert len([message for message in session.messages if message.role == "user"]) == 2
        assert len([message for message in session.messages if message.role == "assistant"]) == 2

        resumed = ConversationSession(root=root, agent_id="test-agent", mode="build")
        loaded = resumed.resume()
        assert loaded >= 4  # 2 user + 2 assistant (system prompt is rebuilt, not persisted)

    def test_session_single_turn_uses_consistent_run_id_for_all_persisted_messages(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextOnlyAdapter()):
            session = ConversationSession(root=root, agent_id="test-agent", mode="build")
            result = session.send("hello")
        entries = read_session(root, "main")
        run_ids = {entry.run_id for entry in entries if entry.run_id}
        assert result.success is True
        assert len(run_ids) == 1
        assert result.run_id in run_ids

    def test_session_resume_rebuilds_todo_state_from_tool_history(self, tmp_path: Path):
        root = _setup_project(tmp_path)

        class _TodoThenTextAdapter:
            def __init__(self):
                self.calls = 0

            def chat(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    todo_call = ToolCall(
                        id="tc_todo_resume",
                        name="TodoWrite",
                        arguments={"todos": [{"content": "Build scene", "status": "in_progress", "activeForm": "Building scene"}]},
                    )
                    return LLMTurnResult(
                        message=Message(role="assistant", tool_calls=[todo_call]),
                        tool_calls=[todo_call],
                        finished=False,
                    )
                return LLMTurnResult(message=Message(role="assistant", content="Done"), finished=True)

        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TodoThenTextAdapter()):
            session = ConversationSession(root=root, agent_id="test-agent", mode="build")
            result = session.send("plan tasks")

        assert result.success is True
        assert result.todo_snapshot == [{"content": "Build scene", "status": "in_progress", "activeForm": "Building scene"}]

        resumed = ConversationSession(root=root, agent_id="test-agent", mode="build")
        loaded = resumed.resume()
        assert loaded >= 3
        assert resumed.todo_manager.snapshot() == [
            {"content": "Build scene", "status": "in_progress", "activeForm": "Building scene"}
        ]

    def test_session_compact_keeps_system_and_recent_messages(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        session = ConversationSession(root=root, agent_id="test-agent", mode="build")
        # Manually populate messages: system + 15 user/assistant pairs
        session.messages = [Message(role="system", content="You are a narrator.")]
        for i in range(15):
            session.messages.append(Message(role="user", content=f"msg {i}"))
            session.messages.append(Message(role="assistant", content=f"reply {i}"))

        assert len(session.messages) == 31  # 1 system + 30 user/assistant

        removed = session.compact(keep_recent=10)

        assert removed == 20  # 31 - 10 - 1 system = 20
        assert session.messages[0].role == "system"
        assert session.messages[0].content == "You are a narrator."
        assert session.messages[1].role == "user"
        assert "compacted" in session.messages[1].content.lower()
        assert session.messages[2].role == "assistant"
        # Last 10 messages preserved
        assert len(session.messages) == 13  # system + compact marker pair + 10 recent
        assert session.messages[-1].content == "reply 14"

    def test_session_compact_noop_when_short(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        session = ConversationSession(root=root, agent_id="test-agent", mode="build")
        session.messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="hi"),
            Message(role="assistant", content="hello"),
        ]
        removed = session.compact(keep_recent=10)
        assert removed == 0
        assert len(session.messages) == 3  # unchanged

    def test_total_turns_and_total_usage_accumulate_across_sends(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextOnlyAdapter()):
            session = ConversationSession(root=root, agent_id="test-agent", mode="build")
            session.send("first")
            session.send("second")

        assert session.total_turns >= 2  # at least 1 turn per send
        # total_usage should be a dict (may be empty if stub doesn't report usage)
        assert isinstance(session.total_usage, dict)

    def test_session_turn_budget_falls_back_to_session_max_turns_when_tool_rounds_default(self, tmp_path: Path):
        """If user only customizes session_max_turns, reuse it as conversation turn budget."""
        root = _setup_project(tmp_path)
        (root / ".neonrp" / "config.json").write_text(
            json.dumps(
                {
                    "llm": {"provider": "stub", "max_context_chars": 100000},
                    "tui": {"session_max_turns": 100, "show_diff_preview": True},
                }
            ),
            encoding="utf-8",
        )

        session = ConversationSession(root=root, agent_id="test-agent", mode="build")
        assert session.max_turns == 100

    def test_session_clear_resets_memory_and_file(self, tmp_path: Path):
        root = _setup_project(tmp_path)
        with patch("neonrp.core.conversation.get_adapter_from_config", return_value=_TextOnlyAdapter()):
            session = ConversationSession(root=root, agent_id="test-agent", mode="build")
            session.send("hello")
            assert len(session.messages) >= 3
            session.clear()

        assert session.messages == []
        session_file = root / ".neonrp" / "sessions" / "main.jsonl"
        assert not session_file.exists()
