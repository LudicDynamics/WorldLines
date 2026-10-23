"""M18 — per-turn orchestration trace.

A structured, append-only record of what the runtime did each multi-agent
turn: which souls were considered/activated and why, what each returned,
what the world-agent produced, and how the turn closed. One JSON object per
turn, appended to ``.neonrp/orchestration/<branch>.jsonl``.

This is the M18 §7 observability surface in its pre-broker form: today the
record is assembled from the live ``_run_multi_agent_turn`` data; once the
pub/sub bus lands (M18 Phase 2) the same record is the bus message stream.
It is also the natural shape of M17's determinism/replay payload.

Design: **never raise into a turn.** A trace-write failure must not affect
play — every public function is best-effort and swallows its own errors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TRACE_SCHEMA_VERSION = 1


@dataclass
class SoulTraceEntry:
    """One soul's slice of a turn trace."""

    sid: str
    instance_id: str
    activated: bool
    reason: str = ""
    location: str | None = None
    state: str | None = None          # completed / degraded / interrupted
    structured: bool | None = None     # was the soul report a structured envelope
    folder_changed: bool | None = None  # did the soul fold-hash change this turn
    tool_calls: int = 0
    speech: str = ""
    judgment: dict[str, Any] | None = None  # the judge's numbers that decided her this turn (follow / stay / attitude …)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "sid": self.sid,
            "instance_id": self.instance_id,
            "activated": self.activated,
            "reason": self.reason,
        }
        # Only include the runtime fields once the soul has actually run.
        for k, v in (
            ("location", self.location),
            ("state", self.state),
            ("structured", self.structured),
            ("folder_changed", self.folder_changed),
            ("judgment", self.judgment),
        ):
            if v is not None:
                d[k] = v
        if self.activated:
            d["tool_calls"] = self.tool_calls
            d["speech"] = self.speech
        return d


@dataclass
class TurnTrace:
    """Accumulator for one multi-agent turn's orchestration record.

    Filled incrementally as the turn progresses; serialised once at the end
    via :func:`append_turn_trace`.
    """

    turn_seq: int
    player_input: str = ""
    player_intent_kind: str = ""
    world_location: str | None = None
    souls: list[SoulTraceEntry] = field(default_factory=list)
    world_agent_tool_calls: list[dict[str, Any]] = field(default_factory=list)
    narration_chars: int = 0
    world_commit_id: str | None = None
    landed_ok: bool | None = None
    notes: str = ""
    # M18 Phase 2c: the ordered message-bus stream for this turn (each entry
    # is a BusMessage.to_dict()). This is the turn routed through the broker;
    # it is also the shape M17's determinism/replay payload consumes.
    bus_messages: list[dict[str, Any]] = field(default_factory=list)
    # exp/jev-system-one: the S1 turn plan (who reacts / how deep / intent)
    # and per-stage timing, so "what System One predicted" vs "who actually
    # acted" is auditable per turn.
    plan: dict[str, Any] | None = None
    timing: dict[str, Any] = field(default_factory=dict)
    # engine v3: the SDK ApplyResult (§5) and the span timeline (§11). Both
    # are None/empty on a v2b turn so old readers see no change.
    apply: dict[str, Any] | None = None
    spans: list[dict[str, Any]] = field(default_factory=list)

    def soul(self, sid: str, instance_id: str, *, activated: bool, reason: str = "") -> SoulTraceEntry:
        """Create + register a soul entry, returned so the caller can fill it
        in as the soul runs."""
        entry = SoulTraceEntry(
            sid=sid, instance_id=instance_id, activated=activated, reason=reason
        )
        self.souls.append(entry)
        return entry

    def record_tool_call(self, name: str, arguments: dict[str, Any] | None) -> None:
        """Record one world-agent tool call (name + a compact arg preview)."""
        preview = ""
        try:
            preview = json.dumps(arguments or {}, ensure_ascii=False)[:200]
        except (TypeError, ValueError):
            preview = "<unserialisable>"
        self.world_agent_tool_calls.append({"name": name, "args": preview})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "turn_seq": self.turn_seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "player": {
                "input": self.player_input[:500],
                "intent_kind": self.player_intent_kind,
            },
            "world_location": self.world_location,
            "souls": [s.to_dict() for s in self.souls],
            "world_agent": {
                "tool_calls": self.world_agent_tool_calls,
                "narration_chars": self.narration_chars,
            },
            "land": {"commit_id": self.world_commit_id, "ok": self.landed_ok},
            "notes": self.notes,
            "plan": self.plan,
            "timing": dict(self.timing),
            "bus_messages": self.bus_messages,
            "apply": self.apply,
            "spans": list(self.spans),
        }


