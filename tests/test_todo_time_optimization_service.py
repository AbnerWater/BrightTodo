from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from lifetrace.schemas.todo import TodoResponse
from lifetrace.services.todo_time_optimization_service import (
    TodoTimeOptimizationError,
    TodoTimeOptimizationService,
)

CONFLICT_TODO_ID = 2
EXPECTED_CONFLICT_CONFIDENCE = 0.86


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
        "created_at": datetime(2029, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2029, 1, 1, tzinfo=UTC),
    }
    data.update(overrides)
    return TodoResponse(**data)


class FakeTodoService:
    def __init__(self, target: TodoResponse, active_todos: list[TodoResponse]) -> None:
        self.target = target
        self.active_todos = active_todos

    def get_todo(self, todo_id: int) -> TodoResponse:
        assert todo_id == self.target.id
        return self.target

    def list_todos(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["status"] == "active"
        return {"total": len(self.active_todos), "todos": self.active_todos}


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


def test_optimize_reports_conflict_and_returns_safe_recommendation() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )
    conflict = _todo(
        CONFLICT_TODO_ID,
        "项目会",
        start_time=_dt("2030-01-01T10:30:00+00:00"),
        end_time=_dt("2030-01-01T11:30:00+00:00"),
    )
    llm_client = FakeLlmClient(
        """
        {
          "recommended_start_time": "2030-01-01T12:00:00+00:00",
          "recommended_end_time": "2030-01-01T13:00:00+00:00",
          "reason": "避开会议冲突，保留整块时间。",
          "confidence": 0.86
        }
        """
    )

    result = _service(llm_client).optimize(1, FakeTodoService(target, [target, conflict]))

    assert result.has_conflict is True
    assert result.conflicts[0].id == CONFLICT_TODO_ID
    assert result.before.start_time == _dt("2030-01-01T10:00:00+00:00")
    assert result.after.start_time == _dt("2030-01-01T12:00:00+00:00")
    assert result.confidence == EXPECTED_CONFLICT_CONFIDENCE
    assert "active_todos" in llm_client.calls[0]["messages"][1]["content"]


def test_optimize_recommends_better_focus_time_when_no_conflict() -> None:
    target = _todo(
        1,
        "阅读论文",
        start_time=_dt("2030-01-01T08:00:00+00:00"),
        end_time=_dt("2030-01-01T09:00:00+00:00"),
    )
    other = _todo(
        2,
        "团队同步",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )
    llm_client = FakeLlmClient(
        """
        {
          "recommended_start_time": "2030-01-01T09:00:00+00:00",
          "recommended_end_time": "2030-01-01T10:00:00+00:00",
          "reason": "上午中段更适合专注阅读。",
          "confidence": 0.74
        }
        """
    )

    result = _service(llm_client).optimize(1, FakeTodoService(target, [target, other]))

    assert result.has_conflict is False
    assert result.conflicts == []
    assert result.after.end_time == _dt("2030-01-01T10:00:00+00:00")


def test_optimize_handles_todo_without_original_time() -> None:
    target = _todo(1, "整理材料")
    llm_client = FakeLlmClient(
        """
        {
          "recommended_start_time": "2030-01-02T08:00:00+00:00",
          "recommended_end_time": "2030-01-02T09:00:00+00:00",
          "reason": "安排到次日上午。",
          "confidence": 0.7
        }
        """
    )

    result = _service(llm_client).optimize(1, FakeTodoService(target, [target]))

    assert result.before.start_time is None
    assert result.before.end_time is None
    assert result.after.start_time == _dt("2030-01-02T08:00:00+00:00")


def test_optimize_raises_when_llm_is_unavailable() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(FakeUnavailableLlmClient()).optimize(1, FakeTodoService(target, [target]))

    assert exc_info.value.error_code == "LLM_UNAVAILABLE"


def test_optimize_raises_when_llm_returns_invalid_json() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(FakeLlmClient("not-json")).optimize(1, FakeTodoService(target, [target]))

    assert exc_info.value.error_code == "LLM_RESPONSE_INVALID"


def test_optimize_rejects_recommendation_that_still_conflicts() -> None:
    target = _todo(
        1,
        "写周报",
        start_time=_dt("2030-01-01T10:00:00+00:00"),
        end_time=_dt("2030-01-01T11:00:00+00:00"),
    )
    conflict = _todo(
        2,
        "项目会",
        start_time=_dt("2030-01-01T12:30:00+00:00"),
        end_time=_dt("2030-01-01T13:30:00+00:00"),
    )
    llm_client = FakeLlmClient(
        """
        {
          "recommended_start_time": "2030-01-01T12:00:00+00:00",
          "recommended_end_time": "2030-01-01T13:00:00+00:00",
          "reason": "仍然冲突的推荐。",
          "confidence": 0.5
        }
        """
    )

    with pytest.raises(TodoTimeOptimizationError) as exc_info:
        _service(llm_client).optimize(1, FakeTodoService(target, [target, conflict]))

    assert exc_info.value.error_code == "RECOMMENDATION_CONFLICT"
