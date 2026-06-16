"""待办 AI 时间冲突检查与执行时间推荐服务"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from lifetrace.llm.llm_client import LLMClient
from lifetrace.schemas.todo import (
    TodoTimeOptimizationConflict,
    TodoTimeOptimizationRange,
    TodoTimeOptimizationResponse,
)
from lifetrace.util.logging_config import get_logger
from lifetrace.util.time_utils import get_utc_now, naive_as_utc, to_utc

if TYPE_CHECKING:
    from collections.abc import Callable

    from lifetrace.schemas.todo import TodoResponse
    from lifetrace.services.todo_service import TodoService

logger = get_logger()

DEFAULT_DURATION_MINUTES = 60
MAX_ACTIVE_TODOS_FOR_PROMPT = 200
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 1200
JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
ISO_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TimeRange:
    """本地冲突检测使用的闭开时间段"""

    start: datetime
    end: datetime


class TodoTimeOptimizationError(Exception):
    """待办时间优化领域错误"""

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


class TodoTimeOptimizationService:
    """生成单个待办的 AI 时间优化预览。"""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        now_provider: Callable[[], datetime] = get_utc_now,
    ) -> None:
        self._llm_client = llm_client
        self._now_provider = now_provider

    def optimize(self, todo_id: int, todo_service: TodoService) -> TodoTimeOptimizationResponse:
        target = todo_service.get_todo(todo_id)
        if target.status != "active":
            raise TodoTimeOptimizationError(400, "INVALID_TODO_STATUS", "仅支持优化活动待办")

        active_todos = self._load_active_todos(todo_service)
        target_range = self._resolve_todo_range(target)
        original_conflicts = (
            self._find_conflicts(target_range, active_todos, target.id) if target_range else []
        )

        llm_client = self._get_llm_client()
        if not llm_client.is_available():
            raise TodoTimeOptimizationError(503, "LLM_UNAVAILABLE", "LLM 服务当前不可用，请检查配置")

        messages = self._build_messages(target, active_todos, original_conflicts)
        try:
            response_text = llm_client.chat(
                messages=messages,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
            )
        except Exception as exc:
            logger.warning(f"AI 待办时间优化请求失败: {exc}")
            raise TodoTimeOptimizationError(
                502,
                "LLM_REQUEST_FAILED",
                "AI 时间优化请求失败，请检查 AI 服务配置",
                str(exc),
            ) from exc

        data = self._parse_llm_response(response_text)
        after = self._resolve_recommended_range(data, target_range)
        self._validate_recommended_range(after, active_todos, target.id)

        return TodoTimeOptimizationResponse(
            todo_id=target.id,
            todo_name=target.name,
            before=self._range_to_schema(target_range),
            after=self._range_to_schema(after),
            has_conflict=bool(original_conflicts),
            conflicts=original_conflicts,
            reason=self._normalize_reason(data),
            confidence=self._normalize_confidence(data.get("confidence")),
        )

    def _load_active_todos(self, todo_service: TodoService) -> list[TodoResponse]:
        payload = todo_service.list_todos(
            limit=MAX_ACTIVE_TODOS_FOR_PROMPT,
            offset=0,
            status="active",
        )
        return list(payload.get("todos", []))

    def _get_llm_client(self) -> Any:
        return self._llm_client or LLMClient()

    def _build_messages(
        self,
        target: TodoResponse,
        active_todos: list[TodoResponse],
        original_conflicts: list[TodoTimeOptimizationConflict],
    ) -> list[dict[str, str]]:
        now = self._now_provider()
        payload = {
            "current_time": self._to_iso(self._ensure_aware(now)),
            "target_todo": self._todo_to_prompt_dict(target),
            "active_todos": [self._todo_to_prompt_dict(todo) for todo in active_todos],
            "detected_conflicts": [
                conflict.model_dump(mode="json") for conflict in original_conflicts
            ],
            "default_duration_minutes": DEFAULT_DURATION_MINUTES,
        }
        system_prompt = (
            "你是 BrightToDo 的待办时间规划助手。请检查目标待办与当前活动待办的时间冲突，"
            "并推荐一个更适合执行该待办的未来时间段。只输出 JSON，不要输出 Markdown。"
        )
        user_prompt = (
            "请根据以下 JSON 数据推荐目标待办的新执行时间。\n"
            "规则：\n"
            "1. recommended_start_time 和 recommended_end_time 必须是 ISO 8601 时间，必须带时区。\n"
            "2. 如果原时间有冲突，请避开所有 active_todos 的时间段。\n"
            "3. 如果原时间没有冲突，也要默认优化为更适合专注执行的未来时间。\n"
            "4. 不要修改其他待办，只推荐目标待办时间。\n"
            "5. confidence 为 0 到 1 的数字。\n\n"
            "返回格式：\n"
            '{"recommended_start_time":"2030-01-01T09:00:00+08:00",'
            '"recommended_end_time":"2030-01-01T10:00:00+08:00",'
            '"reason":"推荐理由","confidence":0.8}\n\n'
            f"数据：\n{json.dumps(payload, ensure_ascii=False)}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _todo_to_prompt_dict(self, todo: TodoResponse) -> dict[str, Any]:
        time_range = self._resolve_todo_range(todo)
        return {
            "id": todo.id,
            "name": todo.name,
            "description": todo.description,
            "priority": todo.priority,
            "status": todo.status,
            "parent_todo_id": todo.parent_todo_id,
            "start_time": self._to_iso(todo.start_time),
            "end_time": self._to_iso(todo.end_time),
            "dtstart": self._to_iso(todo.dtstart),
            "dtend": self._to_iso(todo.dtend),
            "due": self._to_iso(todo.due),
            "deadline": self._to_iso(todo.deadline),
            "duration": todo.duration,
            "resolved_start_time": self._to_iso(time_range.start) if time_range else None,
            "resolved_end_time": self._to_iso(time_range.end) if time_range else None,
        }

    def _parse_llm_response(self, response_text: str) -> dict[str, Any]:
        raw = response_text.strip()
        match = JSON_OBJECT_RE.search(raw)
        if match:
            raw = match.group(0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TodoTimeOptimizationError(
                502,
                "LLM_RESPONSE_INVALID",
                "AI 返回内容不是有效 JSON",
                str(exc),
            ) from exc
        if not isinstance(data, dict):
            raise TodoTimeOptimizationError(502, "LLM_RESPONSE_INVALID", "AI 返回结构无效")
        return data

    def _resolve_recommended_range(
        self,
        data: dict[str, Any],
        target_range: TimeRange | None,
    ) -> TimeRange:
        after_raw = data.get("after") if isinstance(data.get("after"), dict) else {}
        start_raw = (
            data.get("recommended_start_time")
            or data.get("start_time")
            or after_raw.get("start_time")
        )
        end_raw = (
            data.get("recommended_end_time")
            or data.get("end_time")
            or after_raw.get("end_time")
        )
        start = self._parse_llm_datetime(start_raw)
        if start is None:
            raise TodoTimeOptimizationError(502, "LLM_RESPONSE_INVALID", "AI 未返回推荐开始时间")

        end = self._parse_llm_datetime(end_raw)
        if end is None:
            duration = (target_range.end - target_range.start) if target_range else self._default_duration()
            end = start + duration
        if end <= start:
            raise TodoTimeOptimizationError(422, "RECOMMENDATION_INVALID", "AI 推荐结束时间必须晚于开始时间")
        return TimeRange(start=start, end=end)

    def _validate_recommended_range(
        self,
        recommended: TimeRange,
        active_todos: list[TodoResponse],
        target_id: int,
    ) -> None:
        now = self._ensure_aware(self._now_provider())
        if recommended.start <= now:
            raise TodoTimeOptimizationError(422, "RECOMMENDATION_IN_PAST", "AI 推荐时间不能早于当前时间")

        conflicts = self._find_conflicts(recommended, active_todos, target_id)
        if conflicts:
            names = "、".join(conflict.name for conflict in conflicts[:3])
            raise TodoTimeOptimizationError(
                422,
                "RECOMMENDATION_CONFLICT",
                f"AI 推荐时间仍与活动待办冲突：{names}",
            )

    def _resolve_todo_range(self, todo: TodoResponse) -> TimeRange | None:
        start_raw = todo.start_time or todo.dtstart or todo.due or todo.deadline
        if start_raw is None:
            return None

        start = self._normalize_existing_datetime(start_raw)
        end_raw = todo.end_time or todo.dtend
        end = self._normalize_existing_datetime(end_raw) if end_raw else None
        duration = self._parse_duration(todo.duration) or self._default_duration()
        if end is None or end <= start:
            end = start + duration
        return TimeRange(start=start, end=end)

    def _find_conflicts(
        self,
        checked: TimeRange,
        todos: list[TodoResponse],
        excluded_todo_id: int,
    ) -> list[TodoTimeOptimizationConflict]:
        conflicts: list[TodoTimeOptimizationConflict] = []
        for todo in todos:
            if todo.id == excluded_todo_id:
                continue
            todo_range = self._resolve_todo_range(todo)
            if todo_range is None or not self._overlaps(checked, todo_range):
                continue
            conflicts.append(
                TodoTimeOptimizationConflict(
                    id=todo.id,
                    name=todo.name,
                    start_time=todo_range.start,
                    end_time=todo_range.end,
                )
            )
        return conflicts

    def _parse_duration(self, value: str | None) -> timedelta | None:
        if not value:
            return None
        match = ISO_DURATION_RE.match(value.strip().upper())
        if not match:
            return None
        days = int(match.group("days") or 0)
        hours = float(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        seconds = int(match.group("seconds") or 0)
        duration = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        return duration if duration.total_seconds() > 0 else None

    def _parse_llm_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return to_utc(parsed)
        return parsed.astimezone(UTC)

    def _normalize_existing_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return naive_as_utc(value)
        return value.astimezone(UTC)

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return naive_as_utc(value)
        return value.astimezone(UTC)

    def _range_to_schema(self, value: TimeRange | None) -> TodoTimeOptimizationRange:
        return TodoTimeOptimizationRange(
            start_time=value.start if value else None,
            end_time=value.end if value else None,
        )

    def _to_iso(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return self._ensure_aware(value).isoformat()

    def _default_duration(self) -> timedelta:
        return timedelta(minutes=DEFAULT_DURATION_MINUTES)

    def _overlaps(self, left: TimeRange, right: TimeRange) -> bool:
        return left.start < right.end and right.start < left.end

    def _normalize_reason(self, data: dict[str, Any]) -> str:
        reason = str(data.get("reason") or data.get("summary") or "").strip()
        return reason or "已根据活动待办时间安排推荐更合适的执行时间。"

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.7
        return min(max(confidence, 0.0), 1.0)