def _trace_path(root: Path, branch: str) -> Path:
    safe_branch = (branch or "main").replace("/", "-")
    return root / ".neonrp" / "orchestration" / f"{safe_branch}.jsonl"


def append_turn_trace(root: Path, branch: str, trace: TurnTrace) -> None:
    """Append one turn's record as a JSONL line. Best-effort: any failure is
    logged at debug level and swallowed — tracing must never break a turn."""
    try:
        path = _trace_path(root, branch)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(trace.to_dict(), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — observability must never raise into a turn
        logger.debug("orchestration trace append skipped", exc_info=True)
        return
    _keep_replay_if_finished(root, trace)


def amend_turn_trace(root: Path, branch: str, turn_seq: int, fn: Any) -> bool:
    """Change the last record of turn ``turn_seq`` in place (``fn(record)`` edits it) — for what lands after the turn
    (core/write_down_async: the background write-down's correction). The caller holds the run's lock, so no turn is
    appending meanwhile. Best-effort: False when the record is not there or the file cannot be rewritten."""
    try:
        path = _trace_path(root, branch)
        lines = path.read_text(encoding="utf-8").splitlines()
        for i in range(len(lines) - 1, -1, -1):
            if not lines[i].strip():
                continue
            rec = json.loads(lines[i])
            if rec.get("turn_seq") != turn_seq:
                continue
            fn(rec)
            lines[i] = json.dumps(rec, ensure_ascii=False)
            tmp = path.with_suffix(".jsonl.tmp")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            tmp.replace(path)
            return True
    except Exception:  # noqa: BLE001 — observability must never raise
        logger.debug("orchestration trace amend skipped", exc_info=True)
    return False


def _keep_replay_if_finished(root: Path, trace: TurnTrace) -> None:
    """The run ended this turn (an ending fired, or it reached its exit): keep it as a replay on this machine
    (core/replay_library, 10-18). After the append, so the last beat is in the replay; off the turn's thread."""
    apply = getattr(trace, "apply", None)
    if not isinstance(apply, dict):
        return
    ended = apply.get("ended")
    if not ((isinstance(ended, dict) and ended.get("id")) or apply.get("settled")):
        return
    import sys
    import threading

    if sys.platform == "emscripten":   # the browser build has no threads and no replay library (it shares from the ending screen)
        return
    try:
        from neonrp.core import replay_library

        threading.Thread(target=replay_library.on_ending, args=(Path(root), ended if isinstance(ended, dict) else {}, replay_library.HOME),
                         name="replay-on-ending", daemon=True).start()
    except Exception:  # noqa: BLE001 — keeping a replay must never raise into a turn
        logger.debug("replay on ending not started", exc_info=True)


def find_trace_by_commit(
    root: Path, branch: str, commit_id: str
) -> dict[str, Any] | None:
    """M18 §7.3 — the M17 linkage: given a landed world commit id, return the
    turn's full orchestration record (its message stream IS the determinism
    record for that commit)."""
    for trace in read_turn_traces(root, branch):
        if (trace.get("land") or {}).get("commit_id") == commit_id:
            return trace
    return None


def replay_turn_stream(bus: Any, trace: dict[str, Any]) -> int:
    """M18 §7 — replay = republish the recorded stream in order. Publishes
    every recorded bus message of the turn onto ``bus`` (fresh seq/ts; the
    originals ride along in the payload as ``replay_of_seq`` /
    ``replay_of_ts``). Returns the number republished. Subscribers see the
    exact turn again — the M17 determinism/replay surface."""
    count = 0
    for msg in trace.get("bus_messages", []) or []:
        topic = str(msg.get("topic") or "")
        payload = dict(msg.get("payload") or {})
        payload["replay_of_seq"] = msg.get("seq")
        payload["replay_of_ts"] = msg.get("ts")
        try:
            bus.publish(topic, payload)
            count += 1
        except Exception:  # noqa: BLE001 — replay must never raise mid-stream
            logger.debug("replay publish skipped for %r", topic, exc_info=True)
    return count


def read_turn_traces(root: Path, branch: str, *, last: int | None = None) -> list[dict[str, Any]]:
    """Read back turn-trace records (oldest first). ``last`` caps to the most
    recent N. Best-effort: returns [] if the file is absent/unreadable."""
    try:
        path = _trace_path(root, branch)
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return []
    records: list[dict[str, Any]] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            records.append(json.loads(ln))
        except ValueError:
            continue
    return records[-last:] if last else records
