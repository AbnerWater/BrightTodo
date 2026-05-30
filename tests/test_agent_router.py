from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lifetrace.core.dependencies import get_todo_service
from lifetrace.routers.agent import router
from lifetrace.services.agent_import_service import MAX_IMPORT_FILE_BYTES

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_CONTENT_TOO_LARGE = 413
HTTP_UNPROCESSABLE_ENTITY = 422
TOO_LONG_TEXT_LENGTH = 501
SCHEDULE_TODO_ID = 101
FULL_COVERAGE = 100

if TYPE_CHECKING:
    import pytest


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class FakeTodoService:
    def __init__(self) -> None:
        self.created = []
        self.deleted = []
        self.attachments = []

    def list_todos(self, **_kwargs: object):
        return {"total": 0, "todos": []}

    def create_todo(self, data):
        self.created.append(data)
        return SimpleNamespace(id=len(self.created), name=data.name, status=data.status.value)

    def delete_todo(self, todo_id: int) -> None:
        self.deleted.append(todo_id)

    def add_attachment(
        self,
        *,
        todo_id: int,
        file_name: str,
        file_path: str,
        file_size: int | None,
        mime_type: str | None,
        file_hash: str | None,
        source: str = "user",
    ):
        _ = file_hash
        item = SimpleNamespace(
            id=len(self.attachments) + 1,
            todo_id=todo_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            source=source,
        )
        self.attachments.append(item)
        return item


class FakeRouterLlmClient:
    def is_available(self) -> bool:
        return True

    def chat(self, messages, temperature: float, max_tokens: int) -> str:
        _ = messages, temperature, max_tokens
        return """
        {
          "summary": "根据附件生成规划",
          "todos": [
            {
              "title": "准备课程项目展示",
              "description": "整理展示材料",
              "priority": "medium",
              "duration": "PT2H",
              "source_file_indices": [0],
              "source_text": "Course project requires presentation.",
              "confidence": 0.8
            }
          ]
        }
        """


def _client_with_todo_service(fake_service: FakeTodoService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_todo_service] = lambda: fake_service
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


def test_import_todos_endpoint_parses_text_file() -> None:
    client = _client_with_todo_service(FakeTodoService())

    response = client.post(
        "/api/agent/import-todos",
        files={
            "files": (
                "tasks.txt",
                "明天下午三点前完成数学作业，大概需要两个小时".encode(),
                "text/plain",
            )
        },
        data={"reference_time": "2026-05-19T10:00:00+08:00", "create_todos": "false"},
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["file_results"][0]["status"] == "success"
    assert data["extracted_tasks"][0]["task_title"] == "完成数学作业"
    assert data["created_todos"] == []


def test_import_todos_endpoint_can_create_draft_todos() -> None:
    fake_service = FakeTodoService()
    client = _client_with_todo_service(fake_service)

    response = client.post(
        "/api/agent/import-todos",
        files={
            "files": (
                "tasks.md",
                "- 后天回复导师邮件，紧急".encode(),
                "text/markdown",
            )
        },
        data={"reference_time": "2026-05-19T10:00:00+08:00", "create_todos": "true"},
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["created_todos"][0]["name"] == "回复导师邮件"
    assert fake_service.created[0].status.value == "draft"


def test_import_todos_endpoint_rejects_invalid_file_type() -> None:
    client = _client_with_todo_service(FakeTodoService())

    response = client.post(
        "/api/agent/import-todos",
        files={"files": ("archive.zip", b"zip", "application/zip")},
    )

    assert response.status_code == HTTP_BAD_REQUEST
    assert response.json()["error_code"] == "INVALID_FILE_TYPE"


def test_import_todos_endpoint_rejects_large_file_before_service_processing() -> None:
    client = _client_with_todo_service(FakeTodoService())

    response = client.post(
        "/api/agent/import-todos",
        files={
            "files": (
                "large.txt",
                b"x" * (MAX_IMPORT_FILE_BYTES + 2),
                "text/plain",
            )
        },
    )

    assert response.status_code == HTTP_CONTENT_TOO_LARGE
    assert response.json()["error_code"] == "FILE_TOO_LARGE"


def test_attachment_plan_endpoint_returns_confirmable_schedule(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_llm_client",
        lambda: FakeRouterLlmClient(),
    )
    client = _client_with_todo_service(FakeTodoService())

    response = client.post(
        "/api/agent/attachment-plan",
        files={
            "files": (
                "course.txt",
                b"Course project requires presentation.",
                "text/plain",
            )
        },
        data={
            "prompt": "请根据附件生成日程规划",
            "reference_time": "2026-05-30T10:00:00+08:00",
            "planning_start": "2026-05-30T10:00:00+08:00",
        },
    )

    assert response.status_code == HTTP_OK
    data = response.json()
    assert data["plan_id"]
    assert data["file_results"][0]["status"] == "ready"
    assert data["proposed_todos"][0]["title"] == "准备课程项目展示"
    assert data["proposed_todos"][0]["duration"] == "PT2H"


def test_attachment_plan_confirm_creates_draft_and_ai_attachment(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_llm_client",
        lambda: FakeRouterLlmClient(),
    )
    fake_service = FakeTodoService()
    client = _client_with_todo_service(fake_service)

    plan_response = client.post(
        "/api/agent/attachment-plan",
        files={"files": ("course.txt", b"Course project requires presentation.", "text/plain")},
        data={
            "prompt": "请根据附件生成日程规划",
            "reference_time": "2026-05-30T10:00:00+08:00",
            "planning_start": "2026-05-30T10:00:00+08:00",
        },
    )
    plan_data = plan_response.json()

    response = client.post(
        f"/api/agent/attachment-plan/{plan_data['plan_id']}/confirm",
        json={"proposed_todos": plan_data["proposed_todos"]},
    )

    assert response.status_code == HTTP_OK
    assert response.json()["created_todos"][0]["name"] == "准备课程项目展示"
    assert fake_service.created[0].status.value == "draft"
    assert fake_service.attachments[0].source == "ai"
    assert fake_service.attachments[0].file_name == "course.txt"
