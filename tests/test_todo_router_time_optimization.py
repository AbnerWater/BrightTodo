from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lifetrace.core.dependencies import get_todo_service, get_todo_time_optimization_service
from lifetrace.routers.todo import router
from lifetrace.schemas.todo import TodoTimeOptimizationRange, TodoTimeOptimizationResponse
from lifetrace.services.todo_time_optimization_service import TodoTimeOptimizationError

HTTP_OK = 200
HTTP_SERVICE_UNAVAILABLE = 503
EXPECTED_CONFIDENCE = 0.82


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class FakeTodoService:
    pass


class FakeOptimizationService:
    def optimize(self, todo_id: int, todo_service: FakeTodoService) -> TodoTimeOptimizationResponse:
        assert todo_id == 1
        assert isinstance(todo_service, FakeTodoService)
        return TodoTimeOptimizationResponse(
            todo_id=1,
            todo_name="写周报",
            before=TodoTimeOptimizationRange(
                start_time=_dt("2030-01-01T10:00:00+00:00"),
                end_time=_dt("2030-01-01T11:00:00+00:00"),
            ),
            after=TodoTimeOptimizationRange(
                start_time=_dt("2030-01-01T12:00:00+00:00"),
                end_time=_dt("2030-01-01T13:00:00+00:00"),
            ),
            has_conflict=True,
            conflicts=[],
            reason="避开冲突并保留专注时间。",
            confidence=EXPECTED_CONFIDENCE,
        )


class FakeErrorOptimizationService:
    def optimize(self, todo_id: int, todo_service: Any) -> TodoTimeOptimizationResponse:
        _ = todo_id, todo_service
        raise TodoTimeOptimizationError(
            HTTP_SERVICE_UNAVAILABLE,
            "LLM_UNAVAILABLE",
            "LLM 服务当前不可用，请检查配置",
        )


def _client(optimization_service: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_todo_service] = FakeTodoService
    app.dependency_overrides[get_todo_time_optimization_service] = lambda: optimization_service
    return TestClient(app)


def test_todo_time_optimization_endpoint_returns_preview_contract() -> None:
    client = _client(FakeOptimizationService())

    response = client.post("/api/todos/1/time-optimization")

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["todo_id"] == 1
    assert data["todo_name"] == "写周报"
    assert data["before"]["start_time"] == "2030-01-01T10:00:00Z"
    assert data["after"]["end_time"] == "2030-01-01T13:00:00Z"
    assert data["has_conflict"] is True
    assert data["reason"]
    assert data["confidence"] == EXPECTED_CONFIDENCE


def test_todo_time_optimization_endpoint_returns_domain_error_contract() -> None:
    client = _client(FakeErrorOptimizationService())

    response = client.post("/api/todos/1/time-optimization")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["error_code"] == "LLM_UNAVAILABLE"
    assert data["message"] == "LLM 服务当前不可用，请检查配置"
