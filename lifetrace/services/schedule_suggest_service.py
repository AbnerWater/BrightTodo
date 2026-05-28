"""BrightToDo 智能日程编排服务"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from lifetrace.schemas.agent import (
    ScheduleAlternative,
    ScheduleConstraint,
    ScheduleSuggestion,
    ScheduleSuggestRequest,
    ScheduleSuggestResponse,
    ScheduleSuggestTodo,
)
from lifetrace.schemas.todo import TodoPriority
from lifetrace.util.time_utils import get_utc_now

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_TASK_MINUTES = 60
SLOT_STEP_MINUTES = 30
WORKDAY_START = time(8, 0)
WORKDAY_END = time(22, 0)
DEFAULT_LOOKAHEAD_DAYS = 7
MAX_ALTERNATIVES = 2
MAX_DAILY_AVAILABLE_HOURS = 16
MIN_WEEKDAY = 1
MAX_WEEKDAY = 7
MIN_HOUR = 0
MAX_HOUR = 23
MIN_MINUTE = 0
MAX_MINUTE = 59

DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+)M)?)?$",
    re.IGNORECASE,
)
CLOCK_RE = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")

PRIORITY_RANK = {
    TodoPriority.HIGH: 0,
    TodoPriority.MEDIUM: 1,
    TodoPriority.LOW: 2,
    TodoPriority.NONE: 3,
}
PRIORITY_LABELS = {
    TodoPriority.HIGH: "高优先级",
    TodoPriority.MEDIUM: "中优先级",
    TodoPriority.LOW: "低优先级",
    TodoPriority.NONE: "普通优先级",
}
WEEKDAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "周日",
}


@dataclass(frozen=True)
class TimeSlot:
    """可安排或已占用的时间段"""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class NormalizedConstraint:
    """标准化后的周期约束"""

    weekday: int
    start_time: time
    end_time: time
    label: str | None


class ScheduleSuggestError(ValueError):
    """智能编排领域错误"""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class ScheduleSuggestService:
    """生成避开课程冲突的待办执行建议。"""

    def suggest(self, request: ScheduleSuggestRequest) -> ScheduleSuggestResponse:
        if not request.todos:
            raise ScheduleSuggestError("INVALID_INPUT", "待编排任务不能为空")

        planning_start = self._normalize_datetime(request.planning_start)
        planning_end = self._resolve_planning_end(request, planning_start)
        if planning_end <= planning_start:
            raise ScheduleSuggestError("INVALID_INPUT", "编排结束时间必须晚于开始时间")

        daily_limit_minutes = self._normalize_daily_limit(request.daily_available_hours)
        constraints = self._normalize_constraints(request.schedule_constraints)
        occupied_slots: list[TimeSlot] = []
        suggestions: list[ScheduleSuggestion] = []
        unscheduled_todos: list[int] = []

        for todo in sorted(request.todos, key=self._todo_sort_key):
            duration_minutes = self._parse_duration_minutes(todo.duration)
            todo_end = self._resolve_todo_window_end(todo, planning_end)
            if todo_end <= planning_start:
                unscheduled_todos.append(todo.id)
                continue

            candidates = self._collect_candidates(
                start=planning_start,
                end=todo_end,
                duration_minutes=duration_minutes,
                daily_limit_minutes=daily_limit_minutes,
                constraints=constraints,
                occupied_slots=occupied_slots,
            )
            if not candidates:
                unscheduled_todos.append(todo.id)
                continue

            chosen = candidates[0]
            alternatives = [
                ScheduleAlternative(suggested_start=slot.start, suggested_end=slot.end)
                for slot in candidates[1 : MAX_ALTERNATIVES + 1]
            ]
            suggestions.append(
                ScheduleSuggestion(
                    todo_id=todo.id,
                    todo_name=todo.name,
                    suggested_start=chosen.start,
                    suggested_end=chosen.end,
                    reason=self._build_reason(todo, chosen),
                    alternatives=alternatives,
                )
            )
            occupied_slots.append(chosen)

        if not suggestions:
            raise ScheduleSuggestError("NO_AVAILABLE_SLOTS", "没有可用时间段可以安排待办")

        coverage = round(len(suggestions) / len(request.todos) * 100, 2)
        return ScheduleSuggestResponse(
            suggestions=suggestions,
            unscheduled_todos=unscheduled_todos,
            planning_coverage_pct=coverage,
        )

    def _normalize_datetime(self, value: datetime | None) -> datetime:
        if value is None:
            return get_utc_now().astimezone(LOCAL_TZ)
        if value.tzinfo is None:
            return value.replace(tzinfo=LOCAL_TZ)
        return value.astimezone(LOCAL_TZ)

    def _resolve_planning_end(
        self, request: ScheduleSuggestRequest, planning_start: datetime
    ) -> datetime:
        if request.planning_end is not None:
            return self._normalize_datetime(request.planning_end)

        due_dates = [
            self._normalize_datetime(todo.due)
            for todo in request.todos
            if todo.due is not None and self._normalize_datetime(todo.due) > planning_start
        ]
        if due_dates:
            return min(due_dates)
        return planning_start + timedelta(days=DEFAULT_LOOKAHEAD_DAYS)

    def _normalize_daily_limit(self, daily_available_hours: int) -> int:
        if daily_available_hours <= 0:
            raise ScheduleSuggestError("INVALID_INPUT", "每日可用学习时长必须大于 0")
        if daily_available_hours > MAX_DAILY_AVAILABLE_HOURS:
            raise ScheduleSuggestError("INVALID_INPUT", "每日可用学习时长不能超过 16 小时")
        return daily_available_hours * 60

    def _normalize_constraints(
        self, constraints: list[ScheduleConstraint]
    ) -> list[NormalizedConstraint]:
        normalized = []
        for constraint in constraints:
            if not MIN_WEEKDAY <= constraint.weekday <= MAX_WEEKDAY:
                raise ScheduleSuggestError("INVALID_INPUT", "约束 weekday 必须在 1 到 7 之间")
            start_time = self._parse_clock(constraint.start_time)
            end_time = self._parse_clock(constraint.end_time)
            if end_time <= start_time:
                raise ScheduleSuggestError("INVALID_INPUT", "约束结束时间必须晚于开始时间")
            normalized.append(
                NormalizedConstraint(
                    weekday=constraint.weekday,
                    start_time=start_time,
                    end_time=end_time,
                    label=constraint.label,
                )
            )
        return normalized

    def _parse_clock(self, value: str) -> time:
        match = CLOCK_RE.match(value)
        if not match:
            raise ScheduleSuggestError("INVALID_INPUT", "时间格式必须为 HH:MM")
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        if not MIN_HOUR <= hour <= MAX_HOUR or not MIN_MINUTE <= minute <= MAX_MINUTE:
            raise ScheduleSuggestError("INVALID_INPUT", "时间值超出有效范围")
        return time(hour, minute)

    def _todo_sort_key(self, todo: ScheduleSuggestTodo) -> tuple[int, datetime, int]:
        due = (
            self._normalize_datetime(todo.due)
            if todo.due is not None
            else datetime.max.replace(tzinfo=LOCAL_TZ)
        )
        return PRIORITY_RANK[todo.priority], due, todo.id

    def _parse_duration_minutes(self, duration: str | None) -> int:
        if duration is None:
            return DEFAULT_TASK_MINUTES

        match = DURATION_RE.match(duration.strip())
        if not match:
            raise ScheduleSuggestError("INVALID_INPUT", "duration 必须为 ISO 8601 Duration")

        days = int(match.group("days") or 0)
        hours = float(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        total_minutes = int(days * 24 * 60 + hours * 60 + minutes)
        if total_minutes <= 0:
            raise ScheduleSuggestError("INVALID_INPUT", "duration 必须大于 0")
        return total_minutes

    def _resolve_todo_window_end(
        self, todo: ScheduleSuggestTodo, planning_end: datetime
    ) -> datetime:
        if todo.due is None:
            return planning_end
        due = self._normalize_datetime(todo.due)
        return min(due, planning_end)

    def _collect_candidates(
        self,
        start: datetime,
        end: datetime,
        duration_minutes: int,
        daily_limit_minutes: int,
        constraints: list[NormalizedConstraint],
        occupied_slots: list[TimeSlot],
    ) -> list[TimeSlot]:
        candidates = []
        duration = timedelta(minutes=duration_minutes)
        for day in self._iter_dates(start.date(), end.date()):
            if self._scheduled_minutes_for_day(day, occupied_slots) + duration_minutes > (
                daily_limit_minutes
            ):
                continue

            day_start = max(datetime.combine(day, WORKDAY_START, LOCAL_TZ), start)
            day_end = min(datetime.combine(day, WORKDAY_END, LOCAL_TZ), end)
            cursor = self._ceil_to_slot_step(day_start)
            while cursor + duration <= day_end:
                slot = TimeSlot(start=cursor, end=cursor + duration)
                if not self._has_conflict(slot, constraints, occupied_slots):
                    candidates.append(slot)
                cursor += timedelta(minutes=SLOT_STEP_MINUTES)
        return candidates

    def _iter_dates(self, start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)

    def _scheduled_minutes_for_day(self, day: date, slots: list[TimeSlot]) -> int:
        total = 0
        for slot in slots:
            if slot.start.date() == day:
                total += int((slot.end - slot.start).total_seconds() // 60)
        return total

    def _ceil_to_slot_step(self, value: datetime) -> datetime:
        minute = value.minute
        remainder = minute % SLOT_STEP_MINUTES
        if remainder == 0 and value.second == 0 and value.microsecond == 0:
            return value
        delta_minutes = SLOT_STEP_MINUTES - remainder if remainder else 0
        aligned = value + timedelta(minutes=delta_minutes)
        return aligned.replace(second=0, microsecond=0)

    def _has_conflict(
        self,
        slot: TimeSlot,
        constraints: list[NormalizedConstraint],
        occupied_slots: list[TimeSlot],
    ) -> bool:
        if any(self._overlaps(slot, occupied) for occupied in occupied_slots):
            return True
        return any(self._overlaps_constraint(slot, constraint) for constraint in constraints)

    def _overlaps_constraint(
        self, slot: TimeSlot, constraint: NormalizedConstraint
    ) -> bool:
        if slot.start.isoweekday() != constraint.weekday:
            return False
        constraint_slot = TimeSlot(
            start=datetime.combine(slot.start.date(), constraint.start_time, LOCAL_TZ),
            end=datetime.combine(slot.start.date(), constraint.end_time, LOCAL_TZ),
        )
        return self._overlaps(slot, constraint_slot)

    def _overlaps(self, left: TimeSlot, right: TimeSlot) -> bool:
        return left.start < right.end and right.start < left.end

    def _build_reason(self, todo: ScheduleSuggestTodo, slot: TimeSlot) -> str:
        weekday = WEEKDAY_LABELS[slot.start.isoweekday()]
        priority = PRIORITY_LABELS[todo.priority]
        deadline_text = ""
        if todo.due is not None:
            due = self._normalize_datetime(todo.due)
            days_left = max((due.date() - slot.end.date()).days, 0)
            deadline_text = (
                "，当天需要完成" if days_left == 0 else f"，距截止日期约 {days_left} 天"
            )
        return (
            f"{weekday} {slot.start:%H:%M}-{slot.end:%H:%M} 无课程冲突，"
            f"按{priority}排序安排{deadline_text}"
        )
