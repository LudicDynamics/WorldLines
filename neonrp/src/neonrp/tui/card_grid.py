"""Card-style overview: boxes with a picture inside, a title above and a
caption below (「一览画面变成卡片式」).

Used by the launcher for「世界库 · 一览游玩」and「角色库 · 一览游玩」. The
screen only picks — what happens with the pick (LLM → play) is the
caller's business.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Group
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

CARD_COLUMNS = 3
CARD_ART_W = 26
CARD_ART_H = 8


@dataclass(frozen=True)
class CardItem:
    key: str
    title: str
    caption: str = ""
    image: Path | None = None


def _art_for(image: Path | None) -> Any:
    """Matrix-braille rendering of the card picture; a quiet placeholder
    when there is none or rendering fails."""
    if image is not None:
        try:
            from neonrp.core.image_render import render_image_lines

            lines = render_image_lines(image, width=CARD_ART_W, height=CARD_ART_H, mode="braille")
            if lines:
                return Group(*lines)
        except Exception:
            pass
    blank = Text("\n" * (CARD_ART_H // 2 - 1) + "· · ·", style="#2f4a3a", justify="center")
    return blank


class Card(Vertical, can_focus=True):
    def __init__(self, item: CardItem, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.item = item

    def compose(self) -> ComposeResult:
        yield Static(Text(self.item.title, style="bold #e6fff0", justify="center"), classes="card-title", markup=False)
        yield Static(_art_for(self.item.image), classes="card-art")
        yield Static(Text(self.item.caption, style="#8fb39f", justify="center"), classes="card-caption", markup=False)

    def on_click(self) -> None:
        self.focus()
        screen = self.screen
        if isinstance(screen, CardGridScreen):
            screen.dismiss(self.item.key)


class CardGridScreen(ModalScreen[str | None]):
    """Pick one card. Arrows move, Enter picks, Esc leaves with None."""

    DEFAULT_CSS = """
    CardGridScreen {
        align: center middle;
        background: #050806 90%;
    }
    #card-modal {
        width: 96%;
        height: 92%;
        background: #070b08;
        border: round #00B960;
        padding: 0 1;
    }
    #card-title {
        height: 1;
        color: #E4E4E7;
        text-style: bold;
        content-align: center middle;
    }
    #card-hint {
        height: 1;
        color: #71717A;
        content-align: center middle;
        margin-bottom: 1;
    }
    #card-scroll { height: 1fr; }
    #card-grid {
        grid-size: 3;
        grid-gutter: 1 2;
        height: auto;
    }
    Card {
        height: auto;
        border: round #1f3a29;
        padding: 0 1;
        background: #090d0a;
    }
    Card:focus {
        border: round #18FF82;
        background: #0d1710;
    }
    .card-title { height: 1; width: 100%; }
    .card-art { height: auto; width: 100%; content-align: center middle; }
    .card-caption { height: auto; max-height: 3; width: 100%; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("enter", "pick", "Open"),
        Binding("b", "pick_build", "Workshop", show=False),
        Binding("left", "move(-1)", "Prev", show=False),
        Binding("right", "move(1)", "Next", show=False),
        Binding("up", "move(-3)", "Up", show=False),
        Binding("down", "move(3)", "Down", show=False),
    ]

    def __init__(self, title: str, items: list[CardItem], hint: str = "") -> None:
        super().__init__()
        self._title = title
        self._items = list(items)
        self._hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="card-modal"):
            yield Static(self._title, id="card-title", markup=False)
            yield Static(self._hint, id="card-hint", markup=False)
            with VerticalScroll(id="card-scroll"):
                with Grid(id="card-grid"):
                    for i, item in enumerate(self._items):
                        yield Card(item, id=f"card-{i}")

    def on_mount(self) -> None:
        cards = list(self.query(Card))
        if cards:
            cards[0].focus()

    def _cards(self) -> list[Card]:
        return list(self.query(Card))

    def action_move(self, delta: int) -> None:
        cards = self._cards()
        if not cards:
            return
        try:
            idx = cards.index(self.focused) if isinstance(self.focused, Card) else 0
        except ValueError:
            idx = 0
        nxt = max(0, min(len(cards) - 1, idx + delta))
        cards[nxt].focus()
        cards[nxt].scroll_visible()

    def action_pick(self) -> None:
        if isinstance(self.focused, Card):
            self.dismiss(self.focused.item.key)

    def action_pick_build(self) -> None:
        """`b` on a card: the caller gets `build::<key>` — open it in its
        workshop instead of playing / talking (角色工坊的回门, TODO #9)."""
        if isinstance(self.focused, Card):
            self.dismiss(f"build::{self.focused.item.key}")

    def action_cancel(self) -> None:
        self.dismiss(None)
