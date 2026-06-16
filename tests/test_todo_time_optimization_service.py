from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from lifetrace.schemas.todo import TodoResponse
from lifetrace.services.todo_time_optimization_service import (
    TodoTimeOptimizationError,
    TodoTimeOptimizationService,
)

EXTERNAL_CONFLICT_TODO_ID = 6
EXPECTED_GROUP_ITEM_COUNT = 2


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return _dt("2029-12-31T00:00:00+00:00")


def _todo(
    todo_id: int,
    name: str,
    **overrides: Any,
) -> TodoResponse:
    data: dict[str, Any] = {
        "id": todo_id,
        "uid": f"todo-{todo_id}",
        "name": name,
        "status": "active",
        "priority": "medium",
        "created_at": datetime(2029, 1, todo_id, tzinfo=UTC),
        "updated_at": datetime(2029, 1, todo_id, tzinfo=UTC),
        "order": todo_id,
    }
    data.update(overrides)
    return TodoResponse(**data)


def _llm_response(*items: dict[str, Any], summary: str = "父子任务已联合优化。") -> str:
    return json.dumps({"summary": summary, "items": list(items)}, ensure_ascii=False)


def _item(todo_id: int, start: str, end: str, reason: str = "推荐更合适的时间") -> dict[str, Any]:
    return {
        "todo_id": todo_id,
        "recommended_start_time": start,
        "recommended_end_time": end,
        "reason": reason,
        "confidence": 0.82,
    }


