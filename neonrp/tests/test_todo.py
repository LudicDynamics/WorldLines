"""Tests for todo manager (M9-T2)."""

import pytest

from neonrp.core.todo import MAX_TODO_ITEMS, TodoManager


def _valid_items() -> list[dict]:
    return [
        {"content": "Read files", "status": "completed", "activeForm": "Reading files"},
        {"content": "Write plan", "status": "in_progress", "activeForm": "Writing plan"},
        {"content": "Apply patch", "status": "pending", "activeForm": "Applying patch"},
    ]


class TestTodoManager:
    def test_valid_update_and_render(self):
        manager = TodoManager()
        snapshot = manager.update(_valid_items())

        assert len(snapshot) == 3
        assert snapshot[1]["status"] == "in_progress"
        assert manager.render() == "[x] Reading files\n[>] Writing plan\n[ ] Applying patch"

    def test_update_replaces_previous_items(self):
        manager = TodoManager(_valid_items())
        manager.update([{"content": "Only one", "status": "in_progress", "activeForm": "Only one"}])

        assert manager.snapshot() == [{"content": "Only one", "status": "in_progress", "activeForm": "Only one"}]

    def test_rejects_more_than_max_items(self):
        manager = TodoManager()
        items = [
            {"content": f"Task {index}", "status": "pending", "activeForm": f"Task {index}"}
            for index in range(MAX_TODO_ITEMS + 1)
        ]
        # Make status constraints pass except length.
        items[0]["status"] = "in_progress"

        with pytest.raises(ValueError, match="exceeds max size"):
            manager.update(items)

    def test_allows_non_empty_list_without_in_progress(self):
        manager = TodoManager()
        snapshot = manager.update(
            [
                {"content": "A", "status": "pending", "activeForm": "A"},
                {"content": "B", "status": "completed", "activeForm": "B"},
            ]
        )
        assert len(snapshot) == 2

    def test_rejects_multiple_in_progress(self):
        manager = TodoManager()
        with pytest.raises(ValueError, match="at most one in_progress"):
            manager.update(
                [
                    {"content": "A", "status": "in_progress", "activeForm": "Doing A"},
                    {"content": "B", "status": "in_progress", "activeForm": "Doing B"},
                ]
            )

    def test_active_form_defaults_to_content_when_missing(self):
        manager = TodoManager()
        snapshot = manager.update([{"content": "A", "status": "in_progress"}])
        assert snapshot == [{"content": "A", "status": "in_progress", "activeForm": "A"}]

    def test_accepts_done_status_alias(self):
        manager = TodoManager()
        snapshot = manager.update([{"content": "A", "status": "done"}])
        assert snapshot == [{"content": "A", "status": "completed", "activeForm": "A"}]

    def test_rejects_invalid_status(self):
        manager = TodoManager()
        with pytest.raises(ValueError, match="must be one of"):
            manager.update([{"content": "A", "status": "doing", "activeForm": "A"}])

    def test_empty_list_is_allowed(self):
        manager = TodoManager(_valid_items())
        manager.update([])
        assert manager.snapshot() == []
        assert manager.render() == "(no todos)"
