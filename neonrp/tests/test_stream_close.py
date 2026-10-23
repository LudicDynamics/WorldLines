"""A model stream is closed by whoever reads it — never left to the garbage collector (10-11).

The hang it fixes (benchmark open-jev-1011, a turn waiting forever): an unclosed openai stream was collected *inside* the
next request, while that request held httpcore's connection-pool lock; the stream's close() asked for the same lock
(not re-entrant) and the thread waited on itself. Each test runs with the GC off: a close that only happens on
collection does not count."""
from __future__ import annotations

import gc
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _no_gc():
    gc.disable()
    try:
        yield
    finally:
        gc.enable()


class _Stream:
    def __init__(self, items, boom=False):
        self.items, self.boom, self.closed = items, boom, 0

    def __iter__(self):
        yield from self.items
        if self.boom:
            raise OSError("the provider dropped the stream")

    def close(self):
        self.closed += 1


def test_the_sdk_stream_is_closed_when_the_loop_ends_breaks_or_fails():
    from neonrp.core.llm_openai import _closing

    s = _Stream([1, 2, 3])
    assert list(_closing(s)) == [1, 2, 3] and s.closed == 1
    s = _Stream([1, 2, 3])
    g = _closing(s)
    next(g)
    g.close()  # the reader stops early
    assert s.closed == 1
    s = _Stream([1], boom=True)
    with pytest.raises(OSError):
        list(_closing(s))
    assert s.closed == 1


def test_stream_chat_closes_the_adapters_stream_even_when_showing_text_fails():
    from neonrp.core import stream_lines

    closed: list[int] = []

    class Adapter:
        def chat_stream(self, messages):
            try:
                yield SimpleNamespace(delta="<lines>\n你走进公会。\n")
                yield SimpleNamespace(delta="</lines>")
            finally:
                closed.append(1)

        def chat(self, messages):
            return SimpleNamespace(message=SimpleNamespace(content="<lines>\n你走进公会。\n</lines>"))

    def on_text(t):
        raise RuntimeError("the screen went away")

    stream_lines.stream_chat(Adapter(), [], on_text)  # the failure falls back to one plain call …
    assert closed == [1]  # … after the half-read stream was closed


def test_a_cancelled_turn_closes_its_stream_at_once():
    import threading

    from neonrp.core import conversation

    closed: list[int] = []
    cancel = threading.Event()

    class Adapter:
        def chat_stream(self, messages, tools=None):
            try:
                yield SimpleNamespace(delta="一", thinking="", tool_call_starts=[], tool_calls=None, usage=None, finished=False, error=None)
                cancel.set()
                yield SimpleNamespace(delta="二", thinking="", tool_call_starts=[], tool_calls=None, usage=None, finished=False, error=None)
                yield SimpleNamespace(delta="三", thinking="", tool_call_starts=[], tool_calls=None, usage=None, finished=True, error=None)
            finally:
                closed.append(1)

    conversation._chat_stream(Adapter(), [], None, None, None, cancel)
    assert closed == [1]
