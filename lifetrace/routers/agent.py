"""BrightToDo Agent 自研接口路由"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from lifetrace.schemas.agent import AgentParseTaskRequest, AgentParseTaskResponse
from lifetrace.services.agent_parse_service import AgentParseService

router = APIRouter(prefix="/api/agent", tags=["agent"])
MAX_TASK_TEXT_LENGTH = 500


def _error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message, "detail": None},
    )


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
