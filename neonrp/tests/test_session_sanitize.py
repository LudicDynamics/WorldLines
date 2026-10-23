"""Tests for `sanitize_messages_for_resume` — the repair pass that
keeps OpenAI-format APIs (DeepSeek especially) from 400'ing on
sessions that ended mid-tool-call.
"""

from __future__ import annotations

from neonrp.core.llm import Message, ToolCall
from neonrp.core.session import sanitize_messages_for_resume


def _tc(id_: str, name: str = "fn") -> ToolCall:
    return ToolCall(id=id_, name=name, arguments={})


# ---------------------------------------------------------------------------
# Clean / well-formed sessions pass through untouched.
# ---------------------------------------------------------------------------

def test_empty_message_list_is_unchanged() -> None:
    assert sanitize_messages_for_resume([]) == []


def test_well_formed_tool_pair_preserved() -> None:
    msgs = [
        Message(role="user", content="open the door"),
        Message(role="assistant", content="trying", tool_calls=[_tc("call_1")]),
        Message(role="tool", content="opened", tool_call_id="call_1", name="fn"),
        Message(role="assistant", content="done"),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert len(out) == 4
    assert out[1].tool_calls is not None  # preserved
    assert out[2].tool_call_id == "call_1"


def test_multiple_tool_calls_all_resolved_preserved() -> None:
    msgs = [
        Message(role="user", content="do two things"),
        Message(role="assistant", content="ok", tool_calls=[_tc("a"), _tc("b")]),
        Message(role="tool", content="result-a", tool_call_id="a", name="fn"),
        Message(role="tool", content="result-b", tool_call_id="b", name="fn"),
        Message(role="user", content="next"),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert len(out) == 5
    assert out[1].tool_calls and len(out[1].tool_calls) == 2


def test_sanitize_is_idempotent() -> None:
    msgs = [
        Message(role="assistant", content="x", tool_calls=[_tc("call_1")]),
        # No tool response — sanitization will strip tool_calls.
    ]
    once = sanitize_messages_for_resume(msgs)
    twice = sanitize_messages_for_resume(once)
    assert once == twice


# ---------------------------------------------------------------------------
# Trailing dangling tool_calls (session crashed mid-call).
# ---------------------------------------------------------------------------

def test_trailing_dangling_tool_calls_stripped() -> None:
    """Most common case: previous turn called a tool, session was saved
    before the tool result was written. Next session would 400."""
    msgs = [
        Message(role="user", content="open the door"),
        Message(role="assistant", content="trying", tool_calls=[_tc("call_1")]),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert len(out) == 2
    assert out[1].tool_calls is None  # stripped
    assert out[1].content == "trying"  # preserved


def test_trailing_dangling_tool_calls_no_content() -> None:
    """Tool call with no narrative content — still kept as a node, just
    without tool_calls so the API doesn't barf on the next user message.
    """
    msgs = [
        Message(role="user", content="open the door"),
        Message(role="assistant", content=None, tool_calls=[_tc("call_1")]),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert out[1].tool_calls is None


# ---------------------------------------------------------------------------
# Dangling in the middle (some tool ids resolved, others not).
# ---------------------------------------------------------------------------

def test_partial_tool_call_resolution_strips_block() -> None:
    """If any tool_call_id is unresolved, the entire block is broken.
    Strip the assistant's tool_calls AND drop every tool message in the
    tail — all of them are now orphan against the stripped assistant."""
    msgs = [
        Message(role="assistant", content="two", tool_calls=[_tc("a"), _tc("b")]),
        Message(role="tool", content="result-a", tool_call_id="a", name="fn"),
        # tool_call_id 'b' never resolved
        Message(role="user", content="give up, try this instead"),
    ]
    out = sanitize_messages_for_resume(msgs)
    # Assistant tool_calls stripped
    assert out[0].tool_calls is None
    assert out[0].content == "two"  # preserved
    # No tool messages remain in the output
    assert all(m.role != "tool" for m in out)
    # User message preserved at the end
    assert out[-1].role == "user"


def test_dangling_then_new_user_strips_predecessor() -> None:
    msgs = [
        Message(role="user", content="a"),
        Message(role="assistant", content="trying", tool_calls=[_tc("x")]),
        Message(role="user", content="b"),  # closes the tool window with no result
        Message(role="assistant", content="answering b"),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert out[1].tool_calls is None
    assert out[1].content == "trying"


# ---------------------------------------------------------------------------
# Orphan tool messages (no preceding assistant tool_call).
# ---------------------------------------------------------------------------

def test_orphan_tool_message_dropped() -> None:
    msgs = [
        Message(role="user", content="hello"),
        Message(role="tool", content="surprise!", tool_call_id="ghost", name="fn"),
        Message(role="assistant", content="hi"),
    ]
    out = sanitize_messages_for_resume(msgs)
    assert all(m.role != "tool" for m in out)
    assert len(out) == 2


def test_tool_after_consumed_tool_call_is_orphan() -> None:
    """Once the matching tool result has been consumed, a SECOND tool
    message with the same id is an orphan."""
    msgs = [
        Message(role="assistant", content=None, tool_calls=[_tc("a")]),
        Message(role="tool", content="r1", tool_call_id="a", name="fn"),
        Message(role="tool", content="dup", tool_call_id="a", name="fn"),  # orphan
        Message(role="user", content="next"),
    ]
    out = sanitize_messages_for_resume(msgs)
    tool_msgs = [m for m in out if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == "r1"


# ---------------------------------------------------------------------------
# System messages flow through untouched.
# ---------------------------------------------------------------------------

def test_system_message_breaks_tool_block() -> None:
    """A system message between assistant(tool_calls) and the tool
    result terminates the tool block. The assistant's tool_calls is
    stripped (no matching tail); the tool result that follows the
    system message is then orphan and dropped."""
    msgs = [
        Message(role="assistant", content=None, tool_calls=[_tc("a")]),
        Message(role="system", content="reset"),
        Message(role="tool", content="r1", tool_call_id="a", name="fn"),
    ]
    out = sanitize_messages_for_resume(msgs)
    assistant = next(m for m in out if m.role == "assistant")
    assert assistant.tool_calls is None
    assert all(m.role != "tool" for m in out)


# ---------------------------------------------------------------------------
# Consecutive assistant(tool_calls) — the case that broke the first impl.
# ---------------------------------------------------------------------------

def test_two_consecutive_assistant_tool_calls_first_unresolved() -> None:
    """Two assistant(tool_calls) back-to-back with no tool results
    between them: first block is incomplete (no tail at all), strip its
    tool_calls + drop nothing (no tail to drop). Second block continues
    independently."""
    msgs = [
        Message(role="user", content="start"),
        Message(role="assistant", content="first", tool_calls=[_tc("a")]),
        Message(role="assistant", content="second", tool_calls=[_tc("b")]),
        Message(role="tool", content="r-b", tool_call_id="b", name="fn"),
        Message(role="user", content="more"),
    ]
    out = sanitize_messages_for_resume(msgs)
    # First assistant: tool_calls stripped (no matching tool result)
    assert out[1].tool_calls is None
    assert out[1].content == "first"
    # Second assistant: complete block, tool_calls preserved
    assert out[2].tool_calls is not None
    # Tool result for 'b' kept
    tool_msgs = [m for m in out if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].tool_call_id == "b"


def test_sanitize_after_budget_trim_handles_split_block() -> None:
    """Budget trim pops ``messages[1]`` blindly to fit the context
    window, which can cut a tool-call block in half. Re-running
    sanitize on the result must produce a valid stream — no orphan
    assistant tool_calls, no orphan tool messages.

    Production repro: DeepSeek 400'd after the first sanitize because
    budget trim chopped the head of a long history, leaving an
    assistant's tail tool results orphan against the (popped) parent.
    """
    msgs = [
        Message(role="system", content="sys"),
        Message(role="assistant", content=None, tool_calls=[_tc("a"), _tc("b")]),
        Message(role="tool", content="r-a", tool_call_id="a", name="fn"),
        Message(role="tool", content="r-b", tool_call_id="b", name="fn"),
        Message(role="user", content="next"),
        Message(role="assistant", content=None, tool_calls=[_tc("c")]),
        Message(role="tool", content="r-c", tool_call_id="c", name="fn"),
        Message(role="user", content="another"),
    ]
    # Simulate budget trim popping messages[1] (the first assistant).
    # The tool results at indices 1 and 2 (post-pop) are now orphan.
    msgs.pop(1)

    out = sanitize_messages_for_resume(msgs)

    # Check the OpenAI invariant: every assistant(tool_calls) followed
    # by exactly the right tool tail; no bare tool messages between blocks.
    i = 0
    while i < len(out):
        if out[i].role == "assistant" and out[i].tool_calls:
            needed = {tc.id for tc in out[i].tool_calls if tc.id}
            j = i + 1
            seen = set()
            while j < len(out) and out[j].role == "tool":
                seen.add(out[j].tool_call_id)
                j += 1
            assert needed.issubset(seen), f"assistant at {i} missing {needed - seen}"
            i = j
        elif out[i].role == "tool":
            raise AssertionError(f"orphan tool message at {i}")
        else:
            i += 1


def test_block_with_extra_tool_messages_dedup() -> None:
    """An assistant(tool_calls=[a]) followed by THREE tool messages
    where only one has id=a should keep just the matching one."""
    msgs = [
        Message(role="assistant", content=None, tool_calls=[_tc("a")]),
        Message(role="tool", content="bogus", tool_call_id="ghost", name="fn"),
        Message(role="tool", content="r-a", tool_call_id="a", name="fn"),
        Message(role="tool", content="dup-a", tool_call_id="a", name="fn"),
        Message(role="user", content="next"),
    ]
    out = sanitize_messages_for_resume(msgs)
    # Block is complete (a is in tail)
    assert out[0].tool_calls is not None
    tool_msgs = [m for m in out if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == "r-a"
