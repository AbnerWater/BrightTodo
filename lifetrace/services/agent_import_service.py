"""BrightToDo 文件导入待办解析服务"""

from __future__ import annotations

import base64
import io
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lifetrace.routers.floating_capture import _call_vision_model_with_base64, get_llm_client
from lifetrace.schemas.agent import (
    ImportedCreatedTodo,
    ImportedTodoTask,
    ImportTodoFileResult,
    ImportTodosResponse,
)
from lifetrace.schemas.todo import TodoCreate, TodoStatus
from lifetrace.services.agent_parse_service import AgentParseService

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from datetime import datetime

    from lifetrace.services.todo_service import TodoService

MAX_IMPORT_FILE_COUNT = 5
MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024
MAX_CANDIDATE_COUNT = 40
MAX_PREVIEW_CHARS = 1200
MAX_SOURCE_TEXT_CHARS = 240
MIN_TASK_TEXT_CHARS = 2

FileKind = Literal["image", "text", "pdf", "docx"]

IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json"}
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {"application/json", "application/x-ndjson"}
PDF_MIME_TYPES = {"application/pdf"}
DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

TASK_HINT_RE = re.compile(
    r"(待办|任务|TODO|todo|完成|提交|复习|整理|准备|写|看|做|买|回复|截止|ddl|DDL|明天|后天|下周|今天|今晚|紧急)"
)
LIST_MARK_RE = re.compile(
    r"^\s*(?:[-*+•]|[0-9]+[.)、]|[（(]?[一二三四五六七八九十]+[）).、])\s*"
)


@dataclass(frozen=True)
class AgentImportFile:
    """导入服务内部文件对象"""

    file_name: str
    mime_type: str | None
    content: bytes


@dataclass(frozen=True)
class _ProcessedFile:
    result: ImportTodoFileResult
    tasks: list[ImportedTodoTask]
    raw_text: str


class ImportTodosError(Exception):
    """导入接口契约错误"""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail


