from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lifetrace.routers.agent import router

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNPROCESSABLE_ENTITY = 422
TOO_LONG_TEXT_LENGTH = 501
SCHEDULE_TODO_ID = 101
FULL_COVERAGE = 100


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_parse_task_endpoint_returns_contract_fields() -> None:
    client = _client()

    response = client.post(
        "/api/agent/parse-task",
        json={
            "text": "下周一下午三点前完成操作系统作业，大概需要两个小时，比较紧急",
            "reference_time": "2026-05-19T10:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["task_title"] == "完成操作系统作业"
    assert data["priority"] == "high"
    assert data["due"] == "2026-05-25T15:00:00+08:00"
    assert data["duration"] == "PT2H"
    assert data["raw_text"]
    assert data["parse_version"]
    assert 0 <= data["confidence"] <= 1


def test_parse_task_endpoint_rejects_empty_text() -> None:
    client = _client()

    response = client.post("/api/agent/parse-task", json={"text": "   "})

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_parse_task_endpoint_rejects_long_text() -> None:
    client = _client()

    response = client.post(
        "/api/agent/parse-task", json={"text": "写" * TOO_LONG_TEXT_LENGTH}
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_schedule_suggest_endpoint_returns_contract_fields() -> None:
    client = _client()

    response = client.post(
        "/api/agent/schedule-suggest",
        json={
            "todos": [
                {
                    "id": 101,
                    "name": "完成操作系统作业",
                    "priority": "high",
                    "due": "2026-05-19T18:00:00+08:00",
                    "duration": "PT2H",
                }
            ],
            "schedule_constraints": [
                {
                    "weekday": 2,
                    "start_time": "10:00",
                    "end_time": "12:00",
                    "label": "操作系统课",
                }
            ],
            "planning_start": "2026-05-19T10:00:00+08:00",
            "planning_end": "2026-05-19T18:00:00+08:00",
            "daily_available_hours": 6,
        },
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["suggestions"][0]["todo_id"] == SCHEDULE_TODO_ID
    assert data["suggestions"][0]["suggested_start"] == "2026-05-19T12:00:00+08:00"
    assert data["suggestions"][0]["suggested_end"] == "2026-05-19T14:00:00+08:00"
    assert data["suggestions"][0]["alternatives"]
    assert data["unscheduled_todos"] == []
    assert data["planning_coverage_pct"] == FULL_COVERAGE


def test_schedule_suggest_endpoint_rejects_empty_todos() -> None:
    client = _client()

    response = client.post(
        "/api/agent/schedule-suggest",
        json={
            "todos": [],
            "planning_start": "2026-05-19T10:00:00+08:00",
            "planning_end": "2026-05-19T18:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_schedule_suggest_endpoint_rejects_invalid_priority_contract_error() -> None:
    client = _client()

    response = client.post(
        "/api/agent/schedule-suggest",
        json={
            "todos": [
                {
                    "id": 101,
                    "name": "完成操作系统作业",
                    "priority": "urgent",
                    "duration": "PT1H",
                }
            ],
            "planning_start": "2026-05-19T08:00:00+08:00",
            "planning_end": "2026-05-19T22:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_schedule_suggest_endpoint_requires_priority() -> None:
    client = _client()

    response = client.post(
        "/api/agent/schedule-suggest",
        json={
            "todos": [
                {
                    "id": 101,
                    "name": "完成操作系统作业",
                    "duration": "PT1H",
                }
            ],
            "planning_start": "2026-05-19T08:00:00+08:00",
            "planning_end": "2026-05-19T22:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_INPUT"


def test_schedule_suggest_endpoint_reports_no_available_slots() -> None:
    client = _client()

    response = client.post(
        "/api/agent/schedule-suggest",
        json={
            "todos": [
                {
                    "id": 101,
                    "name": "完成操作系统作业",
                    "priority": "high",
                    "duration": "PT1H",
                }
            ],
            "schedule_constraints": [
                {
                    "weekday": 2,
                    "start_time": "08:00",
                    "end_time": "22:00",
                    "label": "全天课程",
                }
            ],
            "planning_start": "2026-05-19T08:00:00+08:00",
            "planning_end": "2026-05-19T22:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert response.json()["error_code"] == "NO_AVAILABLE_SLOTS"
