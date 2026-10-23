"""Stream a model's reply and show only the prose block as it is written (「agent 开始生成字的时候,马上渲染到
tui 上」).

The replies here are text with blocks (<lines>…</lines> <mic>… <board>… <draft>… next: …); only what is inside
<lines> is for the screen. ``stream_chat`` feeds the deltas through a small state machine that passes on the text inside
the block (a tag split across chunks is held back until it is whole) and stops passing at the first line that is a
request the engine must answer (``[dice …]`` …): what the model writes after it is cut by the parser, so it must never
reach the screen. If the stream fails or comes back empty, it falls back to one plain call and shows the block at once.
"""
from __future__ import annotations

import contextlib
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_OPEN, _CLOSE = "<lines>", "</lines>"
_REQUEST_LINE = re.compile(r"^\s*\[(?!~)\s*[A-Za-z_][\w.\-]*[^\]\n]*\]")  # [dice 1d20 vs 12] — a waiting request (not [~map])
_REQUEST_ANY = re.compile(r"\[(?!~)\s*[A-Za-z_][\w.\-]*[^\[\]\n]*\]")  # the same request in the middle of a line (sdk._REQUEST_RE)
_ASYNC_BLOCKS = ("write",)  # async ops whose body spans lines up to a close tag
_ASYNC_LINE = re.compile(r"^\s*\[~\s*([A-Za-z_][\w.\-]*)")  # [~map] / [~sheet] / [~write path]… — the engine's, never screen text (10-08)


