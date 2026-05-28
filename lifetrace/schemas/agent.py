"""BrightToDo Agent 自研接口模型"""

from datetime import datetime

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


class AgentErrorResponse(BaseModel):
    """Agent 接口错误响应"""

    error_code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误信息")
    detail: str | None = Field(None, description="错误详情")
