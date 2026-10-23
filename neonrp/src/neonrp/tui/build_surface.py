"""Build mode's companion surface — a file tree and a document reader.

Play and build should look like two different places, not one screen with a
different word in the status bar. Play already has its own furniture (the
portrait, the scene image, the status lane) and it answers *what the world
looks like right now*. Build's furniture answers the other question: *what
is this world made of* — a collapsible tree of the project and a reader for
whatever file you point at.

Reading only, on purpose. Edits stay in the agent conversation, where the
change is described, diffed and logged; a half-editor beside it would just
be a second way to write that nobody maintains.

「可折叠的 file system…点击 file name 就可以聚焦修改里面的
文档(不过主要还是用来浏览文档,修改的话可以在 agent 对话框里面修改)」
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DirectoryTree, Markdown, Static

from neonrp.tui.jsonview import render_json_doc

# Machine bookkeeping the author never reads. Hiding it is not cosmetic: a
# tree that opens onto `__pycache__` and commit blobs teaches you that the
# tree is noise, and then you stop looking at it.
HIDDEN_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".DS_Store",
        "node_modules",
    }
)
# Shown as a folder but not worth expanding — engine internals.
HIDDEN_PREFIXES: tuple[str, ...] = (".projection.json",)

# A reader, not a viewer of arbitrary blobs.
_TEXT_SUFFIXES = frozenset(
    {".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".py", ".ts", ".tsx", ".css", ".html"}
)
_READ_LIMIT = 200_000  # bytes; past this we summarise instead of pasting


class WorldTree(DirectoryTree):
    """The project as a folder tree, minus the plumbing."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        keep = []
        for path in paths:
            name = path.name
            if name in HIDDEN_NAMES or name.startswith(HIDDEN_PREFIXES):
                continue
            # `.neonrp/` is the engine's own bookkeeping (manifest, events,
            # commit blobs). The author edits the world, not the ledger.
            if name == ".neonrp":
                continue
            keep.append(path)
        return sorted(keep, key=lambda p: (p.is_file(), p.name.lower()))


class DocReader(Vertical):
    """Whatever file the tree is pointing at, rendered for reading.

    Markdown renders as markdown (the world is becoming markdown), JSON goes
    through the house renderer rather than showing raw braces, and anything
    binary gets one honest line instead of a screenful of noise.
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="doc-reader-title")
        yield Markdown("", id="doc-reader-md")
        yield Static("", id="doc-reader-text")

    def show_path(self, path: Path) -> None:
        """Point the reader at a file. Never raises — a bad file is content."""
        try:
            self._show(Path(path))
        except Exception as exc:  # noqa: BLE001 — the reader must not kill a turn
            self._as_text(str(path), f"[读取失败] {exc}")

    # -- internals ----------------------------------------------------

    def _show(self, path: Path) -> None:
        title = path.name
        if not path.is_file():
            self._as_text(title, "(不是文件)")
            return
        size = path.stat().st_size
        if path.suffix.lower() not in _TEXT_SUFFIXES:
            self._as_text(title, f"(二进制文件 · {size} 字节)")
            return
        if size > _READ_LIMIT:
            self._as_text(title, f"(文件过大 · {size} 字节,请在编辑器里看)")
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._as_text(title, f"(读不出文本 · {size} 字节)")
            return

        if path.suffix.lower() == ".md":
            self._as_markdown(title, text)
        elif path.suffix.lower() == ".json":
            try:
                self._as_rich(title, render_json_doc(json.loads(text)))
            except ValueError:
                # Broken JSON is exactly what you want to SEE, not hide.
                self._as_text(title, text)
        else:
            self._as_text(title, text)

    def _set_title(self, title: str) -> None:
        try:
            self.query_one("#doc-reader-title", Static).update(
                Text(title, style="bold")
            )
        except Exception:  # noqa: BLE001 — unmounted (tests construct bare)
            pass

    def _swap(self, *, markdown: bool) -> tuple[Any, Any]:
        md = txt = None
        try:
            md = self.query_one("#doc-reader-md", Markdown)
            txt = self.query_one("#doc-reader-text", Static)
            md.display = markdown
            txt.display = not markdown
        except Exception:  # noqa: BLE001 — unmounted
            pass
        return md, txt

    def _as_markdown(self, title: str, text: str) -> None:
        self._set_title(title)
        md, _ = self._swap(markdown=True)
        if md is not None:
            md.update(text)

    def _as_text(self, title: str, text: str) -> None:
        self._set_title(title)
        _, txt = self._swap(markdown=False)
        if txt is not None:
            txt.update(text)

    def _as_rich(self, title: str, renderable: Any) -> None:
        self._set_title(title)
        _, txt = self._swap(markdown=False)
        if txt is not None:
            txt.update(renderable)

    @property
    def is_scrollable(self) -> bool:
        """A reader that cannot reach the bottom of a document is not a reader.

        (Textual only scrolls widgets with a layout or children; this one has
        both, but say so explicitly so a future refactor cannot quietly take
        it away — see GameStatePanel for the leaf-widget version of this trap.)
        """
        return True


class BuildStage(Horizontal):
    """The build-side furniture: tree on the left, reader on the right.

    Left/right rather than top/bottom because a terminal is wider than it is
    tall, and the conversation below needs every row it can get — a tree is
    narrow by nature, a document wants width.
    """

    def compose(self) -> ComposeResult:
        yield WorldTree(str(Path.cwd()), id="world-tree")
        yield DocReader(id="doc-reader")

    def set_root(self, root: Path) -> None:
        """Point the tree at this world."""
        try:
            tree = self.query_one("#world-tree", WorldTree)
            tree.path = str(root)
        except Exception:  # noqa: BLE001 — unmounted
            pass

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        event.stop()
        try:
            self.query_one("#doc-reader", DocReader).show_path(Path(event.path))
        except Exception:  # noqa: BLE001 — reader absent
            pass
