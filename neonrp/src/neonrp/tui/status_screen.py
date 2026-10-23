"""/status as one screen of tabs (10-23): the player, each character of the run, then usage (account · contract · board
· dice · ending · tokens). ← / → go round the tabs, Esc closes. What each tab shows comes from play_commands."""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from neonrp.tui import play_commands as PC


class StatusScreen(ModalScreen[None]):
    CSS = """
    StatusScreen { align: center middle; background: #09090B 70%; }
    #status-modal {
        width: 86%; max-width: 110; height: 80%;
        background: #09090B; border: solid #00B960; padding: 0 1; layout: vertical;
    }
    #status-modal-title { height: 1; color: #E4E4E7; text-style: bold; }
    #status-tabbar { height: 1; width: 100%; overflow-x: auto; margin-bottom: 1; }
    #status-tabbar Button {
        width: auto; min-width: 4; height: 1; padding: 0 1; margin-right: 1;
        background: #111827; color: #9ca3af; border: none; text-style: none;
    }
    #status-tabbar Button.active { background: #1f2937; color: #4ADE80; text-style: bold; }
    #status-tab-scroll { height: 1fr; }
    #status-modal-hint { height: 1; color: #71717A; }
    """

    BINDINGS = [
        Binding("left", "step(-1)", "Prev", show=False),
        Binding("right", "step(1)", "Next", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    def __init__(self, host: Any, key: str = "player") -> None:
        super().__init__()
        self.host = host
        self.tabs = PC.status_tabs(host)
        keys = [k for k, _ in self.tabs]
        self.key = key if key in keys else keys[0]

    def compose(self) -> ComposeResult:
        with Vertical(id="status-modal"):
            yield Static(PC._m(self.host, "tabs.title"), id="status-modal-title")
            with Horizontal(id="status-tabbar"):
                for i, (_k, label) in enumerate(self.tabs):
                    yield Button(label, id=f"status-tab-{i}")
            yield VerticalScroll(Static("", id="status-tab-body"), id="status-tab-scroll")
            yield Static(PC._m(self.host, "tabs.hint"), id="status-modal-hint")

    def on_mount(self) -> None:
        self.show(self.key)

    def show(self, key: str) -> None:
        keys = [k for k, _ in self.tabs]
        if key not in keys:
            key = keys[0]
        self.key = key
        for i, k in enumerate(keys):
            try:
                self.query_one(f"#status-tab-{i}", Button).set_class(k == key, "active")
            except Exception:  # noqa: BLE001 — not mounted yet
                pass
        try:
            body = PC.status_body(self.host, key)
        except Exception as exc:  # noqa: BLE001 — a tab that cannot be read says so instead of closing the screen
            body = Text(str(exc)[:300], style="#f87171")
        try:
            self.query_one("#status-tab-body", Static).update(body)
            self.query_one(f"#status-tab-{keys.index(key)}", Button).focus()
        except Exception:  # noqa: BLE001
            pass

    def action_step(self, d: int) -> None:
        keys = [k for k, _ in self.tabs]
        self.show(keys[(keys.index(self.key) + d) % len(keys)])

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = str(event.button.id or "")
        if bid.startswith("status-tab-"):
            event.stop()
            self.show(self.tabs[int(bid[len("status-tab-"):])][0])
