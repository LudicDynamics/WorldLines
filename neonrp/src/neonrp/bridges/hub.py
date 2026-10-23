"""In-process pub-sub bus for external interface bridges.

Design:
- `BridgeHub` is a lightweight coordinator. Bridges subscribe to outbound
  events (narrator text, ask_user, etc.) and submit inbound messages
  (player input from Discord/Telegram/Telegram) that the NeonRP runtime
  then handles as if the user typed into the local TUI.
- All bridges run in the same process. We do NOT use asyncio for the
  hub itself — the core runtime is threaded — so the hub dispatches
  outbound events via simple callbacks. Each bridge is responsible for
  adapting from its own async loop if needed (DiscordBridge uses a
  dedicated asyncio event loop in a background thread, etc).
- Errors inside a bridge callback must never propagate. The hub catches
  and logs so the TUI keeps running.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

logger = logging.getLogger(__name__)


OutboundKind = Literal[
    "narrator_text",          # text chunk from assistant/narrator
    "ask_user",               # ask_user prompt with options
    "scene_header",           # scene transition hint
    "state_update",           # state_delta / rule_check summary
    "system_notice",          # meta messages (mode switch, save complete, ...)
    "turn_status",            # turn lifecycle: data={"state": "thinking"|"complete"}
]

InboundKind = Literal[
    "message",                # free-form player input
    "command",                # slash-style command, e.g. "/roll 1d20"
    "button_click",           # UI element click (ask_user option index)
]


@dataclass
class OutboundEvent:
    """Platform-neutral event emitted by the runtime to all bridges."""

    kind: OutboundKind
    speaker: str = ""
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class InboundMessage:
    """Platform-neutral message submitted by a bridge to the runtime."""

    source: str                       # "tui" | "discord" | "telegram" | ...
    kind: InboundKind
    text: str = ""
    user_id: str = ""                 # platform user id
    channel_id: str = ""              # platform channel / chat id
    command: str | None = None        # canonical command name (e.g. "roll")
    command_args: list[str] = field(default_factory=list)
    button_value: str | None = None   # e.g. ask_user option label
    extra: dict[str, Any] = field(default_factory=dict)


class Bridge(Protocol):
    """Interface every bridge implements."""

    name: str                         # unique identifier (e.g. "discord")

    def start(self, hub: "BridgeHub") -> None:
        """Begin accepting events. Must be non-blocking."""
        ...

    def stop(self) -> None:
        """Tear down any background tasks / connections."""
        ...

    def on_outbound(self, event: OutboundEvent) -> None:
        """Called by the hub whenever the runtime emits an event."""
        ...


class BridgeHub:
    """Routes events between NeonRP runtime and registered bridges.

    Lifecycle:
        hub = BridgeHub()
        hub.set_inbound_handler(app._send_message)
        hub.register(TUIBridge(app))
        hub.register(DiscordBridge(cfg))
        hub.start_all()
        ...
        hub.emit(OutboundEvent("narrator_text", speaker="World", text="..."))
        hub.stop_all()
    """

    def __init__(self) -> None:
        self._bridges: list[Bridge] = []
        self._lock = threading.Lock()
        self._inbound_handler: Callable[[InboundMessage], None] | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, bridge: Bridge) -> None:
        with self._lock:
            self._bridges.append(bridge)
            if self._started:
                self._safe_start(bridge)

    def unregister(self, bridge: Bridge) -> None:
        with self._lock:
            if bridge in self._bridges:
                self._bridges.remove(bridge)
                self._safe_stop(bridge)

    def list_bridges(self) -> list[str]:
        with self._lock:
            return [getattr(b, "name", type(b).__name__) for b in self._bridges]

    # ------------------------------------------------------------------
    # Inbound (bridge → runtime)
    # ------------------------------------------------------------------

    def set_inbound_handler(self, handler: Callable[[InboundMessage], None]) -> None:
        """Runtime registers a single handler for bridge-originated messages."""
        self._inbound_handler = handler

    def submit_inbound(self, message: InboundMessage) -> None:
        """Bridges call this to forward a player message into the runtime.

        Runs on whatever thread the bridge submits from. The runtime's
        handler is responsible for thread-safety (typically the TUI's
        `_send_message` which already expects cross-thread calls).
        """
        handler = self._inbound_handler
        if handler is None:
            logger.debug("inbound dropped — no handler registered: %s", message)
            return
        try:
            handler(message)
        except Exception:
            logger.exception("inbound handler raised for %s", message.source)

    # ------------------------------------------------------------------
    # Outbound (runtime → bridges)
    # ------------------------------------------------------------------

    def emit(self, event: OutboundEvent) -> None:
        """Fan out an event to every registered bridge.

        Must never raise — swallow each bridge's exception so the runtime
        keeps streaming.
        """
        with self._lock:
            snapshot = list(self._bridges)
        for bridge in snapshot:
            try:
                bridge.on_outbound(event)
            except Exception:
                logger.exception("bridge %s raised on outbound event", getattr(bridge, "name", "?"))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_all(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            snapshot = list(self._bridges)
        for bridge in snapshot:
            self._safe_start(bridge)

    def stop_all(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False
            snapshot = list(self._bridges)
        for bridge in snapshot:
            self._safe_stop(bridge)

    def _safe_start(self, bridge: Bridge) -> None:
        try:
            bridge.start(self)
        except Exception:
            logger.exception("bridge %s failed to start", getattr(bridge, "name", "?"))

    def _safe_stop(self, bridge: Bridge) -> None:
        try:
            bridge.stop()
        except Exception:
            logger.exception("bridge %s failed to stop cleanly", getattr(bridge, "name", "?"))


# Global hub for the current TUI process. Optional; callers can also
# instantiate their own for tests or headless mode.
_HUB: BridgeHub | None = None


def get_default_hub() -> BridgeHub:
    global _HUB
    if _HUB is None:
        _HUB = BridgeHub()
    return _HUB


def reset_default_hub() -> None:
    """Test helper — drop the process-wide hub."""
    global _HUB
    if _HUB is not None:
        _HUB.stop_all()
    _HUB = None