class FakeTodoService:
    def __init__(self, target_id: int, todos: list[TodoResponse]) -> None:
        self.target_id = target_id
        self.todos = todos

    def get_todo(self, todo_id: int) -> TodoResponse:
        assert todo_id == self.target_id
        for todo in self.todos:
            if todo.id == todo_id:
                return todo
        raise AssertionError(f"todo not found: {todo_id}")

    def list_todos(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["status"] is None
        return {"total": len(self.todos), "todos": self.todos}


class FakeLlmClient:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    def chat(self, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
        self.calls.append(
            {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.response_text


class FakeUnavailableLlmClient:
    def is_available(self) -> bool:
        return False


def _service(llm_client: Any) -> TodoTimeOptimizationService:
    return TodoTimeOptimizationService(llm_client=llm_client, now_provider=_now)


def test_optimize_includes_active_and_draft_descendants_and_reports_conflicts() -> None:
    parent = _todo(
        1,
        "发布准备",
        start_time=_dt("2030-01-01T09:00:00+00:00"),
        end_time=_dt("2030-01-01T12:00:00+00:00"),
    )
    active_child = _todo(
        2,
        "整理清单",
        parent_todo_id=1,
        start_time=_dt("2030-01-01T09:00:00+00:00"),
        end_time=_dt("2030-01-01T10:00:00+00:00"),
    )
    draft_grandchild = _todo(
        3,
        "检查素材",
        parent_todo_id=2,
        status="draft",
        start_time=_dt("2030-01-01T10:30:00+00:00"),
        end_time=_dt("2030-01-01T11:30:00+00:00"),
    )
    completed_child = _todo(4, "已完成项", parent_todo_id=1, status="completed")
    canceled_child = _todo(5, "已取消项", parent_todo_id=1, status="canceled")
    external = _todo(
        6,
        "客户会议",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )
    llm_client = FakeLlmClient(
        _llm_response(
            _item(1, "2030-01-01T12:00:00+00:00", "2030-01-01T15:00:00+00:00"),
            _item(2, "2030-01-01T12:00:00+00:00", "2030-01-01T13:00:00+00:00"),
            _item(3, "2030-01-01T13:00:00+00:00", "2030-01-01T14:00:00+00:00"),
        )
    )

    result = _service(llm_client).optimize(
        1,
        FakeTodoService(
            1,
            [parent, active_child, draft_grandchild, completed_child, canceled_child, external],
        ),
    )

    assert [item.todo_id for item in result.items] == [1, 2, 3]
    assert result.items[2].status == "draft"
    assert result.has_conflict is True
    assert {conflict.id for conflict in result.conflicts} == {EXTERNAL_CONFLICT_TODO_ID}
    assert result.items[2].conflicts[0].id == EXTERNAL_CONFLICT_TODO_ID
    prompt = llm_client.calls[0]["messages"][1]["content"]
    assert "optimization_todos" in prompt
    assert "已完成项" not in prompt
    assert "已取消项" not in prompt


def test_optimize_recommends_better_focus_time_when_group_has_no_conflict() -> None:
    parent = _todo(
        1,
        "论文阅读",
        start_time=_dt("2030-01-01T08:00:00+00:00"),
        end_time=_dt("2030-01-01T10:00:00+00:00"),
    )
    child = _todo(
        2,
        "记录笔记",
        parent_todo_id=1,
        start_time=_dt("2030-01-01T08:30:00+00:00"),
        end_time=_dt("2030-01-01T09:30:00+00:00"),
    )
    llm_client = FakeLlmClient(
        _llm_response(
            _item(1, "2030-01-02T08:00:00+00:00", "2030-01-02T10:00:00+00:00"),
            _item(2, "2030-01-02T08:30:00+00:00", "2030-01-02T09:30:00+00:00"),
        )
    )

    result = _service(llm_client).optimize(1, FakeTodoService(1, [parent, child]))

    assert result.has_conflict is False
    assert result.conflicts == []
    assert len(result.items) == EXPECTED_GROUP_ITEM_COUNT
    assert result.items[1].after.start_time == _dt("2030-01-02T08:30:00+00:00")


def test_optimize_expands_parent_range_to_cover_child_recommendations() -> None:
    parent = _todo(
        1,
        "方案设计",
        start_time=_dt("2030-01-01T09:00:00+00:00"),
        end_time=_dt("2030-01-01T10:00:00+00:00"),
    )
    child = _todo(2, "画草图", parent_todo_id=1)
    llm_client = FakeLlmClient(
        _llm_response(
            _item(1, "2030-01-02T09:00:00+00:00", "2030-01-02T10:00:00+00:00"),
            _item(2, "2030-01-02T14:00:00+00:00", "2030-01-02T15:00:00+00:00"),
        )
    )

    result = _service(llm_client).optimize(1, FakeTodoService(1, [parent, child]))

    assert result.after.start_time == _dt("2030-01-02T09:00:00+00:00")
    assert result.after.end_time == _dt("2030-01-02T15:00:00+00:00")
    assert result.items[0].after.end_time == _dt("2030-01-02T15:00:00+00:00")


def test_optimize_handles_todos_without_original_time() -> None:
    parent = _todo(1, "整理材料")
    child = _todo(2, "补充附件", parent_todo_id=1)
    llm_client = FakeLlmClient(
        _llm_response(
            _item(1, "2030-01-02T08:00:00+00:00", "2030-01-02T10:00:00+00:00"),
            _item(2, "2030-01-02T08:30:00+00:00", "2030-01-02T09:30:00+00:00"),
        )
    )

    result = _service(llm_client).optimize(1, FakeTodoService(1, [parent, child]))

    assert result.items[0].before.start_time is None
    assert result.items[1].before.end_time is None


def test_optimize_raises_when_llm_is_unavailable() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(FakeUnavailableLlmClient()).optimize(1, FakeTodoService(1, [target]))

    assert exc_info.value.error_code == "LLM_UNAVAILABLE"


def test_optimize_raises_when_llm_returns_invalid_json() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(FakeLlmClient("not-json")).optimize(1, FakeTodoService(1, [target]))

    assert exc_info.value.error_code == "LLM_RESPONSE_INVALID"


def test_optimize_rejects_response_missing_participating_child() -> None:
    parent = _todo(1, "发布准备")
    child = _todo(2, "整理清单", parent_todo_id=1)
    llm_client = FakeLlmClient(
        _llm_response(_item(1, "2030-01-02T08:00:00+00:00", "2030-01-02T09:00:00+00:00"))
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(llm_client).optimize(1, FakeTodoService(1, [parent, child]))

    assert exc_info.value.error_code == "LLM_RESPONSE_INVALID"
    assert exc_info.value.detail == "missing_todo_ids=[2]"


def test_optimize_rejects_recommendation_that_still_conflicts_with_external_active_todo() -> None:
    parent = _todo(1, "写周报")
    conflict = _todo(
        2,
        "项目会",
        start_time=_dt("2030-01-01T12:30:00+00:00"),
        end_time=_dt("2030-01-01T13:30:00+00:00"),
    )
    llm_client = FakeLlmClient(
        _llm_response(_item(1, "2030-01-01T12:00:00+00:00", "2030-01-01T13:00:00+00:00"))
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(llm_client).optimize(1, FakeTodoService(1, [parent, conflict]))

    assert exc_info.value.error_code == "RECOMMENDATION_CONFLICT"


def test_optimize_rejects_internal_conflict_between_non_ancestor_tasks() -> None:
    parent = _todo(1, "发布准备")
    left = _todo(2, "整理清单", parent_todo_id=1)
    right = _todo(3, "检查素材", parent_todo_id=1)
    llm_client = FakeLlmClient(
        _llm_response(
            _item(1, "2030-01-02T08:00:00+00:00", "2030-01-02T10:00:00+00:00"),
            _item(2, "2030-01-02T08:30:00+00:00", "2030-01-02T09:30:00+00:00"),
            _item(3, "2030-01-02T09:00:00+00:00", "2030-01-02T10:00:00+00:00"),
        )
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(llm_client).optimize(1, FakeTodoService(1, [parent, left, right]))

    assert exc_info.value.error_code == "RECOMMENDATION_GROUP_CONFLICT"


def test_optimize_rejects_recommendation_in_past_and_invalid_range() -> None:
    target = _todo(1, "写周报")
    llm_client = FakeLlmClient(
        _llm_response(_item(1, "2029-12-30T12:00:00+00:00", "2029-12-30T13:00:00+00:00"))
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(llm_client).optimize(1, FakeTodoService(1, [target]))

    assert exc_info.value.error_code == "RECOMMENDATION_IN_PAST"

    invalid_range_client = FakeLlmClient(
        _llm_response(_item(1, "2030-01-01T13:00:00+00:00", "2030-01-01T12:00:00+00:00"))
    )
    with pytest.raises(TodoTimeOptimizationError) as invalid_exc:
        _service(invalid_range_client).optimize(1, FakeTodoService(1, [target]))

    assert invalid_exc.value.error_code == "RECOMMENDATION_INVALID"
