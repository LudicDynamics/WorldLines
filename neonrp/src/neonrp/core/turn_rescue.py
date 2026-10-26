"""A line the engine could not finish in time is not thrown away (10-25 niko: 超时 / 中断时,已经生成的部分直接显示出来,
可以当成这回合的结果;再给「继续生成」和「重来」).

Three pieces, one run at a time (in memory: the engine process that ran the line):

- **before the line** (:func:`capture`): the run's files as they are — the world, the souls, the session log, the
  traces, the commit refs (not the pictures, not the commits' content-addressed blobs). A failed line puts them back
  (:func:`restore`): 「你的话没有用掉」 is then true of the clock and the board too.
- **a cut line** (:func:`cut_of`): the beat budget cut the world's prose (or a stream broke) after some text. That
  prose already landed with the state transition written from it — text and state agree. The page marks it
  「生成中断」 and the player can go on from it as it is.
- **the two buttons**: 「重来」 = :func:`restore` (back to before the line; the line returns to the input box, as it was or
  to be changed). 「继续生成」 = :func:`continue_turn`: the narrator gets what it wrote as the final prefix and only
  appends (the same continuation contract as after a tool request); a state transition is written from the
  continuation alone and applied on top (no clock tick — the turn's ticks ran), and the turn's record and the
  session's last reply are amended in place. A continuation that is cut again can be continued again.

What a continuation needs (the narrator's system prompt, a user block that re-packs the world as it is now, the
history) is offered by the world's beat when it ends (core/turn_v3.solve_turn → :func:`offer`).

A node kind's beat (the planning talk) cut by time — mid-reply, or settled with no time left for the world's beat —
lands what was said. Its 「继续生成」 is the same line played on (:func:`resuming_talk`): no new player message, no new
snapshot; the node kind reads :func:`resuming` and goes on from its saved talk (or straight to the world's beat when
the talk had settled), instead of talking the line over from the start (10-25 niko: 已经生成的内容不要浪费了).
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# what a snapshot leaves out: pictures (written by their own tools, harmless when kept), content-addressed commit blobs
# (immutable; an orphan is never read), logs
_SKIP_DIRS = ("assets", ".neonrp/commits/blobs", ".neonrp/logs")
_SKIP_NAMES = ("__pycache__", ".DS_Store")
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024  # a run bigger than this is not snapshotted (重来 is then not offered)

# where a beat's hit means its prose stopped before it was done (core/beat_budget.note)
CUT_WHERE = ("llm.stream", "stream.cut", "world.continue", "stream.fallback", "llm.call", "wrap_up")
# a node kind's beat (the talk) also stops short when it settled with no time left for the world's beat
TALK_CUT_WHERE = CUT_WHERE + ("plan.advance",)

_RESUMING: ContextVar[str | None] = ContextVar("neonrp_rescue_resuming", default=None)


@contextmanager
def resuming_talk(text: str):
    """The line ``text`` played on after its talk was cut (「继续生成」): read by the turn (no new player message) and
    by the node kind whose beat was cut (core/node_kinds: it goes on from its saved talk)."""
    tok = _RESUMING.set(str(text or ""))
    try:
        yield
    finally:
        _RESUMING.reset(tok)


def resuming() -> str | None:
    """The line being played on (:func:`resuming_talk`), or None for a line of its own."""
    return _RESUMING.get()


@dataclass
class _Line:
    text: str
    branch: str
    files: dict[str, bytes] | None
    resume: dict[str, Any] | None = None  # offered by the world's beat of this line
    landed: bool = False
    cut: list[dict[str, Any]] = field(default_factory=list)
    continued: int = 0


_LINES: dict[str, _Line] = {}
_LOCK = threading.Lock()


def _key(root: Path) -> str:
    return str(Path(root).resolve())


def _skipped(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in _SKIP_DIRS)


def _walk(root: Path) -> list[str]:
    out: list[str] = []
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root).replace(os.sep, "/")
        rel_d = "" if rel_d == "." else rel_d
        dirs[:] = [x for x in dirs if x not in _SKIP_NAMES and not _skipped(f"{rel_d}/{x}".lstrip("/"))]
        for f in files:
            if f in _SKIP_NAMES or f.endswith(".tmp"):
                continue
            out.append(f"{rel_d}/{f}".lstrip("/"))
    return out


def capture(root: Path, text: str, *, branch: str = "main") -> bool:
    """The run as it is before ``text`` is played. False (and no 重来 for this line) when it cannot be read whole."""
    root = Path(root)
    files: dict[str, bytes] | None = {}
    total = 0
    try:
        for rel in _walk(root):
            try:
                b = (root / rel).read_bytes()
            except OSError:
                continue
            total += len(b)
            if total > MAX_SNAPSHOT_BYTES:
                files = None
                break
            files[rel] = b
    except OSError:
        files = None
    with _LOCK:
        _LINES[_key(root)] = _Line(text=str(text or ""), branch=branch, files=files)
    return files is not None


def line(root: Path) -> _Line | None:
    with _LOCK:
        return _LINES.get(_key(root))


def forget(root: Path) -> None:
    with _LOCK:
        _LINES.pop(_key(root), None)


def offer(root: Path, **resume: Any) -> None:
    """The world's beat of the line being played says how its prose would be continued (core/turn_v3.solve_turn)."""
    ln = line(root)
    if ln is not None:
        ln.resume = dict(resume)


