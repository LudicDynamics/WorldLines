"""Session persistence for NeonRP.

This module provides session management for multi-turn agent conversations.
Sessions store conversation history in JSONL format and support:
- Append/read operations
- Truncation to last N turns
- Branch binding (each branch has its own session)

M6-T4: Session Persistence
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from neonrp.core.llm import Message, ToolCall
from neonrp.core.paths import get_neonrp_dir

# Default session configuration
DEFAULT_MAX_TURNS = 50


@dataclass
class SessionEntry:
    """A single entry in a session log."""

    timestamp: str
    role: str  # user, assistant, tool, system
    content: Optional[str] = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    run_id: Optional[str] = None  # Agent run that created this entry
    # Reasoning / chain-of-thought emitted by the model (DeepSeek
    # `reasoning_content`, etc.). Persisted so resumed sessions can echo
    # it back — DeepSeek thinking mode rejects multi-turn requests that
    # drop it from prior assistant messages.
    reasoning_content: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to serializable dict."""
        d = {
            "timestamp": self.timestamp,
            "role": self.role,
        }
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        if self.run_id:
            d["run_id"] = self.run_id
        if self.reasoning_content:
            d["reasoning_content"] = self.reasoning_content
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SessionEntry":
        """Create from dict."""
        return cls(
            timestamp=data.get("timestamp", ""),
            role=data.get("role", ""),
            content=data.get("content"),
            tool_calls=data.get("tool_calls", []),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            run_id=data.get("run_id"),
            reasoning_content=data.get("reasoning_content"),
        )

    @classmethod
    def from_message(cls, message: Message, run_id: Optional[str] = None) -> "SessionEntry":
        """Create from Message object."""
        tool_calls_data = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls_data.append(
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                )

        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            role=message.role,
            content=message.content,
            tool_calls=tool_calls_data,
            tool_call_id=message.tool_call_id,
            name=message.name,
            run_id=run_id,
            reasoning_content=getattr(message, "reasoning_content", None),
        )

    def to_message(self) -> Message:
        """Convert to Message object."""
        tool_calls = None
        if self.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc["arguments"],
                )
                for tc in self.tool_calls
            ]

        return Message(
            role=self.role,
            content=self.content,
            tool_calls=tool_calls,
            tool_call_id=self.tool_call_id,
            name=self.name,
            reasoning_content=self.reasoning_content,
        )


def get_session_path(root: Path, branch: str) -> Path:
    """Get path to session file for a branch.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        Path to session JSONL file
    """
    session_dir = get_neonrp_dir(root) / "sessions"
    return session_dir / f"{branch}.jsonl"


