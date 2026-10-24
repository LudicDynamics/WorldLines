"""A beat's time budget (10-14: 「一拍的执行框架应该在 10 秒左右,不会超 20 秒,超过 20 秒可以直接 timeout」).

Every beat of a turn — the planning talk, the characters' own turns (S2), the world's narration — runs inside
:func:`beat`. It sets a wall-clock deadline that the model calls under it read themselves:

- each LLM call's request timeout is ``min(call cap, what is left)`` and the SDK does not retry on its own;
- the retry ladder stops when the beat is over (no 60 s read timeout × SDK retries × our retries — the 70–190 s
  calls of the 10-13 benchmark);
- a stream stops at the deadline, and a stalled stream (no chunk for ``stall`` seconds) is not followed by a whole
  plain call when nothing is left;
- tool loops stop calling the model and finish with what they have.

Nothing is killed: there are no threads to cancel in the browser (Pyodide runs every "thread" inline, the network is a
synchronous XHR) or on iOS, so the budget is cooperative — every call checks it before it starts and is sized to what
is left. A call that cannot start fails at once like any failed call, and the caller's existing fallback runs
(the character this beat is skipped, the planning talk hands back what was said, the world settles with its prose).

The whole turn has a budget too (10-14: 「整回合总上限 30 秒」): :func:`turn` opens it, and every beat inside
shares what is left — a beat ends at ``min(its own 20 s, the turn's end − reserve)``. The beats before the world's
(the planning talk, the characters' turns) keep ``world_reserve_s`` back for it, and the world's prose keeps
``settle_s`` back for its state transition, so the turn still lands inside its budget. Code between beats is not timed.

What timed out is recorded (:func:`note`) in the turn's collector (:func:`collect`) and reaches the turn result as
``timeouts`` (the frontend can say 「这一拍超时了」; ``turn: true`` when it was the turn's budget that cut the beat).
The budget lives in context variables; worker threads get it through :func:`carry`. Outside a beat (world creation,
authoring, tests) nothing changes.

Settings (env first, then the run's engine config ``turn.beat_timeout_s`` …):
    NEONRP_TURN_TIMEOUT_S   30   the whole turn, all its beats (0 = off)
    NEONRP_TURN_WORLD_RESERVE_S 10 what the beats before the world's leave for it
    NEONRP_BEAT_TIMEOUT_S   20   one beat (0 = off)
    NEONRP_LLM_CALL_TIMEOUT_S 20 one model call inside a beat
    NEONRP_LLM_STALL_S      15   a stream with no chunk for this long has stalled
    NEONRP_BEAT_SETTLE_S    8    what the world's state transition still gets after its beat ran out
    NEONRP_NARRATE_THINKING 0    the world's beat lets the model think before it writes (1 = on; off: the first word
                                 comes at once — 10-19 N2, thinking ate the turn in a quarter to a half of the beats)
    NEONRP_PLAN_THINKING    0    a node kind's beat before the world (the planning talk) thinks first (1 = on; off:
                                 10-19 N2 M6, its host thought 1.4 s / p90 2.1 s of the time before the first word)
"""
from __future__ import annotations

import contextvars
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from neonrp.core.llm_errors import LLMError

DEFAULT_TURN_S = 30.0
DEFAULT_WORLD_RESERVE_S = 10.0
DEFAULT_BEAT_S = 20.0
DEFAULT_CALL_S = 20.0
DEFAULT_STALL_S = 15.0
DEFAULT_SETTLE_S = 8.0
MIN_RETRY_S = 2.0  # less than this left: a retry would only time out again


class BeatTimeout(LLMError):
    """The beat's time is over: the call was not made (or was cut). Not retryable within this beat."""

    retryable = False


@dataclass
class _Beat:
    name: str
    deadline: float
    sink: list[dict[str, Any]] | None
    t0: float = field(default_factory=time.monotonic)
    noted: set[str] = field(default_factory=set)
    by_turn: bool = False  # its deadline is the turn's (what was left of the turn was shorter than the beat)


