"""The write-down after the prose, in two answers (10-22 niko): the straight one lands at once, the thinking one runs in
the background and corrects the state when it comes.

Why: on 40 real resolve beats the thinking write-down moved the clock on in 22 against the straight one's 7 (and wrote a
quarter more lines), but waiting for it held the beat — a stalled thinking call sat 40–90 s before its first token. Now the
beat ends with the straight answer, the player reads and plays on, and the thinking answer replaces it from behind.

Rules (niko 10-22):
- the player is quicker than the thinking answer → the straight answer stays and the thinking one is cut (a new turn
  starts: :func:`cut`). An answer that comes while the beat is still finishing (its own tail holds the run's lock) waits
  for the lock — up to ``transition_slow_lock_wait_s`` — and lands then; only a new line cuts it (10-23: dropping it as
  busy lost 64 % of the corrections on real deepseek)
- the thinking answer replaces the straight one: each variable it or the straight answer set goes to the thinking
  answer's value (a variable only the straight answer set goes back to where it was) — unless something else changed it
  since, then it is left alone; what the thinking answer adds beyond the straight one (files, moves, flags) lands too
- the engine's own rulings for the beat (the agreed payments, the tools' verdicts) win over both, as in the beat itself
- the player sees it: ``write_down.pending`` when the beat ends with a correction under way, then ``write_down.corrected``
  (with what changed) or ``write_down.same`` / ``.cut`` / ``.timeout`` / ``.failed``, on the session's engine/beat
- the thinking answer gets ``transition_slow_timeout_s`` (90 s) and is then dropped
"""
from __future__ import annotations

import concurrent.futures as _cf
import contextvars
import copy
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_G = threading.Lock()
_PENDING: dict[str, "Pending"] = {}
_LISTEN: dict[str, Callable[[dict[str, Any]], None]] = {}
# set by the write-down of this beat when its thinking answer went to the background; solve_turn picks it up after the apply
SLOW: "contextvars.ContextVar[_cf.Future | None]" = contextvars.ContextVar("neonrp_write_down_slow", default=None)


def _key(root: Path) -> str:
    return str(Path(root).resolve())


def listen(root: Path, fn: Callable[[dict[str, Any]], None] | None) -> None:
    """Where this run's correction events go (the session's engine/beat publisher)."""
    with _G:
        if fn is None:
            _LISTEN.pop(_key(root), None)
        else:
            _LISTEN[_key(root)] = fn


def _emit(root: Path, ev: dict[str, Any]) -> None:
    fn = _LISTEN.get(_key(root))
    if fn is None:
        return
    try:
        fn(ev)
    except Exception:  # noqa: BLE001 — an event never breaks the correction
        logger.debug("write-down event failed", exc_info=True)


_ADAPTERS: dict[str, Any] = {}
PURPOSE_HEADER = "X-Worldlines-Purpose"  # tells our relay this call is the background write-down (metered on its own)
PURPOSE = "writedown-correction"


def slow_spec(root: Path) -> str:
    """What ``turn.transition_slow_model`` names, resolved: '' (the beat's own model) · ``<preset>`` · ``<preset>:<model>``.
    ``auto`` asks the platform (``GET /v1/me/entitlements``): ``models.careful_writedown`` names the relay's model for
    it and ``usage.careful_writedown_remaining`` (null = no cap) says whether any is left → ``worldlines:<model>``;
    not signed in, nothing granted, none left, or no answer → ''."""
    from neonrp.core import beat_budget

    spec = beat_budget.transition_slow_model(root)
    if spec != "auto":
        return spec
    try:
        from neonrp.core import worldlines_auth

        ent = worldlines_auth.entitlements() or {}
    except Exception:  # noqa: BLE001
        return ""
    model = str(((ent.get("models") or {}) if isinstance(ent.get("models"), dict) else {}).get("careful_writedown") or "")
    left = ((ent.get("usage") or {}) if isinstance(ent.get("usage"), dict) else {}).get("careful_writedown_remaining")
    return f"worldlines:{model}" if model and (left is None or (isinstance(left, (int, float)) and left > 0)) else ""


def slow_adapter(root: Path, fallback: Any) -> tuple[str, Any]:
    """(spec, adapter) for the thinking answer (see :func:`slow_spec`), built once per spec and kept; '' → the beat's own
    adapter. A spec that cannot be built is logged and the beat's own model is used."""
    spec = slow_spec(root)
    if not spec:
        return "", fallback
    with _G:
        got = _ADAPTERS.get(spec)
    if got is not None:
        return spec, got
    preset, _, model = spec.partition(":")
    try:
        from neonrp.core import worldlines_auth
        from neonrp.core.hub_publish import adapter_for_preset

        got = adapter_for_preset(preset)
        if model:
            got.model = model
        if worldlines_auth.is_worldlines(getattr(got, "base_url", None)):
            ek = dict(getattr(got, "extra_kwargs", None) or {})
            ek["extra_headers"] = {**(ek.get("extra_headers") or {}), PURPOSE_HEADER: PURPOSE}
            got.extra_kwargs = ek
    except Exception as e:  # noqa: BLE001 — a missing / broken preset: the beat's own model corrects
        logger.warning("write-down slow model %r unavailable (%s): using the beat's own", spec, e)
        return "", fallback
    with _G:
        _ADAPTERS[spec] = got
    return spec, got


