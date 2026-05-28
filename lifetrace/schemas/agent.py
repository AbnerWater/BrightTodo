"""BrightToDo Agent 自研接口模型"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from lifetrace.schemas.todo import TodoPriority


class AgentParseTaskRequest(BaseModel):
    """自然语言任务解析请求"""

    text: str = Field(..., description="中文自然语言任务描述")
    reference_time: datetime | None = Field(None, description="相对时间解析基准")


class AgentParseTaskResponse(BaseModel):
    """自然语言任务解析响应"""

    task_title: str = Field(..., description="解析出的任务标题")
    priority: TodoPriority = Field(..., description="任务优先级")
    due: datetime | None = Field(None, description="截止时间")
    duration: str | None = Field(None, description="预估时长，ISO 8601 Duration")
    description: str | None = Field(None, description="补充描述")
    confidence: float = Field(..., ge=0, le=1, description="解析置信度")
    raw_text: str = Field(..., description="原始输入文字")
    parse_version: str = Field(..., description="解析逻辑版本")


class ScheduleSuggestTodo(BaseModel):
    """智能编排输入待办"""

    id: int = Field(..., description="待办 ID")
    name: str = Field(..., description="待办名称")
    priority: TodoPriority = Field(..., description="优先级")
    due: datetime | None = Field(None, description="截止时间")
    duration: str | None = Field(None, description="预估时长，ISO 8601 Duration")


class ScheduleConstraint(BaseModel):
    """智能编排课程或日程约束"""

    weekday: int = Field(..., description="星期几，1=周一，7=周日")
    start_time: str = Field(..., description="约束开始时间，HH:MM")
    end_time: str = Field(..., description="约束结束时间，HH:MM")
    label: str | None = Field(None, description="约束标签")


class ScheduleSuggestRequest(BaseModel):
    """智能日程编排请求"""

    todos: list[ScheduleSuggestTodo] = Field(..., description="需要编排的待办列表")
    schedule_constraints: list[ScheduleConstraint] = Field(
        default_factory=list, description="不可安排任务的课程或日程约束"
    )
    planning_start: datetime | None = Field(None, description="编排开始时间")
    planning_end: datetime | None = Field(None, description="编排结束时间")
    daily_available_hours: int = Field(6, description="每日可用学习时长")


class ScheduleAlternative(BaseModel):
    """智能编排备选时段"""

    suggested_start: datetime = Field(..., description="建议开始时间")
    suggested_end: datetime = Field(..., description="建议结束时间")


class ScheduleSuggestion(BaseModel):
    """智能编排建议"""

    todo_id: int = Field(..., description="待办 ID")
    todo_name: str = Field(..., description="待办名称")
    suggested_start: datetime = Field(..., description="建议开始时间")
    suggested_end: datetime = Field(..., description="建议结束时间")
    reason: str = Field(..., description="建议理由")
    alternatives: list[ScheduleAlternative] = Field(
        default_factory=list, description="备选时段，最多 2 个"
    )


class ScheduleSuggestResponse(BaseModel):
    """智能日程编排响应"""

    suggestions: list[ScheduleSuggestion] = Field(..., description="编排建议列表")
    unscheduled_todos: list[int] = Field(..., description="无法安排的待办 ID 列表")
    planning_coverage_pct: float = Field(..., description="成功编排的待办百分比")


class ImportTodoFileResult(BaseModel):
    """单个文件导入处理结果"""

    file_name: str = Field(..., description="文件名")
    mime_type: str | None = Field(None, description="MIME 类型")
    size_bytes: int = Field(..., description="文件大小")
    status: Literal["success", "failed"] = Field(..., description="处理状态")
    extracted_count: int = Field(0, description="提取出的待办数量")
    error_code: str | None = Field(None, description="失败错误码")
    message: str | None = Field(None, description="处理说明")
    raw_text_preview: str | None = Field(None, description="文本预览")


class ImportedTodoTask(BaseModel):
    """从文件解析出的待确认任务"""

    task_title: str = Field(..., description="解析出的任务标题")
    priority: TodoPriority = Field(..., description="任务优先级")
    due: datetime | None = Field(None, description="截止时间")
    duration: str | None = Field(None, description="预估时长，ISO 8601 Duration")
    description: str | None = Field(None, description="补充描述")
    source_file: str = Field(..., description="来源文件名")
    source_file_index: int = Field(..., ge=0, description="来源文件在本次上传中的序号")
    source_text: str = Field(..., description="来源文本")
    confidence: float = Field(..., ge=0, le=1, description="解析置信度")


class ImportedCreatedTodo(BaseModel):
    """导入接口创建出的待办摘要"""

    id: int = Field(..., description="待办 ID")
    name: str = Field(..., description="待办标题")
    status: str = Field(..., description="待办状态")


class ImportTodosResponse(BaseModel):
    """文件导入待办响应"""

    file_results: list[ImportTodoFileResult] = Field(..., description="文件处理结果")
    extracted_tasks: list[ImportedTodoTask] = Field(..., description="待确认任务列表")
    created_todos: list[ImportedCreatedTodo] = Field(
        default_factory=list, description="已创建待办列表"
    )
    raw_text_preview: str = Field("", description="合并文本预览")
    processing_time_ms: int = Field(..., description="处理耗时，毫秒")


class AgentErrorResponse(BaseModel):
    """Agent 接口错误响应"""

    error_code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    detail: str | None = Field(None, description="错误详情")
