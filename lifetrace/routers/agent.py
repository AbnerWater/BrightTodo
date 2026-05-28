"""BrightToDo Agent 自研接口路由"""

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from lifetrace.schemas.agent import (
    AgentParseTaskRequest,
    AgentParseTaskResponse,
    ScheduleSuggestRequest,
    ScheduleSuggestResponse,
)
from lifetrace.services.agent_parse_service import AgentParseService
from lifetrace.services.schedule_suggest_service import (
    ScheduleSuggestError,
    ScheduleSuggestService,
)

MAX_TASK_TEXT_LENGTH = 500


def _error_response(
    status_code: int, error_code: str, message: str, detail: str | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message, "detail": detail},
    )


class AgentValidationRoute(APIRoute):
    """将 Agent 入参校验错误转换为统一契约错误响应。"""

    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                return _error_response(
                    400,
                    "INVALID_INPUT",
                    "请求字段格式错误",
                    str(exc),
                )

        return custom_route_handler


router = APIRouter(prefix="/api/agent", tags=["agent"], route_class=AgentValidationRoute)


@router.post("/parse-task", response_model=AgentParseTaskResponse)
async def parse_task(request: AgentParseTaskRequest):
    """解析中文自然语言任务描述"""
    text = request.text.strip()
    if not text:
        return _error_response(400, "INVALID_INPUT", "任务描述不能为空")
    if len(text) > MAX_TASK_TEXT_LENGTH:
        return _error_response(400, "INVALID_INPUT", "任务描述不能超过 500 个字符")

    service = AgentParseService()
    return service.parse_task(text=text, reference_time=request.reference_time)


@router.post("/schedule-suggest", response_model=ScheduleSuggestResponse)
async def schedule_suggest(request: ScheduleSuggestRequest):
    """生成避开课程冲突的待办执行时段建议"""
    service = ScheduleSuggestService()
    try:
        return service.suggest(request)
    except ScheduleSuggestError as exc:
        status_code = 422 if exc.error_code == "NO_AVAILABLE_SLOTS" else 400
        return _error_response(status_code, exc.error_code, exc.message)
