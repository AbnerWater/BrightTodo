from __future__ import annotations

from datetime import datetime
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from lifetrace.schemas.todo import TodoStatus
from lifetrace.services.agent_import_service import (
    MAX_IMPORT_FILE_BYTES,
    MAX_IMPORT_FILE_COUNT,
    AgentImportFile,
    AgentImportService,
    ImportTodosError,
)

HTTP_BAD_REQUEST = 400
HTTP_CONTENT_TOO_LARGE = 413
EXPECTED_TEXT_TASK_COUNT = 2
IMAGE_CONFIDENCE = 0.82


class FakeTodoService:
    def __init__(self) -> None:
        self.created = []

    def list_todos(self, **_kwargs: object):
        return {"total": 0, "todos": []}

    def create_todo(self, data):
        self.created.append(data)
        return SimpleNamespace(id=len(self.created), name=data.name, status=data.status.value)


class FailingAfterFirstTodoService(FakeTodoService):
    def __init__(self) -> None:
        super().__init__()
        self.deleted: list[int] = []

    def create_todo(self, data):
        if self.created:
            raise RuntimeError("模拟创建失败")
        return super().create_todo(data)

    def delete_todo(self, todo_id: int) -> None:
        self.deleted.append(todo_id)


def _reference_time() -> datetime:
    return datetime.fromisoformat("2026-05-19T10:00:00+08:00")


def _service() -> AgentImportService:
    return AgentImportService()


def _txt_file(content: str, name: str = "tasks.txt") -> AgentImportFile:
    return AgentImportFile(
        file_name=name,
        mime_type="text/plain",
        content=content.encode("utf-8"),
    )


