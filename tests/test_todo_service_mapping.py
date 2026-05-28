from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from lifetrace.schemas.todo import TodoCreate, TodoUpdate
from lifetrace.services.todo_service import TodoService


class FakeTodoRepository:
    def __init__(self) -> None:
        now = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        self.todo = {
            "id": 1,
            "uid": "todo-1",
            "name": "Test",
            "item_type": "VTODO",
            "status": "active",
            "priority": "none",
            "created_at": now,
            "updated_at": now,
        }
        self.updated: dict[str, object] | None = None
        self.created_payload: dict[str, object] | None = None

    def get_by_id(self, _todo_id: int):
        return self.todo

    def get_by_uid(self, _uid: str):
        return None

    def list_todos(self, _limit: int, _offset: int, _status: str | None):
        return []

    def count(self, _status: str | None):
        return 0

    def create(self, **kwargs):
        self.created_payload = kwargs
        return 1

    def update(self, _todo_id: int, **kwargs):
        self.updated = kwargs
        return True

    def delete(self, _todo_id: int):
        return True

    def reorder(self, _items):
        return True

    def add_attachment(
        self,
        *,
        _todo_id: int,
        _file_name: str,
        _file_path: str,
        _file_size: int | None,
        _mime_type: str | None,
        _file_hash: str | None,
        _source: str = "user",
    ):
        return None

    def remove_attachment(self, *, _todo_id: int, _attachment_id: int):
        return True

    def get_attachment(self, _attachment_id: int):
        return None


def test_update_todo_dtstart_does_not_touch_due() -> None:
    repo = FakeTodoRepository()
    service = TodoService(repo)
    dtstart = datetime(2024, 1, 1, 10, 0, tzinfo=UTC)

    service.update_todo(1, TodoUpdate(dtstart=dtstart))

    assert repo.updated is not None
    assert "due" not in repo.updated
    assert repo.updated["dtstart"] == dtstart
    assert repo.updated["start_time"] == dtstart


def test_update_todo_due_duration_keeps_deadline() -> None:
    repo = FakeTodoRepository()
    service = TodoService(repo)
    due = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)

    service.update_todo(1, TodoUpdate(duration="PT30M", due=due))

    assert repo.updated is not None
    assert repo.updated["duration"] == "PT30M"
    assert repo.updated["due"] == due
    assert repo.updated["deadline"] == due


def test_create_todo_due_duration_keeps_deadline() -> None:
    repo = FakeTodoRepository()
    service = TodoService(repo)
    due = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)

    service.create_todo(TodoCreate(name="Test", duration="PT30M", due=due))

    assert repo.created_payload is not None
    assert repo.created_payload["duration"] == "PT30M"
    assert repo.created_payload["due"] == due
    assert repo.created_payload["deadline"] == due


def test_create_todo_duration_dtend_conflict_raises() -> None:
    repo = FakeTodoRepository()
    service = TodoService(repo)
    dtend = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)

    with pytest.raises(HTTPException):
        service.create_todo(TodoCreate(name="Test", duration="PT30M", dtend=dtend))


def test_update_todo_time_zone_sets_tzid() -> None:
    repo = FakeTodoRepository()
    service = TodoService(repo)

    service.update_todo(1, TodoUpdate(time_zone="Asia/Shanghai"))

    assert repo.updated is not None
    assert repo.updated["time_zone"] == "Asia/Shanghai"
    assert repo.updated["tzid"] == "Asia/Shanghai"
