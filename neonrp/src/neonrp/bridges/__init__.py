"""External interface bridges (Discord, Telegram, future buddy-bot).

All bridges run in-process and communicate with the NeonRP runtime through
the `BridgeHub` pub-sub bus. They must be non-blocking w.r.t. the TUI —
errors in any one bridge never interrupt gameplay.
"""

from neonrp.bridges.hub import (
    Bridge,
    BridgeHub,
    InboundMessage,
    OutboundEvent,
)

__all__ = [
    "Bridge",
    "BridgeHub",
    "InboundMessage",
    "OutboundEvent",
]