@dataclass
class _Turn:
    deadline: float
    t0: float = field(default_factory=time.monotonic)


_CUR: contextvars.ContextVar[_Beat | None] = contextvars.ContextVar("neonrp_beat", default=None)
_TURN: contextvars.ContextVar[_Turn | None] = contextvars.ContextVar("neonrp_turn", default=None)
_SINK: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("neonrp_beat_sink", default=None)
_CALLS: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("neonrp_beat_calls", default=None)
_CAP: contextvars.ContextVar[float | None] = contextvars.ContextVar("neonrp_call_cap", default=None)


def _env_float(name: str, default: float) -> float:
    try:
        v = os.environ.get(name, "")
        return float(v) if str(v).strip() else default
    except ValueError:
        return default


def _cfg(root: Path | None, key: str) -> Any:
    if root is None:
        return None
    try:
        from neonrp.core import engine_config

        return engine_config.get(root, key, None)
    except Exception:  # noqa: BLE001 — a missing / broken config is the default
        return None


def _setting(env: str, key: str, default: float, root: Path | None) -> float:
    if os.environ.get(env, "").strip():
        return _env_float(env, default)
    v = _cfg(root, key)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def turn_timeout_s(root: Path | None = None) -> float:
    return _setting("NEONRP_TURN_TIMEOUT_S", "turn.turn_timeout_s", DEFAULT_TURN_S, root)


def world_reserve_s(root: Path | None = None) -> float:
    return _setting("NEONRP_TURN_WORLD_RESERVE_S", "turn.world_reserve_s", DEFAULT_WORLD_RESERVE_S, root)


def beat_timeout_s(root: Path | None = None) -> float:
    return _setting("NEONRP_BEAT_TIMEOUT_S", "turn.beat_timeout_s", DEFAULT_BEAT_S, root)


def call_cap_s(root: Path | None = None) -> float:
    cap = _CAP.get()
    return cap if cap is not None else _setting("NEONRP_LLM_CALL_TIMEOUT_S", "turn.llm_call_timeout_s", DEFAULT_CALL_S, root)


@contextmanager
def call_cap(seconds: float) -> Any:
    """Calls made inside may take up to ``seconds`` (instead of the per-call cap) — the write-down's thinking (10-21)."""
    tok = _CAP.set(float(seconds))
    try:
        yield
    finally:
        _CAP.reset(tok)


def transition_think_wait_s(root: Path | None = None) -> float:
    """How long the write-down waits for its thinking answer before it takes the straight one sent with it (10-21:
    「cot和无思考可以并发,然后如果是40秒或者1分钟超时的话,就fall back」; the prose is on screen already)."""
    return _setting("NEONRP_TRANSITION_THINK_WAIT_S", "turn.transition_think_wait_s", 40.0, root)


def transition_async(root: Path | None = None) -> bool:
    """The write-down after the prose lands its straight answer at once and the thinking one corrects it from the
    background (10-22: the thinking answer is fuller — time moved on in 22 of 40 beats against 7 — but waited for, a
    stalled one held the beat 40–90 s). Off: the old race (the thinking answer within ``transition_think_wait_s``)."""
    return _setting("NEONRP_TRANSITION_ASYNC", "turn.transition_async", 1.0, root) > 0


def transition_slow_timeout_s(root: Path | None = None) -> float:
    """How long the background thinking write-down may run before it is dropped (and the straight answer stays)."""
    return _setting("NEONRP_TRANSITION_SLOW_TIMEOUT_S", "turn.transition_slow_timeout_s", 90.0, root)


