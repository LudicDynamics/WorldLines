"""WorldLines Dual-Kernel abstraction.

Provides a protocol for game kernels so the TUI can swap between
NeonRP's built-in ConversationSession and future Claude-based kernels.

Phase 3: NeonRPKernel wraps existing ConversationSession.
Phase 4: ClaudeKernel will use Claude API + custom tool-calling.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass
class TurnResult:
    """Unified result from a kernel turn."""

    success: bool
    assistant_message: str = ""
    files_modified: list[str] = field(default_factory=list)
    tool_calls_made: list[str] = field(default_factory=list)
    turns_used: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    cancelled: bool = False


@runtime_checkable
class GameKernel(Protocol):
    """Protocol for game execution kernels.

    The TUI holds a kernel instance and delegates all player input
    through ``send_turn``.  ``/wl-model`` can swap the active kernel.
    """

    def send_turn(
        self,
        root: Path,
        text: str,
        *,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
        on_ask_user: Callable[[str, list[str]], str | None] | None = None,
    ) -> TurnResult:
        """Execute one player turn and return the result."""
        ...

    def cancel(self) -> None:
        """Signal the running turn to stop."""
        ...

    def clear(self) -> None:
        """Reset conversation state."""
        ...


class NeonRPKernel:
    """Kernel backed by NeonRP's ConversationSession.

    This is a thin adapter that delegates to the existing
    ``ConversationSession.send()`` method.
    """

    def __init__(self, session: Any) -> None:
        """Wrap an existing ConversationSession.

        Args:
            session: A ``neonrp.core.conversation.ConversationSession`` instance.
        """
        self._session = session

    def send_turn(
        self,
        root: Path,
        text: str,
        *,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
        on_ask_user: Callable[[str, list[str]], str | None] | None = None,
    ) -> TurnResult:
        result = self._session.send(
            text,
            on_chunk=on_chunk,
            on_thinking=on_thinking,
            on_tool_use=on_tool_use,
            on_tool_result=on_tool_result,
            on_ask_user=on_ask_user,
        )
        return TurnResult(
            success=result.success,
            assistant_message=result.assistant_message,
            files_modified=result.files_modified,
            tool_calls_made=result.tool_calls_made,
            turns_used=result.turns_used,
            usage=result.usage,
            error=result.error,
            cancelled=result.cancelled,
        )

    def cancel(self) -> None:
        self._session.cancel()

    def clear(self) -> None:
        self._session.clear()


class ClaudeKernel:
    """Placeholder kernel for Phase 4: Claude API + custom tool-calling.

    Not yet implemented. Will use Claude's native tool-use to drive
    game state instead of NeonRP's agent routing.
    """

    def send_turn(
        self,
        root: Path,
        text: str,
        *,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_tool_use: Callable[[str, dict[str, Any]], None] | None = None,
        on_tool_result: Callable[[str, dict[str, Any], str], None] | None = None,
        on_ask_user: Callable[[str, list[str]], str | None] | None = None,
    ) -> TurnResult:
        return TurnResult(
            success=False,
            error="ClaudeKernel not yet implemented (Phase 4).",
        )

    def cancel(self) -> None:
        pass

    def clear(self) -> None:
        pass