def _build_docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("明天下午三点前完成软件工程报告，大概需要两个小时，紧急")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "后天回复导师邮件"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_pdf_bytes() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=240, height=240)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    page[NameObject("/Resources")] = resources
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 120 Td (TODO finish report tomorrow) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_import_text_file_extracts_multiple_tasks_without_creating() -> None:
    fake_todo_service = FakeTodoService()

    response = _service().import_files(
        files=[
            _txt_file(
                "- 明天下午三点前完成数学作业，大概需要两个小时\n"
                "- 后天回复导师邮件，紧急"
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=fake_todo_service,
    )

    assert response.file_results[0].status == "success"
    assert response.file_results[0].extracted_count == EXPECTED_TEXT_TASK_COUNT
    assert {task.task_title for task in response.extracted_tasks} == {
        "完成数学作业",
        "回复导师邮件",
    }
    assert fake_todo_service.created == []


def test_import_docx_extracts_paragraph_and_table_tasks() -> None:
    response = _service().import_files(
        files=[
            AgentImportFile(
                file_name="tasks.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content=_build_docx_bytes(),
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=FakeTodoService(),
    )

    titles = {task.task_title for task in response.extracted_tasks}
    assert "完成软件工程报告" in titles
    assert "回复导师邮件" in titles
    assert "完成软件工程报告" in response.raw_text_preview


def test_import_pdf_extracts_text_task() -> None:
    response = _service().import_files(
        files=[
            AgentImportFile(
                file_name="tasks.pdf",
                mime_type="application/pdf",
                content=_build_pdf_bytes(),
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=FakeTodoService(),
    )

    assert response.file_results[0].status == "success"
    assert response.extracted_tasks
    assert response.extracted_tasks[0].source_file == "tasks.pdf"


def test_import_corrupted_pdf_returns_file_failure() -> None:
    response = _service().import_files(
        files=[
            AgentImportFile(
                file_name="broken.pdf",
                mime_type="application/pdf",
                content=b"not a pdf",
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=FakeTodoService(),
    )

    assert response.file_results[0].status == "failed"
    assert response.file_results[0].error_code == "PDF_PARSE_FAILED"
    assert response.extracted_tasks == []


def test_import_corrupted_docx_returns_file_failure() -> None:
    response = _service().import_files(
        files=[
            AgentImportFile(
                file_name="broken.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                content=b"not a docx",
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=FakeTodoService(),
    )

    assert response.file_results[0].status == "failed"
    assert response.file_results[0].error_code == "DOCX_PARSE_FAILED"
    assert response.extracted_tasks == []


def test_import_image_uses_existing_vision_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLlmClient:
        def is_available(self) -> bool:
            return True

    monkeypatch.setattr(
        "lifetrace.services.agent_import_service.get_llm_client",
        lambda: FakeLlmClient(),
    )
    monkeypatch.setattr(
        "lifetrace.services.agent_import_service._call_vision_model_with_base64",
        lambda **_kwargs: [
            {
                "title": "提交截图报告",
                "source_text": "明天提交截图报告，紧急",
                "confidence": IMAGE_CONFIDENCE,
            }
        ],
    )

    response = _service().import_files(
        files=[
            AgentImportFile(
                file_name="capture.png",
                mime_type="image/png",
                content=b"\x89PNG\r\n\x1a\n",
            )
        ],
        reference_time=_reference_time(),
        create_todos=False,
        todo_service=FakeTodoService(),
    )

    assert response.file_results[0].status == "success"
    assert response.extracted_tasks[0].task_title == "提交截图报告"
    assert response.extracted_tasks[0].confidence == IMAGE_CONFIDENCE


def test_import_create_todos_creates_draft_items() -> None:
    fake_todo_service = FakeTodoService()

    response = _service().import_files(
        files=[_txt_file("明天完成课程展示材料，大概需要两个小时")],
        reference_time=_reference_time(),
        create_todos=True,
        todo_service=fake_todo_service,
    )

    assert response.created_todos[0].name == "完成课程展示材料"
    assert fake_todo_service.created[0].status == TodoStatus.DRAFT
    assert fake_todo_service.created[0].tags == ["文件导入", "AI解析"]


def test_import_create_todos_rolls_back_partial_success() -> None:
    fake_todo_service = FailingAfterFirstTodoService()

    with pytest.raises(ImportTodosError) as exc_info:
        _service().import_files(
            files=[_txt_file("- 明天完成课程展示材料\n- 后天回复导师邮件，紧急")],
            reference_time=_reference_time(),
            create_todos=True,
            todo_service=fake_todo_service,
        )

    assert exc_info.value.error_code == "TODO_CREATE_FAILED"
    assert fake_todo_service.deleted == [1]


@pytest.mark.parametrize(
    ("files", "error_code", "status_code"),
    [
        ([], "INVALID_INPUT", HTTP_BAD_REQUEST),
        (
            [
                AgentImportFile(
                    file_name=f"task-{index}.txt",
                    mime_type="text/plain",
                    content=b"todo",
                )
                for index in range(MAX_IMPORT_FILE_COUNT + 1)
            ],
            "TOO_MANY_FILES",
            HTTP_BAD_REQUEST,
        ),
        ([AgentImportFile("empty.txt", "text/plain", b"")], "EMPTY_FILE", HTTP_BAD_REQUEST),
        (
            [
                AgentImportFile(
                    "large.txt",
                    "text/plain",
                    b"x" * (MAX_IMPORT_FILE_BYTES + 1),
                )
            ],
            "FILE_TOO_LARGE",
            HTTP_CONTENT_TOO_LARGE,
        ),
        (
            [AgentImportFile("archive.zip", "application/zip", b"zip")],
            "INVALID_FILE_TYPE",
            HTTP_BAD_REQUEST,
        ),
    ],
)
def test_import_validation_errors(
    files: list[AgentImportFile],
    error_code: str,
    status_code: int,
) -> None:
    with pytest.raises(ImportTodosError) as exc_info:
        _service().import_files(
            files=files,
            reference_time=_reference_time(),
            create_todos=False,
            todo_service=FakeTodoService(),
        )

    assert exc_info.value.error_code == error_code
    assert exc_info.value.status_code == status_code
