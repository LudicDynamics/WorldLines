"""M18 Phase 2 — the in-process message bus (the broker).

A small synchronous pub/sub broker. Agents (world / players / souls) and
observers (frontends, the orchestration trace) never call each other — they
publish and subscribe on topics. This module is the in-process transport;
the *protocol* (topics + message shapes) is transport-agnostic, so a future
SubprocessBus / MQTTBroker swaps in without touching agent code (M18 §4.1).

Why synchronous: NeonRP turns are lockstep — publish dispatches to matching
subscribers inline, in subscription order. That is enough for single-machine
turn-based play and keeps ordering trivially deterministic (every message
carries a monotonic ``seq``). Real concurrency / cross-host is the M19 /
Phase 6 distributed transport, not this.

Topic matching is MQTT-style: ``+`` matches exactly one level, ``#`` matches
the rest. e.g. ``soul/+/response`` matches ``soul/elena/response``;
``engine/#`` matches ``engine/event`` and ``engine/turn/started``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1


@dataclass(frozen=True)
class BusMessage:
    """One message on the bus. Transport-agnostic: ``payload`` must be
    JSON-serialisable (no Python object references) so the same message can
    later cross a pipe or an MQTT broker unchanged."""

    topic: str
    payload: dict[str, Any]
    seq: int
    ts: str
    protocol_version: int = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "payload": self.payload,
            "seq": self.seq,
            "ts": self.ts,
            "protocol_version": self.protocol_version,
        }


Handler = Callable[[BusMessage], None]


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT-style match. ``+`` = one level, ``#`` = the remaining levels
    (only valid as the final segment). Exact match otherwise."""
    p = pattern.split("/")
    t = topic.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return i == len(p) - 1  # '#' must be the last segment
        if i >= len(t):
            return False
        if seg == "+":
            continue
        if seg != t[i]:
            return False
    return len(p) == len(t)


@dataclass
class _Subscription:
    pattern: str
    handler: Handler


class InProcessBus:
    """Synchronous in-process pub/sub broker.

    ``publish`` assigns the next monotonic ``seq``, stamps the time, and
    dispatches to every subscription whose pattern matches — inline, in
    subscription order. A handler that raises is isolated (logged) so one
    faulty subscriber cannot break a publish or the turn.
    """

    def __init__(self) -> None:
        self._subs: list[_Subscription] = []
        self._seq: int = 0
        self._log: list[BusMessage] = []
        self._record = False
        # Topics dispatched to subscribers but NEVER recorded — token-volume
        # streams (engine/stream) that would bloat the per-turn trace.
        self.transient_topics: set[str] = set()

    # ---- subscription -------------------------------------------------
    def subscribe(self, topic_pattern: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler`` for messages matching ``topic_pattern``.
        Returns an unsubscribe callable."""
        sub = _Subscription(pattern=topic_pattern, handler=handler)
        self._subs.append(sub)

        def _unsubscribe() -> None:
            try:
                self._subs.remove(sub)
            except ValueError:
                pass

        return _unsubscribe

    # ---- publish ------------------------------------------------------
    def publish(self, topic: str, payload: dict[str, Any]) -> BusMessage:
        """Publish ``payload`` on ``topic``. Assigns a monotonic ``seq``,
        dispatches synchronously to all matching subscribers, returns the
        sent message."""
        self._seq += 1
        msg = BusMessage(
            topic=topic,
            payload=payload,
            seq=self._seq,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        if self._record and topic not in self.transient_topics:
            self._log.append(msg)
        for sub in list(self._subs):  # copy: a handler may (un)subscribe
            if topic_matches(sub.pattern, topic):
                try:
                    sub.handler(msg)
                except Exception:  # noqa: BLE001 - isolate a faulty subscriber
                    logger.debug(
                        "bus subscriber for %r raised on %r", sub.pattern, topic,
                        exc_info=True,
                    )
        return msg

    # ---- recording (feeds the orchestration trace / replay) ----------
    def start_recording(self) -> None:
        """Begin capturing every published message into an ordered log —
        the per-turn message stream that M17's determinism payload and the
        M18 §7 trace consume."""
        self._record = True

    def drain_log(self) -> list[BusMessage]:
        """Return and clear the recorded message log (publish order)."""
        out = self._log
        self._log = []
        return out

    @property
    def seq(self) -> int:
        """The last assigned sequence number."""
        return self._seq

    @property
    def subscription_count(self) -> int:
        return len(self._subs)
