"""Tests for core/session.py - session persistence."""

from pathlib import Path

from neonrp.core.llm import Message, ToolCall
from neonrp.core.session import (
    SessionEntry,
    append_message,
    append_session_entry,
    append_user_query,
    append_assistant_response,
    clear_session,
    get_session_length,
    get_session_path,
    read_session,
    read_session_messages,
    session_exists,
    truncate_session,
)


class TestSessionEntry:
    """Tests for SessionEntry dataclass."""

    def test_to_dict_minimal(self):
        """Should serialize minimal entry."""
        entry = SessionEntry(timestamp="2024-01-01T00:00:00Z", role="user", content="Hello")
        d = entry.to_dict()
        assert d["timestamp"] == "2024-01-01T00:00:00Z"
        assert d["role"] == "user"
        assert d["content"] == "Hello"
        assert "tool_calls" not in d
        assert "run_id" not in d

    def test_to_dict_full(self):
        """Should serialize full entry."""
        entry = SessionEntry(
            timestamp="2024-01-01T00:00:00Z",
            role="assistant",
            content=None,
            tool_calls=[{"id": "call_1", "name": "read_file", "arguments": {}}],
            run_id="run-123",
        )
        d = entry.to_dict()
        assert d["role"] == "assistant"
        assert len(d["tool_calls"]) == 1
        assert d["run_id"] == "run-123"
        assert "content" not in d

    def test_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "timestamp": "2024-01-01T00:00:00Z",
            "role": "tool",
            "content": "result",
            "tool_call_id": "call_1",
            "name": "read_file",
        }
        entry = SessionEntry.from_dict(data)
        assert entry.role == "tool"
        assert entry.content == "result"
        assert entry.tool_call_id == "call_1"
        assert entry.name == "read_file"

    def test_from_message(self):
        """Should create from Message object."""
        msg = Message(role="user", content="Hello")
        entry = SessionEntry.from_message(msg, run_id="run-456")
        assert entry.role == "user"
        assert entry.content == "Hello"
        assert entry.run_id == "run-456"
        assert entry.timestamp != ""

    def test_from_message_with_tool_calls(self):
        """Should create from Message with tool calls."""
        tc = ToolCall(id="call_1", name="read_file", arguments={"path": "test.txt"})
        msg = Message(role="assistant", tool_calls=[tc])
        entry = SessionEntry.from_message(msg)
        assert len(entry.tool_calls) == 1
        assert entry.tool_calls[0]["name"] == "read_file"

    def test_to_message(self):
        """Should convert back to Message."""
        entry = SessionEntry(
            timestamp="2024-01-01T00:00:00Z",
            role="user",
            content="Hello",
        )
        msg = entry.to_message()
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_to_message_with_tool_calls(self):
        """Should convert tool calls back to Message."""
        entry = SessionEntry(
            timestamp="2024-01-01T00:00:00Z",
            role="assistant",
            tool_calls=[{"id": "call_1", "name": "test", "arguments": {"a": 1}}],
        )
        msg = entry.to_message()
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "test"