class LinesFilter:
    """Feed it deltas; ``feed`` returns the screen text they add (inside <lines>, up to the first waiting request)."""

    def __init__(self, stop_at_request: bool = True, no_block_ok: bool = False, skip_lines: set[str] | None = None,
                 tail: str = ""):
        self.buf = ""          # raw text not yet decided (a possible partial tag at the end)
        self.inside = False
        self.done = False
        self.stop_at_request = stop_at_request
        self.no_block_ok = no_block_ok  # a reply that never opens <lines> (a bare answer) is shown as it comes
        self.seen_open = False
        self.line = ""         # the current screen line, to spot a request line before showing it
        self.shown = ""
        # lines already on screen from before a tool call: a continuation that starts by restating them is held line by
        # line and dropped until the first new line (10-05 C1)
        self.skip = {x.strip() for x in (skip_lines or set()) if x and x.strip()}
        self.in_async = ""     # inside a multi-line async block ([~write p]…[/write]): its op, until the close tag
        self.part = False      # the start of the current line is already on screen (``line`` holds only the rest)
        self.lineout = ""      # … and that start
        # a stop in the middle of a line (「你摸着砖缝[dice 侦查]」): ``cut`` = the words of that line on screen, no newline
        # after them; the continuation's filter gets them as ``tail`` — a first line that restates them only adds its
        # rest to that line, any other first line starts a new one (10-17: the line was on screen twice)
        self.cut = ""
        self.tail = tail.strip() or None
        self.owed = bool(self.tail)  # the newline the stop held back
        self.continued = bool(self.tail)

    def feed(self, delta: str) -> str:
        if self.done or not delta:
            return ""
        self.buf += delta
        out = ""
        while self.buf and not self.done:
            if not self.inside:
                i = self.buf.find(_OPEN)
                if i < 0:
                    keep = max(0, len(self.buf) - len(_OPEN))
                    self.buf = self.buf[keep:]
                    break
                self.buf, self.inside, self.seen_open = self.buf[i + len(_OPEN):], True, True
                continue
            j = self.buf.find(_CLOSE)
            if j >= 0:
                out += self._take(self.buf[:j], final=True)
                self.buf, self.done = "", True
                break
            hold = len(self.buf) - max(0, self.buf.rfind("<")) if "<" in self.buf[-len(_CLOSE):] else 0
            take, self.buf = self.buf[: len(self.buf) - hold], self.buf[len(self.buf) - hold:]
            out += self._take(take, final=False)
            break
        if not self.shown and not self.continued:
            out = out.lstrip("\n")  # the block's own first newline is not text
        self.shown += out
        return out

    def _out(self, text: str) -> str:
        if text and self.owed:
            self.owed = False
            return "\n" + text
        return text

    def _restated(self) -> str | None:
        """The continuation's first line against the cut line: None = not a restatement (go on as usual); else what of
        it goes on the screen ("" = nothing new yet)."""
        t, self.tail = self.tail, None
        s = self.line.strip()
        if not t or not s.startswith(t):
            return None
        rest, self.line = s[len(t):], ""
        if not rest:
            return ""
        m = _REQUEST_ANY.search(rest) if self.stop_at_request else None
        if m:
            self.done, self.cut = True, (t + rest[:m.start()]).rstrip()
            rest = rest[:m.start()].rstrip()
            self.owed = False
            return rest
        self.owed = False
        self.skip = set()
        return rest + "\n"

    def _take(self, text: str, final: bool) -> str:
        """Plain text goes out as it comes; a piece that starts with ``[`` is held until its line ends — a request line
        stops the screen there (what follows is cut by the parser)."""
        out = ""
        for ch in text:
            self.line += ch
            if ch == "\n":
                if self.tail is not None and not self.line.strip():  # the block's own first newline
                    self.line = ""
                    continue
                if self.tail is not None:
                    r = self._restated()
                    if r is not None:
                        out += r
                        if self.done:
                            return out
                        continue
                if self._async_drop(self.line):
                    out += "\n" if self.part else ""
                    self.line, self.part, self.lineout = "", False, ""
                    continue
                if self.stop_at_request and _REQUEST_LINE.match(self.line):
                    self.done = True
                    if self.part:
                        self.cut = self.lineout.strip()
                    return out
                if self.skip and (not self.line.strip() or self.line.strip() in self.skip):
                    self.line = ""
                    continue
                self.skip = set()
                if self.stop_at_request and (m := _REQUEST_ANY.search(self.line)):  # 「你摸着砖缝[dice 侦查]——大成功!」
                    self.done = True
                    before = self.line[:m.start()].rstrip()
                    self.cut = (self.lineout + before).strip()
                    return out + self._out(before)
                out += self._out(self.line)
                self.line, self.part, self.lineout = "", False, ""
        head = self.line.lstrip()
        if head and not head.startswith("[") and not self.skip and self.tail is None:
            out += self._mid_line()
        elif final and self.line:
            if self.tail is not None and (r := self._restated()) is not None:
                return out + r
            if not self._async_drop(self.line) and not (self.stop_at_request and _REQUEST_LINE.match(self.line)):
                m = _REQUEST_ANY.search(self.line) if self.stop_at_request else None
                if m:
                    before = self.line[:m.start()].rstrip()
                    self.cut, self.done = (self.lineout + before).strip(), True
                    out += self._out(before)
                else:
                    out += self._out(self.line)
            self.line = ""
        return out

    def _mid_line(self) -> str:
        """The part of an unfinished prose line that can go out now: up to a request in it (then the screen stops — the
        words after a request in the same line were written before the engine answered, niko 10-17), else up to a
        bracket still open (it may become a request)."""
        s = self.line
        m = _REQUEST_ANY.search(s) if self.stop_at_request else None
        if m:
            before = s[:m.start()].rstrip()
            self.done, self.line, self.cut = True, "", (self.lineout + before).strip()
            return self._out(before)
        i = s.find("[") if self.stop_at_request else -1
        while i >= 0 and "]" in s[i:]:  # a closed bracket that is no request (「[禁入]」) is prose
            i = s.find("[", s.index("]", i) + 1)
        self.part = self.part or i != 0
        piece = s if i < 0 else s[:i]
        self.line = "" if i < 0 else s[i:]
        self.lineout += piece
        return self._out(piece)

    def _async_drop(self, line: str) -> bool:
        """An async tool line ([~map] …) or a line inside a multi-line async block ([~write p] … [/write]) is the
        engine's to act on, not screen text — the panel / file it makes is shown on its own (10-08)."""
        if self.in_async:
            if f"[/{self.in_async}]" in line:
                self.in_async = ""
            return True
        m = _ASYNC_LINE.match(line)
        if not m:
            return False
        op = m.group(1).lower()
        if op in _ASYNC_BLOCKS and f"[/{op}]" not in line[m.end():].lower():
            self.in_async = op  # [~write path] … — the body runs until [/write] (sdk._WRITE_BODY_RE)
        return True


def _note_error(state: dict[str, Any] | None, res: Any, text: str) -> None:
    if state is None:
        return
    err = getattr(res, "error", None)
    if text:
        state.pop("error", None)
    elif err:
        state["error"] = str(err)


def _ms(t0: float, t: float | None) -> int | None:
    return None if t is None else round((t - t0) * 1000)


def _log(state: dict[str, Any] | None, t0: float, first: float | None, text: str, **kw: Any) -> None:
    """ms to the first chunk (None: no chunk / not a stream) and in all, into ``state`` and the turn's call log."""
    import time

    from neonrp.core import beat_budget

    first_ms = None if first is None else round((first - t0) * 1000)
    ms = round((time.monotonic() - t0) * 1000)
    trunc = bool(state and state.get("truncated"))
    if state is not None:
        state["first_ms"], state["ms"] = first_ms, ms
    beat_budget.log_call(first_ms=first_ms, ms=ms, chars=len(text or ""), **({"truncated": True} if trunc else {}),
                         **{k: v for k, v in kw.items() if k != "truncated" and v})


