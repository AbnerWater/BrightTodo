from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lifetrace.routers.agent import router

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
TOO_LONG_TEXT_LENGTH = 501


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
