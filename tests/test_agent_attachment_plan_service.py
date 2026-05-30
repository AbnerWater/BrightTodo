from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from lifetrace.schemas.todo import TodoStatus
from lifetrace.services.agent_attachment_plan_service import (
    AgentAttachmentPlanService,
    AttachmentPlanError,
)
from lifetrace.services.agent_import_service import AgentImportFile

HTTP_SERVICE_UNAVAILABLE = 503
HTTP_BAD_REQUEST = 400
HTTP_BAD_GATEWAY = 502
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 2600


class FakeUnavailableLlmClient:
    def is_available(self) -> bool:
        return False


class FakeTextLlmClient:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.messages = []

    def is_available(self) -> bool:
        return True

    def chat(self, messages, temperature: float, max_tokens: int) -> str:
        self.messages = messages
        assert temperature == LLM_TEMPERATURE
        assert max_tokens == LLM_MAX_TOKENS
        return self.response_text


class FakeFailingLlmClient:
    def is_available(self) -> bool:
        return True

    def chat(self, messages, temperature: float, max_tokens: int) -> str:
        _ = messages, temperature, max_tokens
        raise RuntimeError("invalid api key")


class FakeVisionCompletions:
    def __init__(self, owner) -> None:
        self.owner = owner

    def create(self, **kwargs):
        self.owner.kwargs = kwargs
        message = SimpleNamespace(content=self.owner.response_text)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeVisionLlmClient:
    model = "fake-text-model"

    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.kwargs = {}
        self.chat = SimpleNamespace(
            completions=FakeVisionCompletions(self),
        )

    def is_available(self) -> bool:
        return True

    def _get_client(self):
        return self


class FakeTodoService:
    def __init__(self) -> None:
        self.created = []
        self.deleted = []
        self.attachments = []

    def create_todo(self, data):
        self.created.append(data)
        return SimpleNamespace(
            id=len(self.created),
            name=data.name,
            status=data.status.value if hasattr(data.status, "value") else data.status,
        )

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
        item = SimpleNamespace(
            id=len(self.attachments) + 1,
            todo_id=todo_id,
            file_name=file_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            file_hash=file_hash,
            source=source,
        )
        self.attachments.append(item)
        return item


class FailingAttachmentTodoService(FakeTodoService):
    def add_attachment(self, **_kwargs):
        raise RuntimeError("attachment failed")


class RealisticTodoService(FakeTodoService):
    def create_todo(self, data):
        if data.duration and data.end_time:
            raise HTTPException(
                status_code=400,
                detail="duration 与 dtend 互斥，请只保留一个",
            )
        return super().create_todo(data)


def _reference_time() -> datetime:
    return datetime.fromisoformat("2026-05-30T10:00:00+08:00")


def _txt_file(text: str, name: str = "course.txt") -> AgentImportFile:
    return AgentImportFile(
        file_name=name,
        mime_type="text/plain",
        content=text.encode("utf-8"),
    )


def _plan_response() -> str:
    return """
    {
      "summary": "已根据课程资料生成学习安排",
      "todos": [
        {
          "title": "准备课程项目展示",
          "description": "整理项目亮点并制作展示材料",
          "priority": "medium",
          "due": null,
          "duration": "PT2H",
          "source_file_indices": [0],
          "source_text": "Course project requires a group presentation and final report.",
          "confidence": 0.86
        }
      ]
    }
    """