def run_slow(root: Path, own: Any, chat: Callable[[Any, list[str]], Any], meta: dict[str, Any], think: Any) -> Any:
    """The thinking write-down: on the chosen model; refused for money there (the account's careful corrections are
    used up) → on the beat's own model instead, ``meta.fallback`` says why. A refusal here is not the player's last
    billing stop (it is handled here)."""
    from neonrp.core import billing_stop

    spec, a = slow_adapter(root, own)
    meta["model"] = spec
    prev = billing_stop.last()
    errs: list[str] = []
    with think(True):
        out = chat(a, errs)
    if a is own or (out[0] or "").strip():
        return out
    stop = next((s for s in (billing_stop.from_text(e) for e in errs) if s is not None), None)
    billing_stop.restore(prev)
    meta["fallback"] = stop.code if stop is not None else "failed"
    with think(True):
        return chat(own, [])


def launch(call: Callable[[], Any]) -> _cf.Future:
    """Run ``call`` on its own thread, outside the beat (an empty context: no beat budget caps it, thinking is on by
    default); the caller gets a future and never waits for it."""
    fut: _cf.Future = _cf.Future()

    def body() -> None:
        try:
            fut.set_result(contextvars.Context().run(call))
        except BaseException as e:  # noqa: BLE001 — handed to whoever reads the future
            fut.set_exception(e)

    threading.Thread(target=body, name="write-down-slow", daemon=True).start()
    return fut


@dataclass
class Pending:
    root: Path
    turn: int
    future: _cf.Future
    timeout: float
    base: list[dict[str, Any]]  # the beat's rulings: they win over both answers
    fast_ops: list[dict[str, Any]]  # what the straight answer landed (accepted ops)
    pre: dict[str, Any]  # variables before the beat's apply
    post: dict[str, Any]  # variables right after it
    writers: str = "on"
    max_ops: int = 40
    branch: str = "main"
    meta: dict[str, Any] = field(default_factory=dict)  # model the thinking answer ran on · fallback (filled by run_slow)
    t0: float = field(default_factory=time.monotonic)
    cut_why: str | None = None
    state: str = "running"  # running · corrected · same · cut · timeout · failed


def register(p: Pending) -> None:
    """The beat ended with the straight answer; watch the thinking one."""
    with _G:
        old = _PENDING.get(_key(p.root))
        if old is not None and old.state == "running":
            old.cut_why = "superseded"
        _PENDING[_key(p.root)] = p
    _emit(p.root, {"kind": "write_down.pending", "turn": p.turn, "timeout_s": p.timeout})
    threading.Thread(target=_watch, args=(p,), name="write-down-watch", daemon=True).start()


def cut(root: Path, why: str = "next_turn") -> None:
    """A new turn starts: a correction still under way for this run is dropped (the straight answer stays)."""
    with _G:
        p = _PENDING.pop(_key(root), None)
        if p is None or p.state != "running":
            return
        p.cut_why = why
    _emit(root, {"kind": "write_down.cut", "turn": p.turn, "why": why})


def pending(root: Path) -> Pending | None:
    with _G:
        return _PENDING.get(_key(root))


def _end(p: Pending, state: str, **extra: Any) -> None:
    with _G:
        if _PENDING.get(_key(p.root)) is p:
            _PENDING.pop(_key(p.root), None)
        already = p.state != "running"
        p.state = state
    if not already and state != "cut":  # a cut was announced when it happened
        _emit(p.root, {"kind": f"write_down.{state}", "turn": p.turn, **{k: v for k, v in p.meta.items() if v}, **extra})