class FileParseError(Exception):
    """单个文件解析失败，不中断其他文件处理。"""

    def __init__(self, error_code: str, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.detail = detail


class AgentImportService:
    """将上传文件解析为待确认任务。"""

    def __init__(self, parse_service: AgentParseService | None = None) -> None:
        self.parse_service = parse_service or AgentParseService()

    def import_files(
        self,
        *,
        files: Sequence[AgentImportFile],
        reference_time: datetime | None,
        create_todos: bool,
        todo_service: TodoService,
    ) -> ImportTodosResponse:
        """解析上传文件，并按需创建草稿待办。"""
        start = time.perf_counter()
        self._validate_files(files)

        processed_files = [
            self._process_file(
                file=file,
                source_file_index=index,
                reference_time=reference_time,
                todo_service=todo_service,
            )
            for index, file in enumerate(files)
        ]
        tasks = self._dedupe_tasks(
            task for processed in processed_files for task in processed.tasks
        )
        created_todos = self._create_todos(tasks, todo_service) if create_todos else []
        preview = self._build_preview(processed.raw_text for processed in processed_files)

        return ImportTodosResponse(
            file_results=[processed.result for processed in processed_files],
            extracted_tasks=tasks,
            created_todos=created_todos,
            raw_text_preview=preview,
            processing_time_ms=round((time.perf_counter() - start) * 1000),
        )

    def _validate_files(self, files: Sequence[AgentImportFile]) -> None:
        if not files:
            raise ImportTodosError(400, "INVALID_INPUT", "请至少上传 1 个文件")
        if len(files) > MAX_IMPORT_FILE_COUNT:
            raise ImportTodosError(400, "TOO_MANY_FILES", "最多一次上传 5 个文件")

        for file in files:
            if not file.file_name:
                raise ImportTodosError(400, "INVALID_INPUT", "文件名不能为空")
            if not file.content:
                raise ImportTodosError(400, "EMPTY_FILE", f"{file.file_name} 是空文件")
            if len(file.content) > MAX_IMPORT_FILE_BYTES:
                raise ImportTodosError(
                    413,
                    "FILE_TOO_LARGE",
                    f"{file.file_name} 超过 10MB 限制",
                )
            if self._detect_file_kind(file) is None:
                raise ImportTodosError(
                    400,
                    "INVALID_FILE_TYPE",
                    "仅支持 PNG/JPEG/WebP、TXT/MD/CSV/JSON、PDF、DOCX 文件",
                    file.file_name,
                )

    def _process_file(
        self,
        *,
        file: AgentImportFile,
        source_file_index: int,
        reference_time: datetime | None,
        todo_service: TodoService,
    ) -> _ProcessedFile:
        kind = self._detect_file_kind(file)
        if kind == "image":
            return self._process_image_file(
                file,
                source_file_index,
                reference_time,
                todo_service,
            )

        try:
            raw_text = self._extract_text(file, kind)
        except FileParseError as exc:
            return _ProcessedFile(
                result=ImportTodoFileResult(
                    file_name=file.file_name,
                    mime_type=file.mime_type,
                    size_bytes=len(file.content),
                    status="failed",
                    extracted_count=0,
                    error_code=exc.error_code,
                    message=exc.message,
                    raw_text_preview="",
                ),
                tasks=[],
                raw_text="",
            )
        tasks = self._extract_tasks_from_text(
            raw_text,
            source_file=file.file_name,
            source_file_index=source_file_index,
            reference_time=reference_time,
        )
        status: Literal["success", "failed"] = "success" if raw_text.strip() else "failed"
        result = ImportTodoFileResult(
            file_name=file.file_name,
            mime_type=file.mime_type,
            size_bytes=len(file.content),
            status=status,
            extracted_count=len(tasks),
            error_code=None if status == "success" else "NO_TEXT_EXTRACTED",
            message=f"提取到 {len(tasks)} 个待确认任务" if tasks else "未识别到待办任务",
            raw_text_preview=self._limit_preview(raw_text),
        )
        return _ProcessedFile(result=result, tasks=tasks, raw_text=raw_text)

    def _process_image_file(
        self,
        file: AgentImportFile,
        source_file_index: int,
        reference_time: datetime | None,
        todo_service: TodoService,
    ) -> _ProcessedFile:
        llm_client = get_llm_client()
        if not llm_client.is_available():
            return _ProcessedFile(
                result=ImportTodoFileResult(
                    file_name=file.file_name,
                    mime_type=file.mime_type,
                    size_bytes=len(file.content),
                    status="failed",
                    extracted_count=0,
                    error_code="LLM_UNAVAILABLE",
                    message="图片解析需要先配置可用的视觉模型",
                ),
                tasks=[],
                raw_text="",
            )

        image_base64 = self._to_image_data_url(file)
        vision_todos = _call_vision_model_with_base64(
            llm_client=llm_client,
            image_base64=image_base64,
            existing_todos=self._list_existing_todos(todo_service),
        )
        tasks = self._convert_image_tasks(
            vision_todos,
            file.file_name,
            source_file_index,
            reference_time,
        )
        return _ProcessedFile(
            result=ImportTodoFileResult(
                file_name=file.file_name,
                mime_type=file.mime_type,
                size_bytes=len(file.content),
                status="success",
                extracted_count=len(tasks),
                message=f"提取到 {len(tasks)} 个待确认任务" if tasks else "图片中未识别到待办任务",
            ),
            tasks=tasks,
            raw_text="\n".join(task.source_text for task in tasks),
        )

    def _extract_text(self, file: AgentImportFile, kind: FileKind | None) -> str:
        if kind == "pdf":
            return self._extract_pdf_text(file.content)
        if kind == "docx":
            return self._extract_docx_text(file.content)
        return self._decode_text(file.content)

    def _extract_pdf_text(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader  # noqa: PLC0415
        except ImportError as exc:
            raise ImportTodosError(500, "PDF_SUPPORT_MISSING", "PDF 解析依赖未安装") from exc

        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            raise FileParseError(
                "PDF_PARSE_FAILED",
                "PDF 文件解析失败，请确认文件未损坏",
                str(exc),
            ) from exc
        return "\n".join(page for page in pages if page.strip())

    def _extract_docx_text(self, content: bytes) -> str:
        try:
            from docx import Document  # noqa: PLC0415
        except ImportError as exc:
            raise ImportTodosError(500, "DOCX_SUPPORT_MISSING", "DOCX 解析依赖未安装") from exc

        try:
            document = Document(io.BytesIO(content))
        except Exception as exc:
            raise FileParseError(
                "DOCX_PARSE_FAILED",
                "DOCX 文件解析失败，请确认文件未损坏",
                str(exc),
            ) from exc
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    def _decode_text(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _extract_tasks_from_text(
        self,
        text: str,
        *,
        source_file: str,
        source_file_index: int,
        reference_time: datetime | None,
    ) -> list[ImportedTodoTask]:
        candidates = self._candidate_lines(text)
        tasks: list[ImportedTodoTask] = []
        for candidate in candidates:
            parsed = self.parse_service.parse_task(
                text=candidate,
                reference_time=reference_time,
            )
            tasks.append(
                ImportedTodoTask(
                    task_title=parsed.task_title,
                    priority=parsed.priority,
                    due=parsed.due,
                    duration=parsed.duration,
                    description=parsed.description,
                    source_file=source_file,
                    source_file_index=source_file_index,
                    source_text=candidate[:MAX_SOURCE_TEXT_CHARS],
                    confidence=parsed.confidence,
                )
            )
        return tasks

    def _candidate_lines(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        raw_segments: list[str] = []
        for line in normalized.split("\n"):
            cleaned = LIST_MARK_RE.sub("", line).strip()
            if not cleaned:
                continue
            raw_segments.extend(self._split_long_line(cleaned))

        candidates = [segment for segment in raw_segments if self._looks_like_task(segment)]
        if not candidates:
            candidates = raw_segments[:5]
        return candidates[:MAX_CANDIDATE_COUNT]

    def _split_long_line(self, line: str) -> list[str]:
        if len(line) <= MAX_SOURCE_TEXT_CHARS:
            return [line]
        return [segment.strip() for segment in re.split(r"[。；;]", line) if segment.strip()]

    def _looks_like_task(self, line: str) -> bool:
        return (
            MIN_TASK_TEXT_CHARS <= len(line) <= MAX_SOURCE_TEXT_CHARS
            and TASK_HINT_RE.search(line) is not None
        )

    def _convert_image_tasks(
        self,
        todos: list[dict[str, object]],
        source_file: str,
        source_file_index: int,
        reference_time: datetime | None,
    ) -> list[ImportedTodoTask]:
        tasks: list[ImportedTodoTask] = []
        for todo in todos:
            title = str(todo.get("title") or "").strip()
            source_text = str(todo.get("source_text") or title).strip()
            if not title and not source_text:
                continue
            parsed = self.parse_service.parse_task(
                text=source_text or title,
                reference_time=reference_time,
            )
            tasks.append(
                ImportedTodoTask(
                    task_title=title or parsed.task_title,
                    priority=parsed.priority,
                    due=parsed.due,
                    duration=parsed.duration,
                    description=str(todo.get("description") or parsed.description or ""),
                    source_file=source_file,
                    source_file_index=source_file_index,
                    source_text=(source_text or title)[:MAX_SOURCE_TEXT_CHARS],
                    confidence=float(todo.get("confidence") or parsed.confidence),
                )
            )
        return tasks

    def _create_todos(
        self,
        tasks: Sequence[ImportedTodoTask],
        todo_service: TodoService,
    ) -> list[ImportedCreatedTodo]:
        created: list[ImportedCreatedTodo] = []
        try:
            for task in tasks:
                todo = todo_service.create_todo(
                    TodoCreate(
                        name=task.task_title,
                        description=task.description,
                        user_notes=self._build_user_notes(task),
                        due=task.due,
                        duration=task.duration,
                        status=TodoStatus.DRAFT,
                        priority=task.priority,
                        tags=["文件导入", "AI解析"],
                    )
                )
                created.append(
                    ImportedCreatedTodo(id=todo.id, name=todo.name, status=todo.status)
                )
        except Exception as exc:
            self._rollback_created_todos(todo_service, created)
            raise ImportTodosError(
                500,
                "TODO_CREATE_FAILED",
                "创建待办失败，已回滚本次已创建项",
                str(exc),
            ) from exc
        return created

    def _rollback_created_todos(
        self,
        todo_service: TodoService,
        created: Sequence[ImportedCreatedTodo],
    ) -> None:
        for todo in reversed(created):
            try:
                todo_service.delete_todo(todo.id)
            except Exception:
                continue

    def _build_user_notes(self, task: ImportedTodoTask) -> str:
        return (
            "来源：文件导入\n"
            f"来源文件：{task.source_file}\n"
            f"来源文本：{task.source_text}\n"
            f"置信度：{round(task.confidence * 100)}%"
        )

    def _dedupe_tasks(self, tasks: Iterable[ImportedTodoTask]) -> list[ImportedTodoTask]:
        result: list[ImportedTodoTask] = []
        seen: set[tuple[str, str | None]] = set()
        for task in tasks:
            key = (re.sub(r"\s+", "", task.task_title).lower(), task.due.isoformat() if task.due else None)
            if key in seen:
                continue
            seen.add(key)
            result.append(task)
        return result

    def _build_preview(self, text_parts: Iterable[str]) -> str:
        combined = "\n\n".join(part.strip() for part in text_parts if part.strip())
        return self._limit_preview(combined)

    def _limit_preview(self, text: str) -> str:
        text = text.strip()
        if len(text) <= MAX_PREVIEW_CHARS:
            return text
        return f"{text[:MAX_PREVIEW_CHARS]}..."

    def _detect_file_kind(self, file: AgentImportFile) -> FileKind | None:
        suffix = Path(file.file_name).suffix.lower()
        mime_type = (file.mime_type or "").lower()
        if suffix in IMAGE_EXTENSIONS or mime_type in IMAGE_MIME_TYPES:
            return "image"
        if suffix in TEXT_EXTENSIONS or mime_type.startswith(TEXT_MIME_PREFIXES) or mime_type in TEXT_MIME_TYPES:
            return "text"
        if suffix == ".pdf" or mime_type in PDF_MIME_TYPES:
            return "pdf"
        if suffix == ".docx" or mime_type in DOCX_MIME_TYPES:
            return "docx"
        return None

    def _to_image_data_url(self, file: AgentImportFile) -> str:
        mime_type = file.mime_type or self._mime_from_extension(file.file_name)
        encoded = base64.b64encode(file.content).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    def _mime_from_extension(self, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".webp":
            return "image/webp"
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        return "image/png"

    def _list_existing_todos(self, todo_service: TodoService) -> list[dict[str, object]]:
        payload = todo_service.list_todos(limit=1000, offset=0, status=None)
        todos = payload.get("todos", [])
        return [
            {"id": todo.id, "name": todo.name, "description": todo.description}
            for todo in todos
        ]