def restore(root: Path) -> bool:
    """The run's files back to before the line (:func:`capture`): changed ones rewritten, new ones removed. The caller
    holds the run (no turn, no background write-down) and reloads its session afterwards."""
    root = Path(root)
    ln = line(root)
    if ln is None or ln.files is None:
        return False
    snap = ln.files
    for rel in _walk(root):
        if rel not in snap:
            try:
                (root / rel).unlink()
            except OSError:
                logger.debug("rescue: could not remove %s", rel, exc_info=True)
    for rel, b in snap.items():
        p = root / rel
        try:
            if p.exists() and p.read_bytes() == b:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + ".rescue.tmp")
            tmp.write_bytes(b)
            tmp.replace(p)
        except OSError:
            logger.warning("rescue: could not restore %s", rel, exc_info=True)
            return False
    ln.landed, ln.resume, ln.cut = False, None, []
    return True


def cut_of(timeouts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The hits of a turn that cut a beat short (or wrapped the turn up): the world's prose, or a node kind's talk."""
    return [dict(h) for h in timeouts or [] if isinstance(h, dict) and h.get("beat")
            and h.get("where") in (CUT_WHERE if h.get("beat") == "world" else TALK_CUT_WHERE)]


def _mode(ln: _Line) -> str | None:
    """How the line goes on: ``world`` (its prose, offered by the world's beat) · ``talk`` (its talk was the line's
    last beat — no world's beat ran) · None."""
    if any(h.get("beat") == "world" for h in ln.cut) and ln.resume is not None:
        return "world"
    if any(h.get("beat") != "world" for h in ln.cut) and ln.resume is None:
        return "talk"
    return None


def after_turn(root: Path, *, success: bool, timeouts: list[dict[str, Any]] | None, resumed: bool = False) -> dict[str, Any]:
    """What the page may offer for the line just played: {cut: [...], redo, continue, resume} (cut empty = it finished).
    ``resumed``: the line played on after a cut talk — the world's beat it reached offers anew; one that failed leaves
    the line as it was (still cut, still to be continued)."""
    ln = line(root)
    if ln is None:
        return {"cut": [], "redo": False, "continue": False, "text": "", "resume": None}
    if resumed:
        if not success:
            return state(root)
        ln.continued += 1
    ln.landed = bool(success)
    ln.cut = cut_of(timeouts) if success else []
    return state(root)



def state(root: Path) -> dict[str, Any]:
    ln = line(root)
    if ln is None:
        return {"cut": [], "redo": False, "continue": False, "text": ""}
    mode = _mode(ln) if ln.landed else None
    return {"cut": list(ln.cut), "redo": ln.files is not None, "text": ln.text, "continued": ln.continued,
            "continue": mode is not None, "resume": mode}


def _amend_last_trace(root: Path, branch: str, fn: Callable[[dict[str, Any]], None]) -> bool:
    import json

    from neonrp.core.orchestration_trace import _trace_path

    path = _trace_path(root, branch)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for i in range(len(lines) - 1, -1, -1):
        if not lines[i].strip():
            continue
        rec = json.loads(lines[i])
        fn(rec)
        lines[i] = json.dumps(rec, ensure_ascii=False)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)
        return True
    return False


def _amend_last_reply(root: Path, branch: str, old: str, new: str) -> bool:
    """The session log's last reply: ``old`` (the prose as it was cut) becomes ``new`` (prose + continuation)."""
    import json

    from neonrp.core.session import get_session_path

    path = get_session_path(root, branch)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for i in range(len(lines) - 1, -1, -1):
        try:
            rec = json.loads(lines[i])
        except ValueError:
            continue
        if rec.get("role") != "assistant":
            continue
        rec["content"] = grow(str(rec.get("content") or ""), old, new)
        lines[i] = json.dumps(rec, ensure_ascii=False)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)
        return True
    return False


def grow(text: str, old: str, new: str) -> str:
    """``text`` with its copy of ``old`` (at the end, or its last one) replaced by ``new``; appended when absent."""
    if not old:
        return (text.rstrip("\n") + "\n\n" + new) if text.strip() else new
    if text.endswith(old):
        return text[: len(text) - len(old)] + new
    k = text.rfind(old)
    if k >= 0:
        return text[:k] + new + text[k + len(old):]
    return text.rstrip("\n") + "\n" + new[len(old):].lstrip("\n") if new.startswith(old) else text


