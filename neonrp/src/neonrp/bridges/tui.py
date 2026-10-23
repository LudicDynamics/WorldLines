"""TUI as a first-class bridge.

`TUIBridge` is a no-op adapter: the TUI is already the primary surface and
handles input/output directly. This class exists so the hub has a stable
set of registered bridges and the list-bridges UI can show "tui" alongside
"discord" / "telegram".

We deliberately do NOT mirror TUI events back through the hub (that would
cause double-rendering in the local transcript). Outbound events emitted
by the runtime are consumed directly by ConversationView; the hub forwards
them to OTHER bridges.
"""

from __future__ import annotations

from typing import Any

from neonrp.bridges.hub import BridgeHub, OutboundEvent


class TUIBridge:
    """Placeholder bridge representing the local TUI surface."""

    name = "tui"

    def __init__(self, app: Any) -> None:
        self._app = app
        self._hub: BridgeHub | None = None

    def start(self, hub: BridgeHub) -> None:
        self._hub = hub

    def stop(self) -> None:
        self._hub = None

    def on_outbound(self, event: OutboundEvent) -> None:  # noqa: ARG002
        # The TUI's ConversationView is already rendering the same content
        # synchronously via its own add_assistant_chunk / add_tool_indicator
        # path. Re-rendering here would duplicate lines in the local view.
        return


# ---------------------------------------------------------------------------
# Helper: emit without importing hub everywhere.
# ---------------------------------------------------------------------------

def emit_if_hub(hub: BridgeHub | None, event: OutboundEvent) -> None:
    """Small convenience used inside the TUI: publish an event only when
    a hub is registered. Keeps call sites tidy:

        emit_if_hub(self.bridge_hub, OutboundEvent("narrator_text", ...))
    """
    if hub is None:
        return
    hub.emit(event)
