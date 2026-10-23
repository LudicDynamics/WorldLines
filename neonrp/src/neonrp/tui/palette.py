"""Command Palette overlay for NeonRP TUI."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, ListView, ListItem, Static

from neonrp.tui.commands import COMMANDS, get_command_suggestions


class CommandPaletteItem(ListItem):
    """A single item in the command palette."""

    def __init__(self, command: str, description: str) -> None:
        super().__init__()
        self.command = command
        self.description = description

    def compose(self) -> ComposeResult:
        """Compose the list item."""
        yield Static(f"[bold cyan]/{self.command}[/] - [dim]{self.description}[/]")


class CommandPalette(ModalScreen):
    """Modal command palette overlay."""

    CSS = """
    CommandPalette {
        align: center middle;
    }

    #palette-container {
        width: 60;
        height: auto;
        max-height: 24;
        background: $surface;
        border: thick $primary;
        padding: 1;
    }

    #palette-title {
        height: 1;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #palette-input {
        width: 100%;
        margin-bottom: 1;
    }

    #palette-list {
        height: auto;
        max-height: 16;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("enter", "select", "Select", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.filter_text = ""

    def compose(self) -> ComposeResult:
        """Compose the command palette."""
        with Vertical(id="palette-container"):
            yield Static("[bold]Command Palette[/]", id="palette-title")
            yield Input(placeholder="Type to filter commands...", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self._refresh_list("")
        self.query_one("#palette-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for filtering."""
        if event.input.id == "palette-input":
            self.filter_text = event.value
            self._refresh_list(event.value)

    def _refresh_list(self, filter_text: str) -> None:
        """Refresh the command list with filter."""
        list_view = self.query_one("#palette-list", ListView)
        list_view.clear()

        suggestions = get_command_suggestions(filter_text.lower())

        for cmd in suggestions:
            spec = COMMANDS.get(cmd, {})
            description = spec.get("help", "")
            if "subcommands" in spec:
                description += f" ({', '.join(spec['subcommands'])})"
            list_view.append(CommandPaletteItem(cmd, description))

    def action_dismiss(self) -> None:
        """Close the palette without selecting."""
        self.dismiss(None)

    def action_select(self) -> None:
        """Select the current item."""
        list_view = self.query_one("#palette-list", ListView)
        if list_view.highlighted_child and isinstance(list_view.highlighted_child, CommandPaletteItem):
            self.dismiss(list_view.highlighted_child.command)
        else:
            # Use the filter text as command if nothing selected
            self.dismiss(self.filter_text)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        if isinstance(event.item, CommandPaletteItem):
            self.dismiss(event.item.command)