def test_attachment_plan_uses_llm_and_confirm_binds_source_attachment(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    fake_llm = FakeTextLlmClient(_plan_response())
    service = AgentAttachmentPlanService(llm_client=fake_llm)

    response = service.create_plan(
        files=[
            _txt_file(
                "Course project requires a group presentation and final report.",
            )
        ],
        prompt="请根据附件生成日程规划",
        reference_time=_reference_time(),
        planning_start=_reference_time(),
        planning_end=None,
        daily_available_hours=6,
    )

    assert response.file_results[0].status == "ready"
    assert response.proposed_todos[0].title == "准备课程项目展示"
    assert response.proposed_todos[0].duration == "PT2H"
    assert response.proposed_todos[0].suggested_start is not None
    assert "Course project requires" in fake_llm.messages[1]["content"]

    fake_todo_service = FakeTodoService()
    confirm_response = service.confirm_plan(
        plan_id=response.plan_id,
        proposed_todos=response.proposed_todos,
        todo_service=fake_todo_service,
    )

    assert confirm_response.created_todos[0].name == "准备课程项目展示"
    assert fake_todo_service.created[0].status == TodoStatus.DRAFT
    assert fake_todo_service.attachments[0].source == "ai"
    assert fake_todo_service.attachments[0].file_name == "course.txt"
    assert Path(fake_todo_service.attachments[0].file_path).exists()
    assert not (tmp_path / "agent-plans" / response.plan_id).exists()


def test_confirm_plan_omits_duration_when_fixed_time_slot_exists(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    service = AgentAttachmentPlanService(llm_client=FakeTextLlmClient(_plan_response()))
    response = service.create_plan(
        files=[_txt_file("Course project requires a group presentation and final report.")],
        prompt="请根据附件生成日程规划",
        reference_time=_reference_time(),
        planning_start=_reference_time(),
        planning_end=None,
        daily_available_hours=6,
    )

    fake_todo_service = RealisticTodoService()
    service.confirm_plan(
        plan_id=response.plan_id,
        proposed_todos=response.proposed_todos,
        todo_service=fake_todo_service,
    )

    assert fake_todo_service.created[0].start_time is not None
    assert fake_todo_service.created[0].end_time is not None
    assert fake_todo_service.created[0].duration is None


def test_confirm_plan_rolls_back_todo_when_attachment_binding_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    service = AgentAttachmentPlanService(llm_client=FakeTextLlmClient(_plan_response()))
    response = service.create_plan(
        files=[_txt_file("Course project requires a group presentation and final report.")],
        prompt="请根据附件生成日程规划",
        reference_time=_reference_time(),
        planning_start=_reference_time(),
        planning_end=None,
        daily_available_hours=6,
    )
    fake_todo_service = FailingAttachmentTodoService()

    with pytest.raises(AttachmentPlanError) as exc_info:
        service.confirm_plan(
            plan_id=response.plan_id,
            proposed_todos=response.proposed_todos,
            todo_service=fake_todo_service,
        )

    assert exc_info.value.error_code == "TODO_CREATE_FAILED"
    assert fake_todo_service.deleted == [1]


def test_cleanup_expired_plans_removes_old_plan_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    old_plan_dir = tmp_path / "agent-plans" / ("a" * 32)
    old_plan_dir.mkdir(parents=True)
    old_plan_dir.joinpath("manifest.json").write_text("{}", encoding="utf-8")
    old_time = datetime.fromisoformat("2026-05-28T10:00:00+08:00").timestamp()

    os.utime(old_plan_dir, (old_time, old_time))
    service = AgentAttachmentPlanService(llm_client=FakeTextLlmClient(_plan_response()))

    service.cleanup_expired_plans(now=_reference_time())

    assert not old_plan_dir.exists()


def test_attachment_plan_rejects_when_llm_unavailable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    service = AgentAttachmentPlanService(llm_client=FakeUnavailableLlmClient())

    with pytest.raises(AttachmentPlanError) as exc_info:
        service.create_plan(
            files=[_txt_file("课程要求完成展示。")],
            prompt="请生成规划",
            reference_time=_reference_time(),
            planning_start=None,
            planning_end=None,
            daily_available_hours=None,
        )

    assert exc_info.value.status_code == HTTP_SERVICE_UNAVAILABLE
    assert exc_info.value.error_code == "LLM_UNAVAILABLE"


def test_attachment_plan_wraps_llm_request_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    service = AgentAttachmentPlanService(llm_client=FakeFailingLlmClient())

    with pytest.raises(AttachmentPlanError) as exc_info:
        service.create_plan(
            files=[_txt_file("课程要求完成展示。")],
            prompt="请生成规划",
            reference_time=_reference_time(),
            planning_start=None,
            planning_end=None,
            daily_available_hours=None,
        )

    assert exc_info.value.status_code == HTTP_BAD_GATEWAY
    assert exc_info.value.error_code == "LLM_REQUEST_FAILED"
    plans_dir = tmp_path / "agent-plans"
    assert not plans_dir.exists() or not any(plans_dir.iterdir())


def test_attachment_plan_rejects_empty_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    service = AgentAttachmentPlanService(llm_client=FakeTextLlmClient(_plan_response()))

    with pytest.raises(AttachmentPlanError) as exc_info:
        service.create_plan(
            files=[_txt_file("课程要求完成展示。")],
            prompt="  ",
            reference_time=_reference_time(),
            planning_start=None,
            planning_end=None,
            daily_available_hours=None,
        )

    assert exc_info.value.status_code == HTTP_BAD_REQUEST
    assert exc_info.value.error_code == "INVALID_INPUT"


def test_attachment_plan_sends_images_as_multimodal_content(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "lifetrace.services.agent_attachment_plan_service.get_attachments_dir",
        lambda: tmp_path,
    )
    fake_llm = FakeVisionLlmClient(_plan_response())
    service = AgentAttachmentPlanService(llm_client=fake_llm)

    response = service.create_plan(
        files=[
            AgentImportFile(
                file_name="board.png",
                mime_type="image/png",
                content=b"\x89PNG\r\n\x1a\n",
            )
        ],
        prompt="请根据图片生成日程规划",
        reference_time=_reference_time(),
        planning_start=_reference_time(),
        planning_end=None,
        daily_available_hours=6,
    )

    messages = fake_llm.kwargs["messages"]
    user_content = messages[1]["content"]
    assert any(item.get("type") == "image_url" for item in user_content)
    assert response.proposed_todos[0].source_files == ["board.png"]
