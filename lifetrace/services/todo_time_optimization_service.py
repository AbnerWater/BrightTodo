"""待办 AI 时间冲突检查与执行时间推荐服务"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from lifetrace.llm.llm_client import LLMClient
from lifetrace.schemas.todo import (
    TodoResponse,
    TodoTimeOptimizationConflict,
    TodoTimeOptimizationItem,
    TodoTimeOptimizationRange,
    TodoTimeOptimizationResponse,
)
from lifetrace.util.logging_config import get_logger
from lifetrace.util.time_utils import get_utc_now, naive_as_utc, to_utc

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger()

DEFAULT_DURATION_MINUTES = 60
MAX_TODOS_FOR_TREE = 1000
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 4000
PARTICIPATING_CHILD_STATUSES = {"active", "draft"}
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


@dataclass(frozen=True)
class OptimizationTarget:
    """本次参与 AI 时间优化的待办"""

    todo: TodoResponse
    depth: int


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
    """生成父级待办及其子任务的 AI 时间优化预览。"""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        now_provider: Callable[[], datetime] = get_utc_now,
    ) -> None:
        self._llm_client = llm_client
        self._now_provider = now_provider

    def optimize(self, todo_id: int, todo_service: Any) -> TodoTimeOptimizationResponse:
        target = todo_service.get_todo(todo_id)
        if target.status != "active":
            raise TodoTimeOptimizationError(400, "INVALID_TODO_STATUS", "仅支持优化活动待办")

        all_todos = self._load_all_todos(todo_service, target)
        targets = self._build_optimization_targets(target, all_todos)
        group_ids = {item.todo.id for item in targets}
        parent_by_id = self._build_parent_map(all_todos)
        external_active_todos = [
            todo for todo in all_todos if todo.status == "active" and todo.id not in group_ids
        ]
        original_conflicts = self._build_original_conflicts(
            targets,
            external_active_todos,
            parent_by_id,
        )

        llm_client = self._get_llm_client()
        if not llm_client.is_available():
            raise TodoTimeOptimizationError(503, "LLM_UNAVAILABLE", "LLM 服务当前不可用，请检查配置")

        messages = self._build_messages(target, targets, external_active_todos, original_conflicts)
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
        recommended = self._resolve_recommended_ranges(data, targets)
        recommended = self._expand_root_to_cover_children(target.id, recommended, targets)
        self._validate_recommended_ranges(
            recommended,
            targets,
            external_active_todos,
            parent_by_id,
        )

        items = self._build_response_items(data, targets, recommended, original_conflicts)
        root_item = items[0]
        aggregated_conflicts = self._aggregate_conflicts(items)
        return TodoTimeOptimizationResponse(
            todo_id=root_item.todo_id,
            todo_name=root_item.todo_name,
            before=root_item.before,
            after=root_item.after,
            has_conflict=any(item.has_conflict for item in items),
            conflicts=aggregated_conflicts,
            reason=self._normalize_reason(data, None, root_item.reason),
            confidence=root_item.confidence,
            items=items,
        )

    def _load_all_todos(self, todo_service: Any, target: TodoResponse) -> list[TodoResponse]:
        payload = todo_service.list_todos(limit=MAX_TODOS_FOR_TREE, offset=0, status=None)
        todos = list(payload.get("todos", []))
        if all(todo.id != target.id for todo in todos):
            todos.insert(0, target)
        return todos

    def _build_optimization_targets(
        self,
        root: TodoResponse,
        all_todos: list[TodoResponse],
    ) -> list[OptimizationTarget]:
        children_map: dict[int, list[TodoResponse]] = {}
        for todo in all_todos:
            if todo.parent_todo_id is None:
                continue
            children_map.setdefault(todo.parent_todo_id, []).append(todo)

        for children in children_map.values():
            children.sort(key=lambda item: (item.order, item.created_at, item.id))

        targets = [OptimizationTarget(todo=root, depth=0)]
        visited = {root.id}

        def traverse(parent_id: int, depth: int) -> None:
            for child in children_map.get(parent_id, []):
                if child.id in visited:
                    continue
                visited.add(child.id)
                if child.status in PARTICIPATING_CHILD_STATUSES:
                    targets.append(OptimizationTarget(todo=child, depth=depth))
                traverse(child.id, depth + 1)

        traverse(root.id, 1)
        return targets

    def _build_parent_map(self, todos: list[TodoResponse]) -> dict[int, int | None]:
        return {todo.id: todo.parent_todo_id for todo in todos}

    def _build_original_conflicts(
        self,
        targets: list[OptimizationTarget],
        external_active_todos: list[TodoResponse],
        parent_by_id: dict[int, int | None],
    ) -> dict[int, list[TodoTimeOptimizationConflict]]:
        target_todos = [item.todo for item in targets]
        result: dict[int, list[TodoTimeOptimizationConflict]] = {}
        for item in targets:
            todo_range = self._resolve_todo_range(item.todo)
            if todo_range is None:
                result[item.todo.id] = []
                continue
            conflicts = self._find_range_conflicts(todo_range, external_active_todos)
            conflicts.extend(
                self._find_internal_conflicts(
                    item.todo,
                    todo_range,
                    target_todos,
                    parent_by_id,
                )
            )
            result[item.todo.id] = self._dedupe_conflicts(conflicts)
        return result

    def _get_llm_client(self) -> Any:
        return self._llm_client or LLMClient()

    def _build_messages(
        self,
        target: TodoResponse,
        targets: list[OptimizationTarget],
        external_active_todos: list[TodoResponse],
        original_conflicts: dict[int, list[TodoTimeOptimizationConflict]],
    ) -> list[dict[str, str]]:
        now = self._now_provider()
        payload = {
            "current_time": self._to_iso(self._ensure_aware(now)),
            "root_todo": self._todo_to_prompt_dict(target, depth=0),
            "optimization_todos": [
                self._todo_to_prompt_dict(item.todo, depth=item.depth) for item in targets
            ],
            "external_active_todos": [
                self._todo_to_prompt_dict(todo) for todo in external_active_todos
            ],
            "detected_conflicts": [
                {
                    "todo_id": item.todo.id,
                    "todo_name": item.todo.name,
                    "conflicts": [
                        conflict.model_dump(mode="json")
                        for conflict in original_conflicts.get(item.todo.id, [])
                    ],
                }
                for item in targets
            ],
            "included_child_statuses": sorted(PARTICIPATING_CHILD_STATUSES),
            "default_duration_minutes": DEFAULT_DURATION_MINUTES,
        }
        system_prompt = (
            "你是 BrightToDo 的父子待办时间规划助手。请联合检查目标父待办及其参与子任务"
            "与当前活动待办的时间冲突，并为每个参与待办推荐未来执行时间。"
            "只输出 JSON，不要输出 Markdown。"
        )
        user_prompt = (
            "请根据以下 JSON 数据，为 optimization_todos 中的每一个待办推荐新执行时间。\n"
            "规则：\n"
            "1. items 必须包含 optimization_todos 的每个 todo_id，且每个 todo_id 只出现一次。\n"
            "2. recommended_start_time 和 recommended_end_time 必须是 ISO 8601 时间，必须带时区。\n"
            "3. 推荐时间必须避开 external_active_todos 的时间段。\n"
            "4. 非祖先关系的参与待办之间不要互相重叠；父级待办作为容器时间段，应覆盖子任务。\n"
            "5. 如果原时间没有冲突，也要默认优化为更适合专注执行的未来时间。\n"
            "6. 不要修改 external_active_todos，只推荐 optimization_todos 的时间。\n"
            "7. confidence 为 0 到 1 的数字。\n\n"
            "返回格式：\n"
            '{"summary":"整体推荐理由","items":[{"todo_id":1,'
            '"recommended_start_time":"2030-01-01T09:00:00+08:00",'
            '"recommended_end_time":"2030-01-01T10:00:00+08:00",'
            '"reason":"推荐理由","confidence":0.8}]}\n\n'
            f"数据：\n{json.dumps(payload, ensure_ascii=False)}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _todo_to_prompt_dict(self, todo: TodoResponse, depth: int | None = None) -> dict[str, Any]:
        time_range = self._resolve_todo_range(todo)
        result = {
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
        if depth is not None:
            result["depth"] = depth
        return result

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

    def _resolve_recommended_ranges(
        self,
        data: dict[str, Any],
        targets: list[OptimizationTarget],
    ) -> dict[int, TimeRange]:
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            if len(targets) == 1:
                raw_items = [data]
            else:
                raise TodoTimeOptimizationError(
                    502,
                    "LLM_RESPONSE_INVALID",
                    "AI 未返回父子待办逐项推荐",
                )

        target_by_id = {item.todo.id: item for item in targets}
        raw_by_id: dict[int, dict[str, Any]] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item_id = self._parse_int(raw_item.get("todo_id") or raw_item.get("id"))
            if item_id in target_by_id:
                raw_by_id[item_id] = raw_item

        missing_ids = [item.todo.id for item in targets if item.todo.id not in raw_by_id]
        if missing_ids:
            raise TodoTimeOptimizationError(
                502,
                "LLM_RESPONSE_INVALID",
                "AI 未返回全部参与待办的推荐时间",
                f"missing_todo_ids={missing_ids}",
            )

        return {
            item.todo.id: self._resolve_recommended_range(
                raw_by_id[item.todo.id],
                self._resolve_todo_range(item.todo),
                item.todo.name,
            )
            for item in targets
        }

    def _resolve_recommended_range(
        self,
        data: dict[str, Any],
        target_range: TimeRange | None,
        todo_name: str,
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
            raise TodoTimeOptimizationError(
                502,
                "LLM_RESPONSE_INVALID",
                f"AI 未返回「{todo_name}」的推荐开始时间",
            )

        end = self._parse_llm_datetime(end_raw)
        if end is None:
            duration = (target_range.end - target_range.start) if target_range else self._default_duration()
            end = start + duration
        if end <= start:
            raise TodoTimeOptimizationError(
                422,
                "RECOMMENDATION_INVALID",
                f"AI 推荐「{todo_name}」的结束时间必须晚于开始时间",
            )
        return TimeRange(start=start, end=end)

    def _expand_root_to_cover_children(
        self,
        root_id: int,
        recommended: dict[int, TimeRange],
        targets: list[OptimizationTarget],
    ) -> dict[int, TimeRange]:
        child_ranges = [
            recommended[item.todo.id]
            for item in targets
            if item.todo.id != root_id and item.todo.id in recommended
        ]
        if not child_ranges or root_id not in recommended:
            return recommended

        root_range = recommended[root_id]
        expanded = TimeRange(
            start=min(root_range.start, *(item.start for item in child_ranges)),
            end=max(root_range.end, *(item.end for item in child_ranges)),
        )
        return {**recommended, root_id: expanded}

    def _validate_recommended_ranges(
        self,
        recommended: dict[int, TimeRange],
        targets: list[OptimizationTarget],
        external_active_todos: list[TodoResponse],
        parent_by_id: dict[int, int | None],
    ) -> None:
        now = self._ensure_aware(self._now_provider())
        for item in targets:
            item_range = recommended[item.todo.id]
            if item_range.start <= now:
                raise TodoTimeOptimizationError(
                    422,
                    "RECOMMENDATION_IN_PAST",
                    f"AI 推荐「{item.todo.name}」的时间不能早于当前时间",
                )
            conflicts = self._find_range_conflicts(item_range, external_active_todos)
            if conflicts:
                names = "、".join(conflict.name for conflict in conflicts[:3])
                raise TodoTimeOptimizationError(
                    422,
                    "RECOMMENDATION_CONFLICT",
                    f"AI 推荐时间仍与活动待办冲突：{item.todo.name} 与 {names}",
                )

        group_conflict = self._find_recommended_group_conflict(
            recommended,
            targets,
            parent_by_id,
        )
        if group_conflict:
            left, right = group_conflict
            raise TodoTimeOptimizationError(
                422,
                "RECOMMENDATION_GROUP_CONFLICT",
                f"AI 推荐后父子待办组内仍存在时间冲突：{left} 与 {right}",
            )

    def _build_response_items(
        self,
        data: dict[str, Any],
        targets: list[OptimizationTarget],
        recommended: dict[int, TimeRange],
        original_conflicts: dict[int, list[TodoTimeOptimizationConflict]],
    ) -> list[TodoTimeOptimizationItem]:
        raw_by_id = self._raw_items_by_id(data)
        items: list[TodoTimeOptimizationItem] = []
        for target in targets:
            todo = target.todo
            conflicts = original_conflicts.get(todo.id, [])
            raw_item = raw_by_id.get(todo.id)
            items.append(
                TodoTimeOptimizationItem(
                    todo_id=todo.id,
                    todo_name=todo.name,
                    parent_todo_id=todo.parent_todo_id,
                    status=todo.status,
                    depth=target.depth,
                    before=self._range_to_schema(self._resolve_todo_range(todo)),
                    after=self._range_to_schema(recommended[todo.id]),
                    has_conflict=bool(conflicts),
                    conflicts=conflicts,
                    reason=self._normalize_reason(raw_item, data),
                    confidence=self._normalize_confidence(
                        raw_item.get("confidence") if raw_item else data.get("confidence")
                    ),
                )
            )
        return items

    def _raw_items_by_id(self, data: dict[str, Any]) -> dict[int, dict[str, Any]]:
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return {}
        result: dict[int, dict[str, Any]] = {}
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item_id = self._parse_int(raw_item.get("todo_id") or raw_item.get("id"))
            if item_id is not None:
                result[item_id] = raw_item
        return result

    def _find_range_conflicts(
        self,
        checked: TimeRange,
        todos: list[TodoResponse],
    ) -> list[TodoTimeOptimizationConflict]:
        conflicts: list[TodoTimeOptimizationConflict] = []
        for todo in todos:
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

    def _find_internal_conflicts(
        self,
        checked_todo: TodoResponse,
        checked_range: TimeRange,
        target_todos: list[TodoResponse],
        parent_by_id: dict[int, int | None],
    ) -> list[TodoTimeOptimizationConflict]:
        conflicts: list[TodoTimeOptimizationConflict] = []
        for todo in target_todos:
            if todo.id == checked_todo.id or self._has_ancestor_relation(
                checked_todo.id,
                todo.id,
                parent_by_id,
            ):
                continue
            todo_range = self._resolve_todo_range(todo)
            if todo_range is None or not self._overlaps(checked_range, todo_range):
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

    def _find_recommended_group_conflict(
        self,
        recommended: dict[int, TimeRange],
        targets: list[OptimizationTarget],
        parent_by_id: dict[int, int | None],
    ) -> tuple[str, str] | None:
        for left_index, left in enumerate(targets):
            for right in targets[left_index + 1 :]:
                if self._has_ancestor_relation(left.todo.id, right.todo.id, parent_by_id):
                    continue
                if self._overlaps(recommended[left.todo.id], recommended[right.todo.id]):
                    return left.todo.name, right.todo.name
        return None

    def _has_ancestor_relation(
        self,
        left_id: int,
        right_id: int,
        parent_by_id: dict[int, int | None],
    ) -> bool:
        return self._is_ancestor(left_id, right_id, parent_by_id) or self._is_ancestor(
            right_id,
            left_id,
            parent_by_id,
        )

    def _is_ancestor(
        self,
        ancestor_id: int,
        child_id: int,
        parent_by_id: dict[int, int | None],
    ) -> bool:
        visited: set[int] = set()
        parent_id = parent_by_id.get(child_id)
        while parent_id is not None and parent_id not in visited:
            if parent_id == ancestor_id:
                return True
            visited.add(parent_id)
            parent_id = parent_by_id.get(parent_id)
        return False

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

    def _parse_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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

    def _normalize_reason(
        self,
        data: dict[str, Any] | None,
        fallback_data: dict[str, Any] | None = None,
        fallback_text: str | None = None,
    ) -> str:
        for candidate in (
            data.get("reason") if data else None,
            data.get("summary") if data else None,
            fallback_data.get("reason") if fallback_data else None,
            fallback_data.get("summary") if fallback_data else None,
            fallback_text,
        ):
            reason = str(candidate or "").strip()
            if reason:
                return reason
        return "已根据父子待办与活动待办时间安排推荐更合适的执行时间。"

    def _normalize_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.7
        return min(max(confidence, 0.0), 1.0)

    def _aggregate_conflicts(
        self,
        items: list[TodoTimeOptimizationItem],
    ) -> list[TodoTimeOptimizationConflict]:
        conflicts: list[TodoTimeOptimizationConflict] = []
        seen: set[int] = set()
        for item in items:
            for conflict in item.conflicts:
                if conflict.id in seen:
                    continue
                seen.add(conflict.id)
                conflicts.append(conflict)
        return conflicts

    def _dedupe_conflicts(
        self,
        conflicts: list[TodoTimeOptimizationConflict],
    ) -> list[TodoTimeOptimizationConflict]:
        result: list[TodoTimeOptimizationConflict] = []
        seen: set[int] = set()
        for conflict in conflicts:
            if conflict.id in seen:
                continue
            seen.add(conflict.id)
            result.append(conflict)
        return result
