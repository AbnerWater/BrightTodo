from __future__ import annotations

from datetime import datetime

import pytest

from lifetrace.schemas.agent import (
    ScheduleConstraint,
    ScheduleSuggestRequest,
    ScheduleSuggestTodo,
)
from lifetrace.schemas.todo import TodoPriority
from lifetrace.services.schedule_suggest_service import (
    ScheduleSuggestError,
    ScheduleSuggestService,
)

FULL_COVERAGE = 100
HALF_COVERAGE = 50


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_schedule_suggest_avoids_course_constraint() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=101,
                name="完成操作系统作业",
                priority=TodoPriority.HIGH,
                due=_dt("2026-05-19T18:00:00+08:00"),
                duration="PT2H",
            )
        ],
        schedule_constraints=[
            ScheduleConstraint(
                weekday=2,
                start_time="10:00",
                end_time="12:00",
                label="操作系统课",
            )
        ],
        planning_start=_dt("2026-05-19T10:00:00+08:00"),
        planning_end=_dt("2026-05-19T18:00:00+08:00"),
        daily_available_hours=6,
    )

    result = ScheduleSuggestService().suggest(request)

    assert result.planning_coverage_pct == FULL_COVERAGE
    assert result.unscheduled_todos == []
    assert result.suggestions[0].suggested_start.isoformat() == "2026-05-19T12:00:00+08:00"
    assert result.suggestions[0].suggested_end.isoformat() == "2026-05-19T14:00:00+08:00"


def test_schedule_suggest_orders_high_priority_first() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=1,
                name="整理低优先级资料",
                priority=TodoPriority.LOW,
                duration="PT1H",
            ),
            ScheduleSuggestTodo(
                id=2,
                name="完成紧急实验报告",
                priority=TodoPriority.HIGH,
                duration="PT1H",
            ),
        ],
        planning_start=_dt("2026-05-19T08:00:00+08:00"),
        planning_end=_dt("2026-05-19T12:00:00+08:00"),
        daily_available_hours=6,
    )

    result = ScheduleSuggestService().suggest(request)

    assert [suggestion.todo_id for suggestion in result.suggestions] == [2, 1]
    assert result.suggestions[0].suggested_start.isoformat() == "2026-05-19T08:00:00+08:00"
    assert result.suggestions[1].suggested_start.isoformat() == "2026-05-19T09:00:00+08:00"


def test_schedule_suggest_orders_same_priority_by_due_time() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=1,
                name="周五前完成论文阅读",
                priority=TodoPriority.MEDIUM,
                due=_dt("2026-05-23T23:59:00+08:00"),
                duration="PT1H",
            ),
            ScheduleSuggestTodo(
                id=2,
                name="明天前完成实验预习",
                priority=TodoPriority.MEDIUM,
                due=_dt("2026-05-20T23:59:00+08:00"),
                duration="PT1H",
            ),
        ],
        planning_start=_dt("2026-05-19T08:00:00+08:00"),
        planning_end=_dt("2026-05-23T23:59:00+08:00"),
    )

    result = ScheduleSuggestService().suggest(request)

    assert [suggestion.todo_id for suggestion in result.suggestions] == [2, 1]


def test_schedule_suggest_normalizes_timezone_to_local_time() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=1,
                name="完成跨时区输入测试",
                priority=TodoPriority.MEDIUM,
                duration="PT1H",
            )
        ],
        planning_start=_dt("2026-05-19T00:30:00+00:00"),
        planning_end=_dt("2026-05-19T04:00:00+00:00"),
    )

    result = ScheduleSuggestService().suggest(request)

    assert result.suggestions[0].suggested_start.isoformat() == "2026-05-19T08:30:00+08:00"


def test_schedule_suggest_reports_partially_unscheduled_todos() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=1,
                name="完成短任务",
                priority=TodoPriority.HIGH,
                duration="PT1H",
            ),
            ScheduleSuggestTodo(
                id=2,
                name="完成长任务",
                priority=TodoPriority.MEDIUM,
                duration="PT5H",
            ),
        ],
        planning_start=_dt("2026-05-19T08:00:00+08:00"),
        planning_end=_dt("2026-05-19T12:00:00+08:00"),
        daily_available_hours=3,
    )

    result = ScheduleSuggestService().suggest(request)

    assert [suggestion.todo_id for suggestion in result.suggestions] == [1]
    assert result.unscheduled_todos == [2]
    assert result.planning_coverage_pct == HALF_COVERAGE


def test_schedule_suggest_raises_when_all_slots_blocked() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=101,
                name="完成操作系统作业",
                priority=TodoPriority.HIGH,
                duration="PT1H",
            )
        ],
        schedule_constraints=[
            ScheduleConstraint(
                weekday=2,
                start_time="08:00",
                end_time="22:00",
                label="全天课程",
            )
        ],
        planning_start=_dt("2026-05-19T08:00:00+08:00"),
        planning_end=_dt("2026-05-19T22:00:00+08:00"),
    )

    with pytest.raises(ScheduleSuggestError) as exc_info:
        ScheduleSuggestService().suggest(request)

    assert exc_info.value.error_code == "NO_AVAILABLE_SLOTS"


def test_schedule_suggest_rejects_invalid_duration() -> None:
    request = ScheduleSuggestRequest(
        todos=[
            ScheduleSuggestTodo(
                id=101,
                name="完成操作系统作业",
                priority=TodoPriority.HIGH,
                duration="2 hours",
            )
        ],
        planning_start=_dt("2026-05-19T08:00:00+08:00"),
        planning_end=_dt("2026-05-19T22:00:00+08:00"),
    )

    with pytest.raises(ScheduleSuggestError) as exc_info:
        ScheduleSuggestService().suggest(request)

    assert exc_info.value.error_code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "schedule_request",
    [
        ScheduleSuggestRequest(
            todos=[
                ScheduleSuggestTodo(
                    id=101,
                    name="完成操作系统作业",
                    priority=TodoPriority.HIGH,
                    duration="PT1H",
                )
            ],
            schedule_constraints=[
                ScheduleConstraint(weekday=8, start_time="08:00", end_time="09:00")
            ],
            planning_start=_dt("2026-05-19T08:00:00+08:00"),
            planning_end=_dt("2026-05-19T22:00:00+08:00"),
        ),
        ScheduleSuggestRequest(
            todos=[
                ScheduleSuggestTodo(
                    id=101,
                    name="完成操作系统作业",
                    priority=TodoPriority.HIGH,
                    duration="PT1H",
                )
            ],
            schedule_constraints=[
                ScheduleConstraint(weekday=2, start_time="10:00", end_time="09:00")
            ],
            planning_start=_dt("2026-05-19T08:00:00+08:00"),
            planning_end=_dt("2026-05-19T22:00:00+08:00"),
        ),
        ScheduleSuggestRequest(
            todos=[
                ScheduleSuggestTodo(
                    id=101,
                    name="完成操作系统作业",
                    priority=TodoPriority.HIGH,
                    duration="PT1H",
                )
            ],
            planning_start=_dt("2026-05-19T08:00:00+08:00"),
            planning_end=_dt("2026-05-19T22:00:00+08:00"),
            daily_available_hours=0,
        ),
    ],
)
def test_schedule_suggest_rejects_invalid_constraints_and_limits(
    schedule_request: ScheduleSuggestRequest,
) -> None:
    with pytest.raises(ScheduleSuggestError) as exc_info:
        ScheduleSuggestService().suggest(schedule_request)

    assert exc_info.value.error_code == "INVALID_INPUT"