def transition_slow_lock_wait_s(root: Path | None = None) -> float:
    """How long a correction that came back while the beat was still finishing (the run's lock held by its own tail) waits
    for the lock before it is dropped as ``busy``. 10-23 real deepseek: corrections came 0.5–0.8 s after turn_done, while
    the tail still held the lock — 7 of 11 were dropped as busy, none was a player moving on first."""
    return _setting("NEONRP_TRANSITION_SLOW_LOCK_WAIT_S", "turn.transition_slow_lock_wait_s", 15.0, root)


def transition_slow_model(root: Path | None = None) -> str:
    """The model preset the background (thinking) write-down runs on — '' = the beat's own model. 10-22: the straight
    answer stays on the fast cheap one (deepseek), the correction may go to a more careful one behind a gateway
    (gemini-3.8-flash via Cloudflare: 40 beats, places 38/38 against 35/38, at ~20x the cost).
    Default ``auto`` (10-23, the platform's careful write-down is live): the account's entitlement decides
    (core/write_down_async.slow_spec) — not signed in, none granted or none left = the beat's own model. ``""`` in the
    world's settings (or the env) = always the beat's own."""
    env = os.environ.get("NEONRP_TRANSITION_SLOW_MODEL")
    if env is not None and env.strip():
        return env.strip()
    v = _cfg(root, "turn.transition_slow_model")
    return str(v).strip() if isinstance(v, str) else "auto"


def stall_s(root: Path | None = None) -> float:
    return _setting("NEONRP_LLM_STALL_S", "turn.llm_stall_s", DEFAULT_STALL_S, root)


def settle_s(root: Path | None = None) -> float:
    return _setting("NEONRP_BEAT_SETTLE_S", "turn.beat_settle_s", DEFAULT_SETTLE_S, root)


def narrate_thinking(root: Path | None = None) -> bool:
    return _setting("NEONRP_NARRATE_THINKING", "turn.narrate_thinking", 0.0, root) > 0


def transition_floor_s(root: Path | None = None) -> float:
    """What the write-down after the prose is sure of (10-21 fixb: with thinking on and a slow API, the transition got
    the 8–9 s the prose left over, timed out, and the beat's money, sleep and moves were silently lost)."""
    t = turn_timeout_s(root)
    want = _setting("NEONRP_TRANSITION_FLOOR_S", "turn.transition_floor_s", 15.0, root)
    return min(want, 0.5 * t) if t > 0 else want


def transition_thinking(root: Path | None = None) -> bool:
    """The write-down after the prose thinks by default (10-20 全线: without it a bite of bread or a chewed herb was in
    the prose but never left the bag — J1 / J7 / S3 0 of 6; thinking: 5 of 6, about +1 s after the prose, not before it)."""
    return _setting("NEONRP_TRANSITION_THINKING", "turn.transition_thinking", 1.0, root) > 0


def plan_thinking(root: Path | None = None) -> bool:
    return _setting("NEONRP_PLAN_THINKING", "turn.plan_thinking", 0.0, root) > 0


@contextmanager
def collect(sink: list[dict[str, Any]] | None = None) -> Iterator[list[dict[str, Any]]]:
    """The turn's record of what timed out: every beat inside appends to it."""
    sink = sink if sink is not None else []
    tok = _SINK.set(sink)
    try:
        yield sink
    finally:
        _SINK.reset(tok)


@contextmanager
def turn(seconds: float | None = None, *, root: Path | None = None,
         sink: list[dict[str, Any]] | None = None) -> Iterator[list[dict[str, Any]]]:
    """One turn: its beats share ``seconds`` (default ``turn_timeout_s``; <= 0 = no turn budget, beats keep their own),
    and what timed out is collected (as :func:`collect`)."""
    s = turn_timeout_s(root) if seconds is None else float(seconds)
    tok = _TURN.set(_Turn(deadline=time.monotonic() + s) if s > 0 else None)
    ctok = _CALLS.set([])
    try:
        with collect(sink) as got:
            yield got
    finally:
        _CALLS.reset(ctok)
        _TURN.reset(tok)