def append_session_entry(root: Path, branch: str, entry: SessionEntry) -> None:
    """Append an entry to the session log.

    Args:
        root: Project root directory
        branch: Branch name
        entry: Session entry to append
    """
    session_path = get_session_path(root, branch)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    with open(session_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


def append_message(root: Path, branch: str, message: Message, run_id: Optional[str] = None) -> None:
    """Append a Message to the session log.

    Args:
        root: Project root directory
        branch: Branch name
        message: Message to append
        run_id: Optional run ID
    """
    entry = SessionEntry.from_message(message, run_id)
    append_session_entry(root, branch, entry)


def read_session(root: Path, branch: str) -> list[SessionEntry]:
    """Read all entries from a session log.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        List of session entries
    """
    session_path = get_session_path(root, branch)
    if not session_path.exists():
        return []

    entries = []
    with open(session_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                    entries.append(SessionEntry.from_dict(data))
                except json.JSONDecodeError:
                    continue  # Skip malformed lines

    return entries


def read_session_messages(root: Path, branch: str) -> list[Message]:
    """Read session entries as Message objects.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        List of Message objects
    """
    entries = read_session(root, branch)
    return [entry.to_message() for entry in entries]


def sanitize_messages_for_resume(messages: list[Message]) -> list[Message]:
    """Repair orphan tool_call / tool-result sequences in a resumed session.

    OpenAI-format chat APIs require every assistant message that carries
    ``tool_calls`` to be followed by exactly one ``role: "tool"`` message
    per ``tool_call_id``. Otherwise the next request returns either:

        400 — "An assistant message with 'tool_calls' must be followed
              by tool messages responding to each 'tool_call_id'."
        400 — "Messages with role 'tool' must be a response to a
              preceding message with 'tool_calls'."

    DeepSeek's API is strict about both halves; OpenAI proper is lenient
    about dangling tool results but not dangling tool calls.

    A session can become unbalanced when a prior turn ended mid-stream:
    network drop, kill -9, provider error after the model emitted the
    call but before we wrote the tool result, the user cancelled an
    AskUserQuestion, two assistant turns landed back-to-back, etc. The
    on-disk session log is a faithful append-only record; we leave it
    intact and only repair the in-memory copy used to call the LLM.

    Algorithm (block-based, single pass):

    Walk the message list. When we hit an ``assistant`` message with
    ``tool_calls``, grab every immediately-following ``role: "tool"``
    message as that block's tail (stops at the next non-tool message
    or end of stream). If every ``tool_call_id`` in the assistant has
    a matching ``tool_call_id`` in the tail, the block is **complete**
    — keep the assistant + its first matching tool per id (dedup).
    Otherwise, **strip** ``tool_calls`` from the assistant (preserving
    content + reasoning_content) and drop the entire tool tail — all
    of them would be orphans against the now-stripped assistant.

    Bare tool messages between blocks (not in any block's tail) are
    always orphans and get dropped.

    Deterministic and idempotent. Running twice is a no-op.
    """
    from dataclasses import replace

    out: list[Message] = []
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]

        if msg.role == "assistant" and msg.tool_calls:
            # Gather the tool-message tail for this block.
            j = i + 1
            tail: list[Message] = []
            while j < n and messages[j].role == "tool":
                tail.append(messages[j])
                j += 1

            needed = {tc.id for tc in msg.tool_calls if tc.id}
            tail_ids = {tm.tool_call_id for tm in tail if tm.tool_call_id}

            if needed and needed.issubset(tail_ids):
                # Complete block — emit assistant + exactly one tool per
                # needed id (skip duplicates and ids not in `needed`).
                out.append(msg)
                emitted: set[str] = set()
                for tm in tail:
                    tcid = tm.tool_call_id or ""
                    if tcid in needed and tcid not in emitted:
                        out.append(tm)
                        emitted.add(tcid)
                i = j
                continue

            # Incomplete block — strip tool_calls from the assistant
            # (preserve content / reasoning_content) and drop the tail
            # entirely. All those tail tool messages would be orphan
            # references to the now-stripped tool_calls.
            out.append(replace(msg, tool_calls=None))
            i = j
            continue

        if msg.role == "tool":
            # A tool message NOT immediately following an
            # assistant(tool_calls) is an orphan — would 400.
            i += 1
            continue

        out.append(msg)
        i += 1

    return out


def truncate_session(root: Path, branch: str, max_turns: int = DEFAULT_MAX_TURNS) -> int:
    """Truncate session to keep only the last N conversation turns.

    A "turn" starts at each ``role="user"`` entry and includes all
    subsequent non-user, non-system entries (assistant, tool, etc.)
    until the next user entry.  System messages are always preserved.

    Args:
        root: Project root directory
        branch: Branch name
        max_turns: Maximum *user turns* to keep

    Returns:
        Number of entries removed
    """
    entries = read_session(root, branch)

    # Separate system messages from conversation entries
    system_entries = [e for e in entries if e.role == "system"]
    non_system = [e for e in entries if e.role != "system"]

    # Group non-system entries into turns (each turn starts with a user msg)
    turns: list[list[SessionEntry]] = []
    for entry in non_system:
        if entry.role == "user":
            turns.append([entry])
        else:
            if turns:
                turns[-1].append(entry)
            else:
                # Orphan non-user entry before any user msg – start a group
                turns.append([entry])

    if len(turns) <= max_turns:
        return 0

    kept_turns = turns[-max_turns:]
    kept_entries = system_entries + [e for turn in kept_turns for e in turn]
    removed = len(entries) - len(kept_entries)

    # Rewrite session file
    session_path = get_session_path(root, branch)
    with open(session_path, "w", encoding="utf-8") as f:
        for entry in kept_entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    return removed


def clear_session(root: Path, branch: str) -> bool:
    """Clear all entries from a session.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        True if session was cleared, False if it didn't exist
    """
    session_path = get_session_path(root, branch)
    if session_path.exists():
        session_path.unlink()
        return True
    return False


def session_exists(root: Path, branch: str) -> bool:
    """Check if a session exists for a branch.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        True if session file exists
    """
    return get_session_path(root, branch).exists()


def get_session_length(root: Path, branch: str) -> int:
    """Get number of entries in a session.

    Args:
        root: Project root directory
        branch: Branch name

    Returns:
        Number of entries
    """
    return len(read_session(root, branch))


def append_user_query(root: Path, branch: str, query: str, run_id: Optional[str] = None) -> None:
    """Append a user query to the session.

    Convenience method for adding user messages.

    Args:
        root: Project root directory
        branch: Branch name
        query: User query text
        run_id: Optional run ID
    """
    message = Message(role="user", content=query)
    append_message(root, branch, message, run_id)


def append_assistant_response(
    root: Path,
    branch: str,
    content: Optional[str] = None,
    tool_calls: Optional[list[ToolCall]] = None,
    run_id: Optional[str] = None,
) -> None:
    """Append an assistant response to the session.

    Args:
        root: Project root directory
        branch: Branch name
        content: Response content
        tool_calls: Tool calls made
        run_id: Optional run ID
    """
    message = Message(role="assistant", content=content, tool_calls=tool_calls)
    append_message(root, branch, message, run_id)
