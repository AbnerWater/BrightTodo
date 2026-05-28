from __future__ import annotations

from datetime import datetime

import pytest

from lifetrace.schemas.todo import TodoPriority
from lifetrace.services.agent_parse_service import AgentParseService

REFERENCE = datetime.fromisoformat("2026-05-19T10:00:00+08:00")


@pytest.mark.parametrize(
    ("text", "title", "priority", "due", "duration"),
    [
        (
            "明天下午三点前完成线代作业",
            "完成线代作业",
            TodoPriority.MEDIUM,
            "2026-05-20T15:00:00+08:00",
            None,
        ),
        (
            "下周一之前交操作系统实验报告，很紧急，要4小时",
            "交操作系统实验报告",
            TodoPriority.HIGH,
            "2026-05-25T23:59:00+08:00",
            "PT4H",
        ),
        (
            "三天后提交英语作业",
            "提交英语作业",
            TodoPriority.NONE,
            "2026-05-22T23:59:00+08:00",
            None,
        ),
        (
            "今天晚上九点背单词半小时",
            "背单词",
            TodoPriority.NONE,
            "2026-05-19T21:00:00+08:00",
            "PT30M",
        ),
        (
            "这周五前复习数据库，低优先级",
            "复习数据库",
            TodoPriority.LOW,
            "2026-05-22T23:59:00+08:00",
            None,
        ),
        (
            "明天早上把PPT做完，大概需要三个小时",
            "把PPT做完",
            TodoPriority.NONE,
            "2026-05-20T23:59:00+08:00",
            "PT3H",
        ),
        (
            "完成课程设计，截止日期是5月25号",
            "完成课程设计",
            TodoPriority.NONE,
            "2026-05-25T23:59:00+08:00",
            None,
        ),
        (
            "紧急：明天早八前提交代码",
            "提交代码",
            TodoPriority.HIGH,
            "2026-05-20T08:00:00+08:00",
            None,
        ),
        (
            "下下周三完成毕业论文初稿",
            "完成毕业论文初稿",
            TodoPriority.NONE,
            "2026-06-03T23:59:00+08:00",
            None,
        ),
        ("买东西", "买东西", TodoPriority.NONE, None, None),
        (
            "今天把高数作业做了，中等优先级，需要90分钟",
            "把高数作业做了",
            TodoPriority.MEDIUM,
            "2026-05-19T23:59:00+08:00",
            "PT90M",
        ),
        (
            "后天上午十点开组会，准备汇报材料",
            "准备汇报材料",
            TodoPriority.NONE,
            "2026-05-21T10:00:00+08:00",
            None,
        ),
        (
            "本周内完成软件工程大作业，高优先级，预计8小时",
            "完成软件工程大作业",
            TodoPriority.HIGH,
            "2026-05-25T23:59:00+08:00",
            "PT8H",
        ),
        (
            "明天中午之前回复导师邮件",
            "回复导师邮件",
            TodoPriority.NONE,
            "2026-05-20T12:00:00+08:00",
            None,
        ),
        (
            "下周五前背完第五章单词，大概要两小时",
            "背完第五章单词",
            TodoPriority.NONE,
            "2026-05-29T23:59:00+08:00",
            "PT2H",
        ),
        (
            "今晚十一点前提交作业",
            "提交作业",
            TodoPriority.NONE,
            "2026-05-19T23:00:00+08:00",
            None,
        ),
        (
            "一周后交实验报告",
            "交实验报告",
            TodoPriority.NONE,
            "2026-05-26T23:59:00+08:00",
            None,
        ),
        (
            "明天把宿舍打扫一下，不急",
            "把宿舍打扫一下",
            TodoPriority.LOW,
            "2026-05-20T23:59:00+08:00",
            None,
        ),
        (
            "6月1号前完成毕业设计答辩PPT，非常紧急，需要6小时",
            "完成毕业设计答辩PPT",
            TodoPriority.HIGH,
            "2026-06-01T23:59:00+08:00",
            "PT6H",
        ),
        ("整理笔记", "整理笔记", TodoPriority.NONE, None, None),
    ],
)
def test_parse_task_matches_sprint1_cases(
    text: str,
    title: str,
    priority: TodoPriority,
    due: str | None,
    duration: str | None,
) -> None:
    result = AgentParseService().parse_task(text, REFERENCE)

    assert result.task_title == title
    assert result.priority == priority
    assert result.duration == duration
    assert result.raw_text == text
    assert result.parse_version
    if due is None:
        assert result.due is None
    else:
        assert result.due is not None
        assert result.due.isoformat() == due


def test_parse_task_uses_reference_timezone_for_naive_datetime() -> None:
    reference = REFERENCE.replace(tzinfo=None)

    result = AgentParseService().parse_task("明天下午三点前完成线代作业", reference)

    assert result.due is not None
    assert result.due.isoformat() == "2026-05-20T15:00:00+08:00"