def talk_seconds(root: Path | None = None) -> float:
    """A beat that may be the whole turn (the planning talk: when it does not resolve, no world beat follows it — 10-19): it may use the turn's whole budget, not one beat's. Outside a turn budget (off): one beat's."""
    t = turn_timeout_s(root)
    return t if t > 0 else beat_timeout_s(root)


def carve(reserve: float, where: str = "carve") -> bool:
    """This beat has just decided the turn goes on to the world's beat: from now on it ends ``reserve`` seconds before
    the turn does, so the world's beat gets its share (10-19: a talk that used the turn's whole budget, then advanced).
    False (nothing changed, noted) when less than ``reserve`` is left of the turn — the caller does not go on this turn.
    No turn budget: True."""
    t, b = _TURN.get(), _CUR.get()
    if t is None:
        return True
    if t.deadline - time.monotonic() < reserve:
        note(where)
        return False
    if b is not None:
        b.deadline = min(b.deadline, t.deadline - max(0.0, reserve))
    return True


def world_floor_s(root: Path | None = None) -> float:
    """What the world's beat is sure of when it starts: its reserve + the settle, at most 60 % of the turn (30 s → 18 s)."""
    t = turn_timeout_s(root)
    want = world_reserve_s(root) + settle_s(root)
    return min(want, 0.6 * t) if t > 0 else want


def floor(seconds: float, where: str = "floor") -> None:
    """The turn has at least ``seconds`` left from now: the world's beat starts with its own share even when the beats
    before it ran long (10-19 N2 M5: talk + characters + Jev took 9–20 s, the 10 s they keep back did not survive the
    code between beats, and the world's prose got 9 ms – 1 s → 31 of 44 resolve beats timed out with nothing written).
    Extending is recorded with the turn's calls (``extended_ms``: the turn then runs past its budget by that much — not
    a timeout, nothing ran out). No turn budget: nothing changes."""
    t = _TURN.get()
    if t is None or seconds <= 0:
        return
    want = time.monotonic() + seconds
    if t.deadline < want:
        calls = _CALLS.get()
        if calls is not None:
            calls.append({"beat": where, "at_ms": round((time.monotonic() - t.t0) * 1000), "extended_ms": round((want - t.deadline) * 1000)})
        t.deadline = want


def ensure(seconds: float, where: str = "ensure") -> None:
    """This beat (and the turn) have at least ``seconds`` left from now — like :func:`floor`, for the beat itself."""
    b = _CUR.get()
    if b is None or seconds <= 0:
        return
    want = time.monotonic() + seconds
    t = _TURN.get()
    if t is not None and t.deadline < want:
        calls = _CALLS.get()
        if calls is not None:
            calls.append({"beat": where, "at_ms": round((time.monotonic() - t.t0) * 1000), "extended_ms": round((want - t.deadline) * 1000)})
        t.deadline = want
    if b.deadline < want:
        b.deadline = want


def log_call(**entry: Any) -> None:
    """Record one model call of this turn (which beat, ms to the first chunk, ms in all …) for the turn's trace."""
    calls = _CALLS.get()
    if calls is not None:
        b = _CUR.get()
        calls.append({"beat": b.name if b is not None else None, **entry})


def calls() -> list[dict[str, Any]]:
    """This turn's model calls so far (:func:`log_call`)."""
    return list(_CALLS.get() or [])


def turn_remaining() -> float | None:
    """Seconds left in this turn (None outside a turn budget)."""
    t = _TURN.get()
    return None if t is None else t.deadline - time.monotonic()