def stream_chat(adapter: Any, messages: list[Any], on_text: Callable[[str], None] | None, *,
                stop_at_request: bool = True, skip_lines: set[str] | None = None,
                state: dict[str, Any] | None = None) -> tuple[str, bool]:
    """Returns (the whole reply, whether anything was shown). ``on_text`` gets the screen text as it is written.
    ``state["tail"]``: the line a stop in its middle left on screen (read for this reply, written for the next one).
    ``state["error"]``: why an empty reply is empty, when the model said so (a refused / failed call — 10-18: a guest's
    403 came back as an empty beat); unset when the reply has text. ``state["truncated"]``: the stream was cut (the
    beat's time ran out, the stream broke) after some text — the reply is that part (10-19: kept, not a failed beat).
    ``state["first_ms"]`` / ``state["ms"]``: ms to the first chunk / in all; each call is also logged for the turn's trace
    (core/beat_budget.log_call)."""
    import time

    t0 = time.monotonic()
    if state is not None:
        state.pop("truncated", None)
    if on_text is None or not hasattr(adapter, "chat_stream"):
        res = adapter.chat(messages)
        out = (getattr(getattr(res, "message", None), "content", None) or "").strip()
        _note_error(state, res, out)
        _log(state, t0, None, out, stream=False)
        return out, False
    f = LinesFilter(stop_at_request=stop_at_request, skip_lines=skip_lines, tail=str((state or {}).get("tail") or ""))
    if state is not None:
        state["tail"] = ""
    full = ""
    first: float | None = None
    think: float | None = None  # the first thinking chunk: a call with no first_ms was thinking, not silent
    cut = ""  # the stream ended before it finished: an error chunk (the beat's time, a broken stream) or an exception
    raised = False
    try:
        with contextlib.closing(adapter.chat_stream(messages)) as gen:  # closed here, not by the GC (llm_openai._closing)
            for chunk in gen:
                d = getattr(chunk, "delta", None) or ""
                if getattr(chunk, "error", None):
                    cut = str(chunk.error)
                if think is None and getattr(chunk, "thinking", None):
                    think = time.monotonic()
                if d:
                    if first is None:
                        first = time.monotonic()
                    full += d
                    t = f.feed(d)
                    if t:
                        on_text(t)
    except Exception as e:  # noqa: BLE001 — a dropped stream (deepseek mid-stream stalls) falls back to one plain call
        logger.debug("stream failed; plain call", exc_info=True)
        cut, raised = str(e), True
        if state is not None:
            state["error"] = str(e)
    from neonrp.core import beat_budget

    if raised and not (full.strip() and beat_budget.expired(beat_budget.MIN_RETRY_S)):
        full = ""  # a stream that broke with time left: one whole plain call, as before
    if full.strip() and cut:
        # cut after some text (10-19: the beat's time ran out mid-reply): that part is the reply — kept, marked
        if state is not None:
            state["truncated"] = True
            state.pop("error", None)
    if not full.strip() and beat_budget.expired(beat_budget.MIN_RETRY_S):
        # the beat is over (core/beat_budget): no second, whole plain call after a stalled stream — the caller's
        # fallback for an empty reply runs (10-14: a stall + the plain call was the 60 s + 30 s beat)
        beat_budget.note("stream.fallback")
        _log(state, t0, first, "", stream=True, think_ms=_ms(t0, think))
        return "", bool(f.shown)
    if not full.strip():
        res = adapter.chat(messages)
        full = (getattr(getattr(res, "message", None), "content", None) or "").strip()
        _note_error(state, res, full)
        _log(state, t0, first, full, stream=True, fallback=True, think_ms=_ms(t0, think))
        if not f.shown:
            m = re.search(r"<lines>(.*?)</lines>", full, re.S)
            body = (m.group(1).strip() if m else "")
            if body:
                g = LinesFilter(stop_at_request=stop_at_request, tail=f.tail or "")
                t = g.feed(f"<lines>{body}</lines>")
                if state is not None and g.cut:
                    state["tail"] = g.cut
                if t:
                    on_text(t)
                    return full.strip(), True
        return full.strip(), bool(f.shown)
    _log(state, t0, first, full, stream=True, think_ms=_ms(t0, think))
    if not f.seen_open and not f.shown:  # no <lines> block at all (a bare answer): show it whole
        bare = re.sub(r"<(mic|board|draft|vars|files|ops|options)>.*?</\1>", "", full, flags=re.S)
        bare = "\n".join(x for x in bare.splitlines() if x.strip() and not x.strip().startswith("next:")).strip()
        if bare:
            on_text(bare + "\n")
            return full.strip(), True
    rest = f._take("", final=True) if (f.line and not f.done) else ""
    if rest:
        on_text(rest)
    if state is not None and f.cut:
        state["tail"] = f.cut
    return full.strip(), bool(f.shown or rest)
