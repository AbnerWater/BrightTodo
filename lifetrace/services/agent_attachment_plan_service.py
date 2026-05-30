"""BrightToDo 附件驱动 AI 日程规划服务"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

from lifetrace.routers.floating_capture import get_llm_client
from lifetrace.schemas.agent import (
    AttachmentPlanConfirmResponse,
    AttachmentPlanCreatedTodo,
    AttachmentPlanFileResult,
    AttachmentPlanResponse,
    AttachmentPlanTodo,
    ScheduleSuggestRequest,
    ScheduleSuggestTodo,
)
from lifetrace.schemas.todo import TodoCreate, TodoPriority, TodoStatus
from lifetrace.services.agent_import_service import (
    AgentImportFile,
    AgentImportService,
    FileParseError,
    ImportTodosError,
)
from lifetrace.services.schedule_suggest_service import ScheduleSuggestError, ScheduleSuggestService
from lifetrace.util.logging_config import get_logger
from lifetrace.util.path_utils import get_attachments_dir
from lifetrace.util.settings import settings
from lifetrace.util.time_utils import get_utc_now

if TYPE_CHECKING:
    from datetime import datetime

    from openai.types.chat import ChatCompletionMessageParam

    from lifetrace.services.todo_service import TodoService
else:
    ChatCompletionMessageParam = Any

logger = get_logger()

PLAN_STORAGE_DIR = "agent-plans"
MAX_LLM_DOCUMENT_CHARS = 10000
MAX_PLAN_TODO_COUNT = 12
DEFAULT_DAILY_AVAILABLE_HOURS = 6
DEFAULT_CONFIDENCE = 0.7
PLAN_TTL_SECONDS = 24 * 60 * 60
DEFAULT_VISION_MODEL = "qwen3-vl-plus"
DASHSCOPE_BASE_URL_MARKER = "dashscope.aliyuncs.com"
ISO_DURATION_RE = re.compile(
    r"^P(?:(?:\d+(?:\.\d+)?D)?"
    r"(?:T(?:\d+(?:\.\d+)?H)?(?:\d+(?:\.\d+)?M)?(?:\d+(?:\.\d+)?S)?)?)$"
)


@dataclass(frozen=True)
class _StoredPlanFile:
    """临时规划中的附件文件。"""

    index: int
    file_name: str
    mime_type: str | None
    size_bytes: int
    storage_path: str
    file_hash: str
    kind: str
    raw_text: str
    image_data_url: str | None


class AttachmentPlanError(Exception):
    """附件规划接口契约错误。"""

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


class AgentAttachmentPlanService:
    """将用户确认后的附件对话请求转换为待确认日程规划。"""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        import_service: AgentImportService | None = None,
        schedule_service: ScheduleSuggestService | None = None,
    ) -> None:
        self._llm_client = llm_client
        self.import_service = import_service or AgentImportService()
        self.schedule_service = schedule_service or ScheduleSuggestService()

    def create_plan(
        self,
        *,
        files: list[AgentImportFile],
        prompt: str,
        reference_time: datetime | None,
        planning_start: datetime | None,
        planning_end: datetime | None,
        daily_available_hours: int | None,
    ) -> AttachmentPlanResponse:
        """基于附件和用户确认的 prompt 生成待确认日程规划。"""
        start = time.perf_counter()
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise AttachmentPlanError(400, "INVALID_INPUT", "Prompt 不能为空")

        self._validate_files(files)
        self.cleanup_expired_plans()
        llm_client = self._get_llm_client()
        if not llm_client.is_available():
            raise AttachmentPlanError(503, "LLM_UNAVAILABLE", "LLM 服务当前不可用，请检查配置")

        plan_id = uuid4().hex
        plan_dir = self._plan_dir(plan_id)
        plan_dir.mkdir(parents=True, exist_ok=False)

        try:
            stored_files, file_results = self._store_and_prepare_files(plan_dir, files)
            usable_files = [file for file in stored_files if file.kind == "image" or file.raw_text.strip()]
            if not usable_files:
                raise AttachmentPlanError(
                    422,
                    "NO_USABLE_FILE_CONTENT",
                    "附件中没有可供 LLM 分析的文本或图片内容",
                )

            try:
                response_text = self._call_llm_for_plan(
                    llm_client=llm_client,
                    prompt=clean_prompt,
                    files=usable_files,
                    reference_time=reference_time,
                )
            except Exception as exc:
                logger.warning(f"附件 AI 日程规划请求失败: {exc}")
                raise AttachmentPlanError(
                    502,
                    "LLM_REQUEST_FAILED",
                    self._build_llm_failure_message(exc),
                    str(exc),
                ) from exc
            proposed_todos, summary = self._parse_plan_response(response_text, stored_files)
            proposed_todos, schedule_summary = self._apply_schedule_suggestions(
                proposed_todos=proposed_todos,
                planning_start=planning_start,
                planning_end=planning_end,
                daily_available_hours=daily_available_hours,
            )
            if summary and schedule_summary:
                schedule_summary = f"{summary}\n{schedule_summary}"
            elif summary:
                schedule_summary = summary

            self._write_manifest(
                plan_dir=plan_dir,
                prompt=clean_prompt,
                files=stored_files,
                proposed_todos=proposed_todos,
                schedule_summary=schedule_summary,
            )

            return AttachmentPlanResponse(
                plan_id=plan_id,
                file_results=file_results,
                proposed_todos=proposed_todos,
                schedule_summary=schedule_summary,
                processing_time_ms=round((time.perf_counter() - start) * 1000),
            )
        except Exception:
            shutil.rmtree(plan_dir, ignore_errors=True)
            raise

    def confirm_plan(
        self,
        *,
        plan_id: str,
        proposed_todos: list[AttachmentPlanTodo],
        todo_service: TodoService,
    ) -> AttachmentPlanConfirmResponse:
        """确认规划，创建草稿待办并把来源附件绑定到待办。"""
        start = time.perf_counter()
        if not proposed_todos:
            raise AttachmentPlanError(400, "INVALID_INPUT", "请至少确认 1 个待办")

        manifest = self._load_manifest(plan_id)
        stored_files = self._manifest_files(manifest)
        prompt = str(manifest.get("prompt") or "")

        created: list[AttachmentPlanCreatedTodo] = []
        created_todo_ids: list[int] = []
        copied_paths: list[Path] = []
        try:
            for todo in proposed_todos:
                if not todo.title.strip():
                    continue
                has_fixed_end = todo.suggested_end is not None
                created_todo = todo_service.create_todo(
                    TodoCreate(
                        name=todo.title.strip(),
                        description=todo.description,
                        user_notes=self._build_user_notes(todo, prompt),
                        due=todo.due,
                        duration=None if has_fixed_end else todo.duration,
                        start_time=todo.suggested_start,
                        end_time=todo.suggested_end,
                        status=TodoStatus.DRAFT,
                        priority=todo.priority,
                        tags=["附件规划", "AI解析"],
                    )
                )
                created_todo_ids.append(created_todo.id)
                attachment_ids = self._copy_and_bind_attachments(
                    todo=todo,
                    created_todo_id=created_todo.id,
                    stored_files=stored_files,
                    todo_service=todo_service,
                    copied_paths=copied_paths,
                )
                created.append(
                    AttachmentPlanCreatedTodo(
                        id=created_todo.id,
                        name=created_todo.name,
                        status=created_todo.status,
                        attachment_ids=attachment_ids,
                    )
                )
        except Exception as exc:
            for todo_id in reversed(created_todo_ids):
                try:
                    todo_service.delete_todo(todo_id)
                except Exception:
                    continue
            for path in copied_paths:
                path.unlink(missing_ok=True)
            raise AttachmentPlanError(
                500,
                "TODO_CREATE_FAILED",
                "创建待办或绑定附件失败，已回滚本次已创建项",
                str(exc),
            ) from exc

        if not created:
            raise AttachmentPlanError(400, "INVALID_INPUT", "请至少保留 1 个有标题的待办")

        self.delete_plan(plan_id)
        return AttachmentPlanConfirmResponse(
            created_todos=created,
            processing_time_ms=round((time.perf_counter() - start) * 1000),
        )

    def delete_plan(self, plan_id: str) -> None:
        """删除未确认的临时规划附件。"""
        plan_dir = self._plan_dir(plan_id)
        if plan_dir.exists():
            shutil.rmtree(plan_dir)

    def cleanup_expired_plans(self, *, now: datetime | None = None) -> None:
        """清理超过 TTL 的未确认规划，避免附件长期滞留。"""
        root = self._plans_root()
        if not root.exists():
            return
        current = now or get_utc_now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        current_ts = current.timestamp()
        for plan_dir in root.iterdir():
            if not plan_dir.is_dir():
                continue
            try:
                age_seconds = current_ts - plan_dir.stat().st_mtime
                if age_seconds > PLAN_TTL_SECONDS:
                    shutil.rmtree(plan_dir)
            except OSError as exc:
                logger.warning(f"清理过期附件规划失败 {plan_dir}: {exc}")

    def _validate_files(self, files: list[AgentImportFile]) -> None:
        try:
            self.import_service._validate_files(files)
        except ImportTodosError as exc:
            raise AttachmentPlanError(
                exc.status_code,
                exc.error_code,
                exc.message,
                exc.detail,
            ) from exc

    def _store_and_prepare_files(
        self, plan_dir: Path, files: list[AgentImportFile]
    ) -> tuple[list[_StoredPlanFile], list[AttachmentPlanFileResult]]:
        stored_files: list[_StoredPlanFile] = []
        file_results: list[AttachmentPlanFileResult] = []
        for index, file in enumerate(files):
            kind = self.import_service._detect_file_kind(file)
            if kind is None:
                raise AttachmentPlanError(
                    400,
                    "INVALID_FILE_TYPE",
                    "仅支持 PNG/JPEG/WebP、TXT/MD/CSV/JSON、PDF、DOCX 文件",
                    file.file_name,
                )

            target_path = plan_dir / self._storage_name(index, file.file_name)
            target_path.write_bytes(file.content)
            raw_text = ""
            image_data_url: str | None = None
            status: Literal["ready", "failed"] = "ready"
            error_code = None
            message = "已加入下一次 AI 规划"

            if kind == "image":
                image_data_url = self.import_service._to_image_data_url(file)
            else:
                try:
                    raw_text = self.import_service._extract_text(file, kind)
                    if not raw_text.strip():
                        status = "failed"
                        error_code = "NO_TEXT_EXTRACTED"
                        message = "未能从文件中提取可分析文本"
                except FileParseError as exc:
                    status = "failed"
                    error_code = exc.error_code
                    message = exc.message

            stored_files.append(
                _StoredPlanFile(
                    index=index,
                    file_name=file.file_name,
                    mime_type=file.mime_type,
                    size_bytes=len(file.content),
                    storage_path=str(target_path),
                    file_hash=hashlib.sha256(file.content).hexdigest(),
                    kind=str(kind),
                    raw_text=raw_text,
                    image_data_url=image_data_url,
                )
            )
            file_results.append(
                AttachmentPlanFileResult(
                    file_name=file.file_name,
                    mime_type=file.mime_type,
                    size_bytes=len(file.content),
                    status=status,
                    error_code=error_code,
                    message=message,
                    raw_text_preview=self.import_service._limit_preview(raw_text),
                )
            )
        return stored_files, file_results

    def _call_llm_for_plan(
        self,
        *,
        llm_client: Any,
        prompt: str,
        files: list[_StoredPlanFile],
        reference_time: datetime | None,
    ) -> str:
        has_images = any(file.image_data_url for file in files)
        system_prompt, text_prompt = self._build_plan_prompts(prompt, files, reference_time)
        if has_images and hasattr(llm_client, "_get_client"):
            content: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
            for file in files:
                if file.image_data_url:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": file.image_data_url},
                        }
                    )
            messages = cast(
                "list[ChatCompletionMessageParam]",
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
            )
            client = llm_client._get_client()
            response = client.chat.completions.create(
                model=self._resolve_attachment_vision_model(llm_client),
                messages=messages,
                temperature=0.2,
                max_tokens=2600,
                timeout=90,
                extra_body={"enable_thinking": False},
            )
            return response.choices[0].message.content or ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_prompt},
        ]
        if hasattr(llm_client, "chat"):
            return llm_client.chat(messages=messages, temperature=0.2, max_tokens=2600)

        client = llm_client._get_client()
        response = client.chat.completions.create(
            model=llm_client.model,
            messages=cast("list[ChatCompletionMessageParam]", messages),
            temperature=0.2,
            max_tokens=2600,
            timeout=90,
            extra_body={"enable_thinking": False},
        )
        return response.choices[0].message.content or ""

    def _resolve_attachment_vision_model(self, llm_client: Any) -> str:
        """选择附件规划图片请求使用的模型。"""
        primary_model = str(getattr(llm_client, "model", "") or settings.llm.model or "").strip()
        vision_model = str(settings.llm.vision_model or "").strip()
        base_url = str(settings.llm.base_url or "").lower()

        if not vision_model:
            return primary_model

        if (
            vision_model == DEFAULT_VISION_MODEL
            and primary_model
            and DASHSCOPE_BASE_URL_MARKER not in base_url
        ):
            logger.info(
                "附件规划检测到默认视觉模型与当前 LLM 服务不匹配，改用主模型: "
                f"{primary_model}"
            )
            return primary_model

        return vision_model

    def _build_llm_failure_message(self, exc: Exception) -> str:
        """把常见 LLM 供应商错误转换为用户可操作的提示。"""
        detail = str(exc)
        lower_detail = detail.lower()

        if "invalid_api_key" in lower_detail or "incorrect api key" in lower_detail:
            return "AI API Key 无效，请检查 AI 服务配置"
        if "settlement_unknown_model" in lower_detail or "settlement blocked" in lower_detail:
            return "当前 AI 服务不支持所选模型，请检查主模型/视觉模型配置"
        if "service temporarily unavailable" in lower_detail or "算力池" in detail:
            return "AI 服务暂时不可用，请稍后重试或切换可用模型"

        return "LLM 附件规划请求失败，请检查 AI 服务配置"

    def _build_plan_prompts(
        self,
        prompt: str,
        files: list[_StoredPlanFile],
        reference_time: datetime | None,
    ) -> tuple[str, str]:
        reference = reference_time or get_utc_now()
        system_prompt = (
            "你是 BrightToDo 的附件日程规划 Agent。"
            "用户提供的文件或图片不一定包含显式 TODO，你必须理解资料内容，"
            "推断用户接下来需要执行、准备、提交、复习、跟进或安排的具体事项。"
            "每个事项必须可执行，并给出初始执行时长估计。"
            "只输出 JSON，不要输出 Markdown。"
        )
        file_blocks: list[str] = []
        for file in files:
            if file.kind == "image":
                file_blocks.append(
                    f"[文件 {file.index}] {file.file_name} 是图片附件，请结合图片内容理解任务。"
                )
                continue
            file_blocks.append(
                f"[文件 {file.index}] {file.file_name}\n"
                f"{self._limit_document_text(file.raw_text)}"
            )
        text_prompt = (
            f"当前时间：{reference.isoformat()}\n"
            f"用户确认的 Prompt：{prompt}\n\n"
            "请基于全部附件生成最多 12 个待确认日程项。"
            "如果能推断截止时间，due 使用 ISO 8601；否则为 null。"
            "duration 必须使用 ISO 8601 Duration，例如 PT30M、PT1H、PT2H30M。"
            "priority 只能是 high、medium、low、none。"
            "source_file_indices 必须填写支撑该任务的附件序号数组。"
            "source_text 填写最能支撑该任务的文字片段；图片则填写你观察到的关键内容。\n\n"
            "返回格式：\n"
            '{"summary":"整体规划说明","todos":[{"title":"任务标题","description":"说明",'
            '"priority":"medium","due":null,"duration":"PT1H",'
            '"source_file_indices":[0],"source_text":"来源依据","confidence":0.8}]}\n\n'
            "附件内容：\n"
            + "\n\n".join(file_blocks)
        )
        return system_prompt, text_prompt

    def _parse_plan_response(
        self, response_text: str, stored_files: list[_StoredPlanFile]
    ) -> tuple[list[AttachmentPlanTodo], str]:
        try:
            data = self.import_service._load_json_from_llm_response(response_text)
        except json.JSONDecodeError as exc:
            raise AttachmentPlanError(
                502,
                "LLM_RESPONSE_INVALID",
                "LLM 返回内容不是有效 JSON",
                str(exc),
            ) from exc

        if isinstance(data, list):
            raw_todos = data
            summary = ""
        elif isinstance(data, dict):
            raw_todos = data.get("todos") or data.get("tasks") or data.get("proposed_todos") or []
            summary = str(data.get("summary") or data.get("schedule_summary") or "")
        else:
            raw_todos = []
            summary = ""

        file_names = {file.index: file.file_name for file in stored_files}
        proposed: list[AttachmentPlanTodo] = []
        for raw in raw_todos[:MAX_PLAN_TODO_COUNT]:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("name") or "").strip()
            if not title:
                continue
            source_indices = self._normalize_source_indices(
                raw.get("source_file_indices") or raw.get("source_files"),
                file_names,
            )
            duration = self._normalize_duration(raw.get("duration")) or self.import_service._estimate_initial_duration(title)
            proposed.append(
                AttachmentPlanTodo(
                    plan_item_id=uuid4().hex,
                    title=title[:200],
                    description=str(raw.get("description") or "").strip() or None,
                    priority=self.import_service._normalize_priority(
                        raw.get("priority"),
                        TodoPriority.NONE,
                    ),
                    due=self.import_service._parse_llm_due(raw.get("due")),
                    duration=duration,
                    source_file_indices=source_indices,
                    source_files=[file_names[index] for index in source_indices if index in file_names],
                    source_text=str(raw.get("source_text") or "").strip()[:240] or None,
                    confidence=self.import_service._normalize_confidence(
                        raw.get("confidence"),
                        DEFAULT_CONFIDENCE,
                    ),
                )
            )
        return proposed, summary

    def _apply_schedule_suggestions(
        self,
        *,
        proposed_todos: list[AttachmentPlanTodo],
        planning_start: datetime | None,
        planning_end: datetime | None,
        daily_available_hours: int | None,
    ) -> tuple[list[AttachmentPlanTodo], str]:
        if not proposed_todos:
            return [], "LLM 未返回可确认的日程项。"

        request = ScheduleSuggestRequest(
            todos=[
                ScheduleSuggestTodo(
                    id=index + 1,
                    name=todo.title,
                    priority=todo.priority,
                    due=todo.due,
                    duration=todo.duration,
                )
                for index, todo in enumerate(proposed_todos)
            ],
            planning_start=planning_start,
            planning_end=planning_end,
            daily_available_hours=daily_available_hours or DEFAULT_DAILY_AVAILABLE_HOURS,
        )
        try:
            response = self.schedule_service.suggest(request)
        except ScheduleSuggestError as exc:
            return proposed_todos, f"已生成待办，但暂未生成可用执行时段：{exc.message}"

        suggestions = {item.todo_id: item for item in response.suggestions}
        updated: list[AttachmentPlanTodo] = []
        for index, todo in enumerate(proposed_todos, start=1):
            suggestion = suggestions.get(index)
            if suggestion is None:
                updated.append(todo)
                continue
            updated.append(
                todo.model_copy(
                    update={
                        "suggested_start": suggestion.suggested_start,
                        "suggested_end": suggestion.suggested_end,
                        "schedule_reason": suggestion.reason,
                    }
                )
            )
        summary = (
            f"已为 {len(response.suggestions)} 个待办生成建议时段，"
            f"覆盖率 {response.planning_coverage_pct}%"
        )
        if response.unscheduled_todos:
            summary += f"，{len(response.unscheduled_todos)} 个待办暂未安排。"
        return updated, summary

    def _copy_and_bind_attachments(
        self,
        *,
        todo: AttachmentPlanTodo,
        created_todo_id: int,
        stored_files: dict[int, _StoredPlanFile],
        todo_service: TodoService,
        copied_paths: list[Path],
    ) -> list[int]:
        attachment_ids: list[int] = []
        for source_index in todo.source_file_indices:
            stored = stored_files.get(source_index)
            if stored is None:
                continue
            source_path = Path(stored.storage_path)
            attachments_dir = get_attachments_dir()
            attachments_dir.mkdir(parents=True, exist_ok=True)
            target_path = attachments_dir / self._storage_name(source_index, stored.file_name)
            shutil.copy2(source_path, target_path)
            copied_paths.append(target_path)
            attachment = todo_service.add_attachment(
                todo_id=created_todo_id,
                file_name=stored.file_name,
                file_path=str(target_path),
                file_size=stored.size_bytes,
                mime_type=stored.mime_type,
                file_hash=stored.file_hash,
                source="ai",
            )
            attachment_ids.append(attachment.id)
        return attachment_ids

    def _write_manifest(
        self,
        *,
        plan_dir: Path,
        prompt: str,
        files: list[_StoredPlanFile],
        proposed_todos: list[AttachmentPlanTodo],
        schedule_summary: str,
    ) -> None:
        payload = {
            "prompt": prompt,
            "files": [file.__dict__ for file in files],
            "proposed_todos": [todo.model_dump(mode="json") for todo in proposed_todos],
            "schedule_summary": schedule_summary,
        }
        (plan_dir / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load_manifest(self, plan_id: str) -> dict[str, Any]:
        manifest_path = self._plan_dir(plan_id) / "manifest.json"
        if not manifest_path.exists():
            raise AttachmentPlanError(404, "PLAN_NOT_FOUND", "附件规划已失效或不存在")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def _manifest_files(self, manifest: dict[str, Any]) -> dict[int, _StoredPlanFile]:
        result: dict[int, _StoredPlanFile] = {}
        for raw in manifest.get("files") or []:
            if not isinstance(raw, dict):
                continue
            file = _StoredPlanFile(
                index=int(raw["index"]),
                file_name=str(raw["file_name"]),
                mime_type=raw.get("mime_type"),
                size_bytes=int(raw["size_bytes"]),
                storage_path=str(raw["storage_path"]),
                file_hash=str(raw["file_hash"]),
                kind=str(raw["kind"]),
                raw_text=str(raw.get("raw_text") or ""),
                image_data_url=raw.get("image_data_url"),
            )
            result[file.index] = file
        return result

    def _get_llm_client(self) -> Any:
        return self._llm_client or get_llm_client()

    def _plan_dir(self, plan_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
            raise AttachmentPlanError(400, "INVALID_INPUT", "plan_id 格式错误")
        return self._plans_root() / plan_id

    def _plans_root(self) -> Path:
        return get_attachments_dir() / PLAN_STORAGE_DIR

    def _storage_name(self, index: int, file_name: str) -> str:
        safe_name = Path(file_name).name or "attachment"
        suffix = Path(safe_name).suffix
        stem = Path(safe_name).stem[:40] or "attachment"
        return f"{index}-{uuid4().hex}-{stem}{suffix}"

    def _normalize_source_indices(self, value: Any, file_names: dict[int, str]) -> list[int]:
        raw_values = value if isinstance(value, list) else [value]
        indices: list[int] = []
        name_to_index = {name: index for index, name in file_names.items()}
        for raw in raw_values:
            if raw is None:
                continue
            if isinstance(raw, int) and raw in file_names:
                indices.append(raw)
                continue
            text = str(raw)
            if text.isdigit() and int(text) in file_names:
                indices.append(int(text))
                continue
            if text in name_to_index:
                indices.append(name_to_index[text])
        if not indices and file_names:
            indices = [min(file_names)]
        return sorted(set(indices))

    def _normalize_duration(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        raw = str(value).strip().upper()
        if ISO_DURATION_RE.match(raw) and raw not in {"P", "PT"}:
            return raw
        return self.import_service._normalize_llm_duration(value)

    def _limit_document_text(self, text: str) -> str:
        normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
        if len(normalized) <= MAX_LLM_DOCUMENT_CHARS:
            return normalized
        return f"{normalized[:MAX_LLM_DOCUMENT_CHARS]}\n\n[后续文本已截断]"

    def _build_user_notes(self, todo: AttachmentPlanTodo, prompt: str) -> str:
        parts = [
            "来源：附件 AI 规划",
            f"原始 Prompt：{prompt}",
        ]
        if todo.source_files:
            parts.append(f"来源文件：{', '.join(todo.source_files)}")
        if todo.source_text:
            parts.append(f"来源依据：{todo.source_text}")
        if todo.schedule_reason:
            parts.append(f"编排理由：{todo.schedule_reason}")
        parts.append(f"置信度：{round(todo.confidence * 100)}%")
        return "\n".join(parts)
