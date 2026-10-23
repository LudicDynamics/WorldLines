"""TUI debug panel — live view of recent LLM calls.

Subscribes to ``debug_sink``'s ring buffer; renders one card per call with
tokens in/out, cache hits, tokens/sec, thinking text, and tool calls. Only
imported when ``DEBUG_ENABLED`` is True — production startup (``python -O``
or ``NEONRP_DEBUG`` unset) never pulls in Textual widgets from this file.

Open with F12 from the conversation screen. Esc closes; ``c`` clears the
buffer; ``r`` forces a repaint.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from neonrp.core import debug_sink

_REFRESH_INTERVAL = 0.5  # seconds


def _fmt_int(n: int) -> str:
    """Compact int format: 1234 -> 1.2k. Numbers in a debug panel get long."""
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k"
    return f"{n / 1_000_000:.2f}M"


def _format_record(rec: dict[str, Any]) -> str:
    """One LLM call → multi-line Static text. Plain text on purpose: a
    debug panel should be copy-pasteable into a bug report."""
    seq = rec.get("seq", "?")
    agent = rec.get("agent_id", "?")
    model = rec.get("model", "") or "?"
    turn = rec.get("turn", "?")
    dur = rec.get("duration_ms", 0)
    tps = rec.get("tokens_per_sec", 0)
    pt = int(rec.get("prompt_tokens", 0))
    ct = int(rec.get("completion_tokens", 0))
    cc = int(rec.get("cache_creation_tokens", 0))
    cr = int(rec.get("cache_read_tokens", 0))
    cache_hit_pct = (cr / pt * 100.0) if pt > 0 else 0.0

    header = f"#{seq}  agent={agent}  model={model}  turn={turn}"
    timing = f"  duration={dur}ms  speed={tps} tok/s"
    tokens = (
        f"  in={_fmt_int(pt)}  out={_fmt_int(ct)}"
        f"  cache_read={_fmt_int(cr)} ({cache_hit_pct:.0f}%)"
        f"  cache_create={_fmt_int(cc)}"
    )
    lines = [header, timing, tokens]

    thinking = str(rec.get("thinking") or "").strip()
    if thinking:
        # First 6 lines of the thinking block, indented; rest folded.
        tlines = thinking.splitlines()
        preview = "\n".join("    " + ln for ln in tlines[:6])
        more = f"\n    … ({len(tlines) - 6} more lines)" if len(tlines) > 6 else ""
        lines.append("  thinking:")
        lines.append(preview + more)

    tool_calls = rec.get("tool_calls") or []
    if tool_calls:
        tc_names = ", ".join(
            tc.get("name", "?") for tc in tool_calls if isinstance(tc, dict)
        )
        lines.append(f"  tools: {tc_names}")

    text_preview = str(rec.get("text_preview") or "").strip()
    if text_preview:
        # One-line preview, truncated.
        line = text_preview.replace("\n", " ")
        if len(line) > 140:
            line = line[:137] + "…"
        lines.append(f"  text: {line}")

    err = str(rec.get("error") or "").strip()
    if err:
        lines.append(f"  ERROR: {err}")

    return "\n".join(lines)


class DebugScreen(ModalScreen[None]):
    """Modal screen listing recent LLM calls from ``debug_sink``.

    Polls ``latest_seq`` on a tick; only re-renders when the seq advanced,
    so an idle panel costs ~one int comparison per 500ms.

    ESC closes this panel. The key is consumed here — it never reaches the
    parent conversation screen (so dismissing the debug panel never triggers
    "cancel thinking" / "cancel input").
    """

    BINDINGS = [
        Binding("c", "clear_buffer", "clear", show=True),
        Binding("r", "force_refresh", "refresh", show=True),
    ]

    DEFAULT_CSS = """
    DebugScreen {
        align: center middle;
    }
    DebugScreen > VerticalScroll {
        width: 90%;
        height: 90%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    DebugScreen Static.empty {
        color: $text-muted;
        padding: 2;
    }
    DebugScreen Static.record {
        background: $boost;
        padding: 1 1;
        margin-bottom: 1;
        border-left: thick $accent;
    }
    DebugScreen Static.title {
        text-style: bold;
        color: $accent;
        padding-bottom: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_seq = -1

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="debug-scroll"):
            yield Static(
                "neonrp · debug · LLM calls  [esc close · c clear · r refresh]",
                classes="title",
                id="debug-title",
            )
            yield Static("(waiting for first LLM call…)", classes="empty", id="debug-empty")

    def on_mount(self) -> None:
        self._repaint()
        self.set_interval(_REFRESH_INTERVAL, self._tick)

    def _tick(self) -> None:
        cur = debug_sink.latest_seq()
        if cur != self._last_seq:
            self._repaint()

    def _repaint(self) -> None:
        try:
            scroll = self.query_one("#debug-scroll", VerticalScroll)
        except Exception:  # noqa: BLE001 — screen tearing during close
            return
        # Drop all but the title; rebuild record children.
        for child in list(scroll.children):
            if isinstance(child, Static) and "title" in child.classes:
                continue
            child.remove()

        records = debug_sink.get_recent_calls(limit=50)
        if not records:
            scroll.mount(
                Static("(no LLM calls recorded yet)", classes="empty")
            )
            self._last_seq = debug_sink.latest_seq()
            return

        for rec in records:
            scroll.mount(Static(_format_record(rec), classes="record"))
        self._last_seq = debug_sink.latest_seq()

    def on_key(self, event: Key) -> None:
        """ESC dismisses this panel and is consumed — it never reaches the
        parent conversation screen (where ESC cancels the current turn/input)."""
        if event.key == "escape":
            event.stop()
            self.dismiss(None)
            return
        super().on_key(event)

    def action_clear_buffer(self) -> None:
        debug_sink.clear()
        self._last_seq = -1
        self._repaint()

    def action_force_refresh(self) -> None:
        self._last_seq = -1
        self._repaint()