@contextmanager
def beat(name: str, seconds: float | None = None, *, root: Path | None = None,
         reserve: float = 0.0) -> Iterator[_Beat | None]:
    """Run a beat under a deadline. A beat inside another never outlives it; inside a :func:`turn` it ends ``reserve``
    seconds before the turn does (what is kept for the beats after it). ``seconds`` <= 0 (or the setting 0) = no beat
    deadline of its own (the turn's still holds)."""
    s = beat_timeout_s(root) if seconds is None else float(seconds)
    t = _TURN.get()
    if s <= 0 and t is None:
        yield None
        return
    outer = _CUR.get()
    now = time.monotonic()
    deadline = now + s if s > 0 else float("inf")
    by_turn = False
    if t is not None and t.deadline - max(0.0, reserve) < deadline:
        deadline, by_turn = t.deadline - max(0.0, reserve), True
    if outer is not None and outer.deadline <= deadline:
        deadline, by_turn = outer.deadline, outer.by_turn
    b = _Beat(name=name, deadline=deadline, sink=_SINK.get() if outer is None else outer.sink, by_turn=by_turn)
    tok = _CUR.set(b)
    try:
        yield b
    finally:
        _CUR.reset(tok)


@contextmanager
def at_least(seconds: float) -> Iterator[None]:
    """Within a beat, give the next calls at least ``seconds`` more (the world's state transition after its prose:
    the turn must still land). No beat: nothing changes."""
    b = _CUR.get()
    if b is None or seconds <= 0:
        yield
        return
    old = b.deadline
    b.deadline = max(old, _in_turn(time.monotonic() + seconds))
    try:
        yield
    finally:
        b.deadline = old


def grant(seconds: float, where: str = "settle") -> None:
    """Give the rest of this beat at least ``seconds`` more, for good (the world's state transition after its prose:
    the turn must still land). Noted when the beat had already run out. No beat: nothing changes."""
    b = _CUR.get()
    if b is None or seconds <= 0:
        return
    if b.deadline <= time.monotonic():
        note(where)
    b.deadline = max(b.deadline, _in_turn(time.monotonic() + seconds))


def _in_turn(deadline: float) -> float:
    """A grant never outlives the turn (10-14: the whole turn ≤ turn_timeout_s)."""
    t = _TURN.get()
    return deadline if t is None else min(deadline, t.deadline)


def timed_out(name: str | None = None) -> bool:
    """Did a beat (this one by name, or any) run out of time in this turn?"""
    b = _CUR.get()
    sink = (b.sink if b is not None else None) or _SINK.get() or []
    return any(name is None or h.get("beat") == name for h in sink) or (b is not None and bool(b.noted) and (name is None or b.name == name))


def current() -> _Beat | None:
    return _CUR.get()


def remaining() -> float | None:
    """Seconds left in this beat (None outside a beat)."""
    b = _CUR.get()
    return None if b is None else b.deadline - time.monotonic()


def expired(margin: float = 0.0) -> bool:
    r = remaining()
    return r is not None and r <= margin


def call_timeout(root: Path | None = None) -> float | None:
    """The timeout for one model call made now (None outside a beat)."""
    r = remaining()
    if r is None:
        return None
    return max(0.0, min(call_cap_s(root), r))


def note(where: str, **extra: Any) -> None:
    """Record that ``where`` in this beat ran out of time (once per beat and place)."""
    b = _CUR.get()
    if b is None or where in b.noted:
        return
    b.noted.add(where)
    if b.sink is not None:
        b.sink.append({"beat": b.name, "where": where, "ms": round((time.monotonic() - b.t0) * 1000),
                       **({"turn": True} if b.by_turn else {}), **extra})


def check(where: str) -> None:
    """Raise :class:`BeatTimeout` (and note it) when the beat is over."""
    if expired():
        note(where)
        raise BeatTimeout(f"beat timeout ({where})")


def hits() -> list[dict[str, Any]]:
    """What timed out so far in this turn."""
    s = _SINK.get()
    return list(s or [])


def carry(fn: Callable[..., Any]) -> Callable[..., Any]:
    """``fn`` to run in a worker thread with this beat and turn (each call in its own copy of the context)."""
    ctx = contextvars.copy_context()

    def run(*a: Any, **k: Any) -> Any:
        return ctx.copy().run(fn, *a, **k)

    return run
