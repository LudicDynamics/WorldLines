"""Todo manager for conversation planning tools (M9-T2)."""

from __future__ import annotations

from dataclasses import dataclass


VALID_STATUSES = {"pending", "in_progress", "completed"}
MAX_TODO_ITEMS = 20


@dataclass(frozen=True)
class TodoItem:
    """A normalized todo item."""

    content: str
    status: str
    active_form: str

    def to_dict(self) -> dict[str, str]:
        return {
            "content": self.content,
            "status": self.status,
            "activeForm": self.active_form,
        }


class TodoManager:
    """Stateful todo list manager used by the `TodoWrite` tool."""

    def __init__(self, items: list[dict] | None = None) -> None:
        self._items: list[TodoItem] = []
        if items is not None:
            self.update(items)

    def update(self, items: list[dict]) -> list[dict]:
        """Replace todo list after validation.

        Rules:
        - At most 20 items.
        - Allowed statuses: pending/in_progress/completed (``done`` is silently
          normalized to ``completed`` for compatibility with weaker LLMs).
        - Non-empty lists may contain at most 1 in_progress item.
        - Required fields: content, status.  activeForm defaults to content if
          omitted (schema marks it required, but we tolerate omission).
        """
        if not isinstance(items, list):
            raise ValueError("items must be an array")
        if len(items) > MAX_TODO_ITEMS:
            raise ValueError(f"todo list exceeds max size ({MAX_TODO_ITEMS})")

        normalized: list[TodoItem] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"items[{index}] must be an object")

            for required in ("content", "status"):
                if required not in item:
                    raise ValueError(f"items[{index}] missing required field: {required}")

            content = str(item["content"]).strip()
            status_raw = str(item["status"]).strip()
            status = "completed" if status_raw == "done" else status_raw
            active_form = str(item.get("activeForm") or content).strip()

            if not content:
                raise ValueError(f"items[{index}].content cannot be empty")
            if not active_form:
                raise ValueError(f"items[{index}].activeForm cannot be empty")
            if status not in VALID_STATUSES:
                raise ValueError(
                    f"items[{index}].status must be one of: {', '.join(sorted(VALID_STATUSES))}, got: '{status}'"
                )

            normalized.append(TodoItem(content=content, status=status, active_form=active_form))

        in_progress_count = sum(1 for item in normalized if item.status == "in_progress")
        if normalized and in_progress_count > 1:
            raise ValueError("todo list must contain at most one in_progress item")

        self._items = normalized
        return self.snapshot()

    def snapshot(self) -> list[dict]:
        """Return current todo list in tool-friendly format."""
        return [item.to_dict() for item in self._items]

    def render(self) -> str:
        """Render todos as compact markdown-style checklist text."""
        if not self._items:
            return "(no todos)"

        marker = {
            "completed": "[x]",
            "in_progress": "[>]",
            "pending": "[ ]",
        }
        return "\n".join(f"{marker[item.status]} {item.active_form}" for item in self._items)