def _watch(p: Pending) -> None:
    from neonrp.core import run_lock

    try:
        raw, _ms, _usage = p.future.result(timeout=max(0.0, p.timeout - (time.monotonic() - p.t0)))
    except _cf.TimeoutError:
        _end(p, "timeout")
        return
    except Exception as e:  # noqa: BLE001
        _end(p, "failed", why=str(e)[:200])
        return
    from neonrp.core import beat_budget

    wait = beat_budget.transition_slow_lock_wait_s(p.root)
    until = time.monotonic() + max(0.0, wait)
    while True:
        if p.cut_why:  # the next line started (it took the lock, then cut this): the straight answer stays
            _end(p, "cut")
            return
        with run_lock.try_hold(p.root, alone=False) as ok:  # only this run: another run's turn in this process is not ours
            if ok:
                if p.cut_why:
                    _end(p, "cut")
                    return
                try:
                    changes = land(p, raw or "")
                except Exception as e:  # noqa: BLE001 — a failed correction leaves the straight answer as it is
                    logger.warning("write-down correction failed: %s", e, exc_info=True)
                    _end(p, "failed", why=str(e)[:200])
                    return
                break
        if time.monotonic() >= until:  # held all that while and no new line: something else is writing the run
            with _G:
                p.cut_why = p.cut_why or "busy"
            _emit(p.root, {"kind": "write_down.cut", "turn": p.turn, "why": "busy"})
            _end(p, "cut")
            return
        time.sleep(0.05)  # the beat's own tail still holds the lock: wait for it
    _end(p, "corrected" if changes["applied"] else "same", **changes)


def correction_ops(p: Pending, slow_ops: list[dict[str, Any]], reg: Any) -> list[dict[str, Any]]:
    """What turns the state the straight answer left into the thinking answer's (see the module's rules)."""
    from neonrp.core.turn_v3 import _same_target

    slow = [o for o in slow_ops if not any(_same_target(o, b, reg) for b in p.base)]
    ruled = {str(b.get("var")) for b in p.base if b.get("var")}
    now = {k: v.value for k, v in reg.variables.items()}
    s_vars = {str(o["var"]): o.get("value") for o in slow if o.get("op") == "set" and o.get("var")}
    f_vars = {str(o["var"]): o.get("value") for o in p.fast_ops if o.get("op") == "set" and o.get("var")}
    out: list[dict[str, Any]] = []
    for v in sorted(set(s_vars) | set(f_vars)):
        if v in ruled or v not in reg.variables or now.get(v) != p.post.get(v):  # ruled, unknown, or changed since
            continue
        target = s_vars[v] if v in s_vars else p.pre.get(v)
        if target != now.get(v):
            out.append({"op": "set", "var": v, "value": target})

    def is_player_move(o: dict[str, Any]) -> bool:
        return o.get("op") == "move_to" and str(o.get("who") or "") in ("player", "")

    s_move = next((o for o in slow if is_player_move(o)), None)
    f_move = next((o for o in p.fast_ops if is_player_move(o)), None)
    if now.get("location") == p.post.get("location") and "location" not in ruled:
        if s_move is not None and (f_move is None or str(s_move.get("to")) != str(f_move.get("to"))):
            out.append(dict(s_move))
        elif s_move is None and f_move is not None and p.pre.get("location") not in (None, now.get("location")):
            out.append({"op": "move_to", "who": "player", "to": p.pre.get("location")})
    for o in slow:  # the rest (files, other movers, flags): what the straight answer did not do
        if (o.get("op") == "set" and o.get("var")) or is_player_move(o):
            continue
        if not any(_same_target(o, f, reg) for f in p.fast_ops):
            out.append(dict(o))
    return out


def land(p: Pending, raw: str) -> dict[str, Any]:
    """Verify and apply the correction (the run's lock is held). → what changed, for the event."""
    from neonrp.core.registry import load_registry
    from neonrp.core.sdk import apply, verify
    from neonrp.core.turn_v3 import parse_transition

    reg = load_registry(p.root)
    ops = correction_ops(p, parse_transition(raw), reg)
    if not ops:
        return {"applied": [], "refused": []}
    vr = verify(p.root, ops, reg, max_ops=p.max_ops)
    accepted = [o for o in vr.accepted if o.get("op") != "need"]
    ar = apply(p.root, accepted, reg, turn=p.turn, refused=vr.refused, writers=p.writers, ticks=False)
    out = {"applied": list(ar.applied), "created": list(ar.created), "refused": list(ar.refused),
           "gained": list(ar.gained), "lost": list(ar.lost)}
    _amend_trace(p, out, dict(ar.variables))
    return out


def _amend_trace(p: Pending, changes: dict[str, Any], variables: dict[str, Any]) -> None:
    """The turn's record (/traces, replays) ends on the corrected state: its changes, marked, and the variables after."""
    from neonrp.core.orchestration_trace import amend_turn_trace

    def edit(rec: dict[str, Any]) -> None:
        rec["write_down"] = {"state": "corrected", **{k: v for k, v in changes.items() if v}}
        ap = rec.get("apply")
        if isinstance(ap, dict):
            ap["applied"] = list(ap.get("applied") or []) + [{**a, "corrected": True} for a in changes.get("applied") or []]
            ap["variables"] = variables

    amend_turn_trace(p.root, p.branch, p.turn, edit)


def snapshot(reg: Any) -> dict[str, Any]:
    return {k: copy.deepcopy(v.value) for k, v in reg.variables.items()}
