"""BrightToDo Agent 自研接口路由"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from lifetrace.core.dependencies import get_todo_service
from lifetrace.schemas.agent import (
    AgentParseTaskRequest,
    AgentParseTaskResponse,
    AgentTextPlanRequest,
    AttachmentPlanConfirmRequest,
    AttachmentPlanConfirmResponse,
    AttachmentPlanResponse,
    ImportTodosResponse,
    ScheduleSuggestRequest,
    ScheduleSuggestResponse,
)
from lifetrace.services.agent_attachment_plan_service import (
    AgentAttachmentPlanService,
    AttachmentPlanError,
)
from lifetrace.services.agent_import_service import (
    MAX_IMPORT_FILE_BYTES,
    MAX_IMPORT_FILE_COUNT,
    AgentImportFile,
    AgentImportService,
    ImportTodosError,
)
from lifetrace.services.agent_parse_service import AgentParseService
from lifetrace.services.schedule_suggest_service import (
    ScheduleSuggestError,
    ScheduleSuggestService,
)
from lifetrace.services.todo_service import TodoService

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


async def _read_import_files(files: list[UploadFile]) -> list[AgentImportFile]:
    """按接口限制读取上传文件，避免超大文件在校验前进入内存。"""
    if len(files) > MAX_IMPORT_FILE_COUNT:
        raise ImportTodosError(400, "TOO_MANY_FILES", "最多一次上传 5 个文件")

    import_files: list[AgentImportFile] = []
    for file in files:
        content = await file.read(MAX_IMPORT_FILE_BYTES + 1)
        if len(content) > MAX_IMPORT_FILE_BYTES:
            raise ImportTodosError(
                413,
                "FILE_TOO_LARGE",
                f"{file.filename or '未命名文件'} 超过 10MB 限制",
            )
        import_files.append(
            AgentImportFile(
                file_name=file.filename or "",
                mime_type=file.content_type,
                content=content,
            )
        )
    return import_files


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


@router.post("/text-plan", response_model=AttachmentPlanResponse)
async def text_plan(request: AgentTextPlanRequest):
    """基于自然语言生成待确认日程规划"""
    try:
        service = AgentAttachmentPlanService()
        return service.create_text_plan(
            prompt=request.prompt,
            reference_time=request.reference_time,
            planning_start=request.planning_start,
            planning_end=request.planning_end,
            daily_available_hours=request.daily_available_hours,
        )
    except AttachmentPlanError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.detail)


@router.post("/schedule-suggest", response_model=ScheduleSuggestResponse)
async def schedule_suggest(request: ScheduleSuggestRequest):
    """生成避开课程冲突的待办执行时段建议"""
    service = ScheduleSuggestService()
    try:
        return service.suggest(request)
    except ScheduleSuggestError as exc:
        status_code = 422 if exc.error_code == "NO_AVAILABLE_SLOTS" else 400
        return _error_response(status_code, exc.error_code, exc.message)


@router.post("/import-todos", response_model=ImportTodosResponse)
async def import_todos(
    files: list[UploadFile] = File(..., description="待解析文件列表"),
    reference_time: datetime | None = Form(None, description="相对时间解析基准"),
    create_todos: bool = Form(False, description="是否立即创建草稿待办"),
    todo_service: TodoService = Depends(get_todo_service),
):
    """从图片或文档中解析待确认待办"""
    service = AgentImportService()
    try:
        import_files = await _read_import_files(files)
        return service.import_files(
            files=import_files,
            reference_time=reference_time,
            create_todos=create_todos,
            todo_service=todo_service,
        )
    except ImportTodosError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.detail)


@router.post("/attachment-plan", response_model=AttachmentPlanResponse)
async def create_attachment_plan(
    files: list[UploadFile] = File(..., description="作为下一次对话附件提交的文件列表"),
    prompt: str = Form(..., description="用户确认后的规划 prompt"),
    reference_time: datetime | None = Form(None, description="相对时间解析基准"),
    conversation_id: str | None = Form(None, description="聊天会话 ID"),
    planning_start: datetime | None = Form(None, description="编排开始时间"),
    planning_end: datetime | None = Form(None, description="编排结束时间"),
    daily_available_hours: int | None = Form(None, description="每日可用学习时长"),
):
    """基于附件和用户确认 prompt 生成待确认日程规划。"""
    _ = conversation_id
    service = AgentAttachmentPlanService()
    try:
        import_files = await _read_import_files(files)
        return service.create_plan(
            files=import_files,
            prompt=prompt,
            reference_time=reference_time,
            planning_start=planning_start,
            planning_end=planning_end,
            daily_available_hours=daily_available_hours,
        )
    except (AttachmentPlanError, ImportTodosError) as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.detail)


@router.post(
    "/attachment-plan/{plan_id}/confirm",
    response_model=AttachmentPlanConfirmResponse,
)
async def confirm_attachment_plan(
    plan_id: str,
    request: AttachmentPlanConfirmRequest,
    todo_service: TodoService = Depends(get_todo_service),
):
    """确认附件规划并创建草稿待办，同时绑定来源附件。"""
    service = AgentAttachmentPlanService()
    try:
        return service.confirm_plan(
            plan_id=plan_id,
            proposed_todos=request.proposed_todos,
            create_mode=request.create_mode,
            parent_title=request.parent_title,
            parent_description=request.parent_description,
            todo_service=todo_service,
        )
    except AttachmentPlanError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.detail)


@router.delete("/attachment-plan/{plan_id}", status_code=204)
async def delete_attachment_plan(plan_id: str):
    """放弃附件规划并清理临时文件。"""
    service = AgentAttachmentPlanService()
    try:
        service.delete_plan(plan_id)
    except AttachmentPlanError as exc:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.detail)
    return None