class TestSessionOperations:
    """Tests for session file operations."""

    def test_get_session_path(self, tmp_path: Path):
        """Should return correct session path."""
        path = get_session_path(tmp_path, "main")
        assert path == tmp_path / ".neonrp" / "sessions" / "main.jsonl"

    def test_append_and_read(self, tmp_path: Path):
        """Should append and read entries."""
        entry = SessionEntry(
            timestamp="2024-01-01T00:00:00Z",
            role="user",
            content="Test message",
        )
        append_session_entry(tmp_path, "main", entry)

        entries = read_session(tmp_path, "main")
        assert len(entries) == 1
        assert entries[0].content == "Test message"

    def test_append_multiple(self, tmp_path: Path):
        """Should append multiple entries."""
        for i in range(3):
            entry = SessionEntry(
                timestamp=f"2024-01-0{i + 1}T00:00:00Z",
                role="user",
                content=f"Message {i}",
            )
            append_session_entry(tmp_path, "main", entry)

        entries = read_session(tmp_path, "main")
        assert len(entries) == 3
        assert entries[2].content == "Message 2"

    def test_append_message(self, tmp_path: Path):
        """Should append Message object."""
        msg = Message(role="user", content="Hello from Message")
        append_message(tmp_path, "main", msg, run_id="run-1")

        entries = read_session(tmp_path, "main")
        assert len(entries) == 1
        assert entries[0].content == "Hello from Message"
        assert entries[0].run_id == "run-1"

    def test_append_session_entry_preserves_utf8_characters(self, tmp_path: Path):
        """Session JSONL should store readable UTF-8 instead of \\uXXXX escapes."""
        entry = SessionEntry(
            timestamp="2024-01-01T00:00:00Z",
            role="user",
            content="开始游戏",
        )
        append_session_entry(tmp_path, "main", entry)

        session_path = get_session_path(tmp_path, "main")
        raw = session_path.read_text(encoding="utf-8")
        assert "开始游戏" in raw
        assert "\\u5f00\\u59cb\\u6e38\\u620f" not in raw

    def test_read_session_messages(self, tmp_path: Path):
        """Should read entries as Messages."""
        msg1 = Message(role="user", content="Question")
        msg2 = Message(role="assistant", content="Answer")
        append_message(tmp_path, "main", msg1)
        append_message(tmp_path, "main", msg2)

        messages = read_session_messages(tmp_path, "main")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_read_empty_session(self, tmp_path: Path):
        """Should return empty list for missing session."""
        entries = read_session(tmp_path, "nonexistent")
        assert entries == []

    def test_session_exists(self, tmp_path: Path):
        """Should check session existence."""
        assert session_exists(tmp_path, "main") is False

        entry = SessionEntry(timestamp="2024-01-01", role="user", content="test")
        append_session_entry(tmp_path, "main", entry)

        assert session_exists(tmp_path, "main") is True

    def test_get_session_length(self, tmp_path: Path):
        """Should return entry count."""
        assert get_session_length(tmp_path, "main") == 0

        for i in range(5):
            entry = SessionEntry(timestamp="2024-01-01", role="user", content=f"msg{i}")
            append_session_entry(tmp_path, "main", entry)

        assert get_session_length(tmp_path, "main") == 5