def continue_turn(root: Path, *, on_text: Callable[[str], None] | None = None,
                  messages: list[Any] | None = None) -> dict[str, Any]:
    """「继续生成」: the cut prose of the last line goes on from where it stopped (see the module doc). Run while holding
    the run. → {ok, text: the continuation as shown, replaced_last: its first line restates the cut last line in full,
    narration: the whole prose, options, applied, cut: [...] (cut again), timeouts} or {ok: False, error}."""
    import re

    from neonrp import prompts as _prompts
    from neonrp.core import beat_budget as _bb
    from neonrp.core import turn_v3 as _tv3
    from neonrp.core.adv import narrate_lang_line, pack_ops_lines
    from neonrp.core.registry import load_registry
    from neonrp.core.sdk import apply, identity_gate, verify

    root = Path(root)
    ln = line(root)
    st = state(root)
    if ln is None or not st["continue"]:
        return {"ok": False, "error": "nothing to continue"}
    r = ln.resume or {}
    prefix = str(r.get("narration") or "")
    old = str(r.get("shown") or prefix)  # what the record and the log hold now (the beat's short line when nothing was written)
    adapter, system, block = r["adapter"], r["system"], r["block"]
    lang, narr_lang = str(r.get("lang") or "zh"), str(r.get("narr_lang") or "en")
    T = _tv3._T(lang)
    _tv3._SECTIONS["lang"] = lang
    _tv3._HISTORY_TURNS = list(r.get("history") or [])
    skip = {x.strip() for x in prefix.splitlines() if x.strip()}
    out_state: dict[str, Any] = {}
    with _bb.turn(root=root) as hits:
        with _bb.beat("world", root=root, reserve=_bb.settle_s(root)):
            _tv3.STREAM.update(on_text=on_text, on_event=None, shown=False, skip=skip or None, tail="", tier=None)
            try:
                out, _ms, _usage = _tv3.solve(adapter, system, block(prefix))
            finally:
                _tv3.STREAM.update(on_text=None, on_event=None, shown=False, skip=None)
            raw = out.raw or ""
            cont = _tv3.drop_restated(prefix, out.narration) if prefix else (out.narration or "").strip("\n")
            opts = re.findall(r"\[options\s+([^\]]+)\]", raw)
            cont = re.sub(r"\[options[^\]]*\]", "", cont).strip("\n")
            options = [x.strip() for x in re.split(r"[|｜]", opts[-1]) if x.strip()] if opts else []
            pl = prefix.splitlines()
            first = cont.split("\n", 1)[0].strip()
            replaced = bool(cont and pl and pl[-1].strip() and first.startswith(pl[-1].strip())) or bool(old and not prefix)
            full = _tv3.join_continued(prefix, cont) if prefix else cont
            applied: list[dict[str, Any]] = []
            if cont.strip():
                _bb.grant(_bb.settle_s(root), "world.settle")
                reg = load_registry(root)
                t_user = (block("") + _prompts.text("transition", narr_lang, root).format(
                    lines=cont[:5000], tools=T["no_tools"], pack_ops=pack_ops_lines(reg, narr_lang) or T["no_tools"])
                    + "".join("\n\n" + x for x in (narrate_lang_line(root, narr_lang),) if x))
                raw2 = _tv3._write_down(adapter, system, t_user, root, background=False, lang=narr_lang)[0]
                vr = verify(root, _tv3.parse_transition(raw2), reg, max_ops=int(r.get("max_ops") or 24))
                vr, _ = identity_gate(root, reg, vr, cont)
                ar = apply(root, [o for o in vr.accepted if o.get("op") != "need"], reg, turn=int(r.get("turn") or 0),
                           refused=vr.refused, writers=str(r.get("writers") or "on"), narration=cont,
                           player_says=str(r.get("user_text") or ""), ticks=False)
                applied = list(ar.applied)
                out_state = {"applied": applied, "created": list(ar.created), "variables": dict(ar.variables)}
    hits = list(hits)
    if not cont.strip():
        return {"ok": False, "error": "the continuation said nothing", "timeouts": hits}
    if "{{" in full:
        reg = load_registry(root)
        full, cont = reg.render_refs(full), reg.render_refs(cont)
    n = ln.continued + 1

    def edit(rec: dict[str, Any]) -> None:
        ap = rec.get("apply") if isinstance(rec.get("apply"), dict) else {}
        ap["narration_plain"] = full
        ap["annotated"] = grow(str(ap.get("annotated") or ""), old, full)
        if options:
            ap["options"] = options
        ap["applied"] = list(ap.get("applied") or []) + [{**a, "continued": n} for a in out_state.get("applied") or []]
        if out_state.get("variables"):
            ap["variables"] = out_state["variables"]
        try:
            from neonrp.core import mentions as _mn

            ap["mentions"] = _mn.find(load_registry(root), full)
        except Exception:  # noqa: BLE001
            pass
        ap["continued"] = n  # how many times this beat's prose was continued (the record shows it)
        rec["apply"] = ap

    _amend_last_trace(root, ln.branch, edit)
    _amend_last_reply(root, ln.branch, old, full)
    for m in reversed(messages or []):
        if getattr(m, "role", None) == "assistant":
            m.content = grow(str(m.content or ""), old, full)
            break
    ln.continued = n
    r["narration"] = r["shown"] = full
    ln.cut = cut_of(hits)
    return {"ok": True, "text": cont, "replaced_last": replaced, "narration": full, "options": options,
            "applied": applied, "cut": list(ln.cut), "timeouts": hits}