class TestSessionTruncation:
    """Tests for session truncation (turn-based)."""

    def test_truncate_to_max_turns(self, tmp_path: Path):
        """Should truncate to max user turns, keeping full turn groups."""
        # 10 turns: each turn = user + assistant = 20 entries total
        for i in range(10):
            u = SessionEntry(timestamp=f"2024-01-{i:02d}", role="user", content=f"msg{i}")
            a = SessionEntry(timestamp=f"2024-01-{i:02d}", role="assistant", content=f"reply{i}")
            append_session_entry(tmp_path, "main", u)
            append_session_entry(tmp_path, "main", a)

        removed = truncate_session(tmp_path, "main", max_turns=5)
        assert removed == 10  # removed 5 turns * 2 entries each

        entries = read_session(tmp_path, "main")
        assert len(entries) == 10  # kept 5 turns * 2 entries
        assert entries[0].content == "msg5"
        assert entries[1].content == "reply5"

    def test_truncate_preserves_system(self, tmp_path: Path):
        """Should preserve system messages during truncation."""
        sys_entry = SessionEntry(timestamp="2024-01-01", role="system", content="System prompt")
        append_session_entry(tmp_path, "main", sys_entry)

        # 10 turns with assistant replies
        for i in range(10):
            u = SessionEntry(timestamp=f"2024-01-{i + 2:02d}", role="user", content=f"msg{i}")
            a = SessionEntry(timestamp=f"2024-01-{i + 2:02d}", role="assistant", content=f"reply{i}")
            append_session_entry(tmp_path, "main", u)
            append_session_entry(tmp_path, "main", a)

        truncate_session(tmp_path, "main", max_turns=3)

        entries = read_session(tmp_path, "main")
        assert len(entries) == 7  # 1 system + 3 turns * 2 entries
        assert entries[0].role == "system"
        assert entries[1].content == "msg7"
        assert entries[2].content == "reply7"

    def test_truncate_already_small(self, tmp_path: Path):
        """Should not truncate if already within turn limit."""
        for i in range(3):
            entry = SessionEntry(timestamp=f"2024-01-0{i + 1}", role="user", content=f"msg{i}")
            append_session_entry(tmp_path, "main", entry)

        removed = truncate_session(tmp_path, "main", max_turns=10)
        assert removed == 0
        assert get_session_length(tmp_path, "main") == 3

    def test_truncate_multi_entry_turns(self, tmp_path: Path):
        """Should keep all entries in a turn (user + tool_call + tool_result + assistant)."""
        # Turn 1: simple
        append_session_entry(tmp_path, "main", SessionEntry(timestamp="t1", role="user", content="q1"))
        append_session_entry(tmp_path, "main", SessionEntry(timestamp="t1", role="assistant", content="a1"))
        # Turn 2: heavy tool use (5 entries after user)
        append_session_entry(tmp_path, "main", SessionEntry(timestamp="t2", role="user", content="q2"))
        for j in range(5):
            append_session_entry(tmp_path, "main", SessionEntry(timestamp="t2", role="assistant", content=f"tool{j}"))
        # Turn 3: simple
        append_session_entry(tmp_path, "main", SessionEntry(timestamp="t3", role="user", content="q3"))
        append_session_entry(tmp_path, "main", SessionEntry(timestamp="t3", role="assistant", content="a3"))

        # Keep last 2 turns → turn 2 (6 entries) + turn 3 (2 entries) = 8
        removed = truncate_session(tmp_path, "main", max_turns=2)
        assert removed == 2  # turn 1 had 2 entries

        entries = read_session(tmp_path, "main")
        assert len(entries) == 8
        assert entries[0].content == "q2"
        assert entries[-1].content == "a3"


class TestSessionClear:
    """Tests for session clearing."""

    def test_clear_existing(self, tmp_path: Path):
        """Should clear existing session."""
        entry = SessionEntry(timestamp="2024-01-01", role="user", content="test")
        append_session_entry(tmp_path, "main", entry)
        assert session_exists(tmp_path, "main")

        result = clear_session(tmp_path, "main")
        assert result is True
        assert session_exists(tmp_path, "main") is False

    def test_clear_nonexistent(self, tmp_path: Path):
        """Should return False for nonexistent session."""
        result = clear_session(tmp_path, "nonexistent")
        assert result is False


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_append_user_query(self, tmp_path: Path):
        """Should append user query."""
        append_user_query(tmp_path, "main", "What is the weather?", run_id="run-1")

        entries = read_session(tmp_path, "main")
        assert len(entries) == 1
        assert entries[0].role == "user"
        assert entries[0].content == "What is the weather?"
        assert entries[0].run_id == "run-1"

    def test_append_assistant_response(self, tmp_path: Path):
        """Should append assistant response."""
        append_assistant_response(tmp_path, "main", content="It's sunny!", run_id="run-1")

        entries = read_session(tmp_path, "main")
        assert len(entries) == 1
        assert entries[0].role == "assistant"
        assert entries[0].content == "It's sunny!"

    def test_append_assistant_with_tool_calls(self, tmp_path: Path):
        """Should append assistant response with tool calls."""
        tc = ToolCall(id="call_1", name="get_weather", arguments={"city": "Tokyo"})
        append_assistant_response(tmp_path, "main", tool_calls=[tc])

        entries = read_session(tmp_path, "main")
        assert len(entries) == 1
        assert len(entries[0].tool_calls) == 1
        assert entries[0].tool_calls[0]["name"] == "get_weather"
