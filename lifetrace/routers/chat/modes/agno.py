"""Agno 模式处理器（基于 Agno 框架的 Agent）。"""

import json
from pathlib import Path
from typing import Any

from fastapi.responses import StreamingResponse

from lifetrace.llm.agno_agent import (
    TOOL_EVENT_PREFIX,
    TOOL_EVENT_SUFFIX,
    AgnoAgentService,
)
from lifetrace.schemas.chat import ChatMessage
from lifetrace.services.chat_service import ChatService
from lifetrace.util.logging_config import get_logger

from ..helpers import (
    get_conversation_history,
    make_error_streaming_response,
    validate_workspace_path,
)

logger = get_logger()


def _strip_tool_events(
    chunk: str,
    pending: str,
) -> tuple[str, str, list[dict[str, Any]]]:
    """从流式 chunk 中剥离工具事件标记，返回纯内容、剩余未完成标记、解析出的事件列表。"""
    content = pending + chunk
    events: list[dict[str, Any]] = []

    while True:
        start_idx = content.find(TOOL_EVENT_PREFIX)
        if start_idx == -1:
            break

        end_idx = content.find(TOOL_EVENT_SUFFIX, start_idx + len(TOOL_EVENT_PREFIX))
        if end_idx == -1:
            # 工具事件未完整，保留到下次处理
            pending_chunk = content[start_idx:]
            return content[:start_idx], pending_chunk, events

        json_start = start_idx + len(TOOL_EVENT_PREFIX)
        json_str = content[json_start:end_idx]
        try:
            events.append(json.loads(json_str))
        except json.JSONDecodeError:
            logger.warning("[stream][agno] 工具事件 JSON 解析失败")

        content = content[:start_idx] + content[end_idx + len(TOOL_EVENT_SUFFIX) :]

    # 处理可能跨 chunk 的前缀残留（例如 '\n[TOO'）
    max_prefix_len = min(len(TOOL_EVENT_PREFIX) - 1, len(content))
    for length in range(max_prefix_len, 0, -1):
        if TOOL_EVENT_PREFIX.startswith(content[-length:]):
            return content[:-length], content[-length:], events

    return content, "", events


def _build_external_tools_config(
    external_tools: list[str],
    workspace_path: str | None,
    enable_file_delete: bool,
) -> dict[str, dict]:
    """构建外部工具配置

    Args:
        external_tools: 外部工具列表
        workspace_path: 工作区路径
        enable_file_delete: 是否允许删除文件

    Returns:
        外部工具配置字典
    """
    config: dict[str, dict] = {}
    if not workspace_path:
        return config

    # 需要 base_dir 的本地工具
    if "file" in external_tools:
        config["file"] = {"base_dir": workspace_path, "enable_delete": enable_file_delete}
    if "local_fs" in external_tools:
        config["local_fs"] = {"base_dir": workspace_path}
    if "shell" in external_tools:
        config["shell"] = {"base_dir": workspace_path}

    return config


def create_agno_streaming_response(
    message: ChatMessage,
    chat_service: ChatService,
    session_id: str,
    lang: str = "en",
) -> StreamingResponse:
    """处理 Agno 模式，使用 Agno 框架的 Agent 进行对话

    支持的外部工具：
        搜索类（无需配置）：
        - websearch: 通用网页搜索（自动选择后端）
        - hackernews: Hacker News 新闻

        本地类（需要 workspace_path）：
        - file: 文件操作（读写、搜索）
        - local_fs: 简化文件写入
        - shell: 命令行执行
        - sleep: 暂停执行
    """
    logger.info(f"[stream] 进入 Agno 模式, lang={lang}")

    external_tools = message.external_tools or []
    workspace_path = message.workspace_path

    # 本地类工具需要 workspace_path，如果未提供则使用用户 home 目录
    local_tools = {"file", "local_fs", "shell"}
    needs_workspace = bool(local_tools & set(external_tools))

    if needs_workspace and not workspace_path:
        # 使用用户 home 目录作为默认工作区
        workspace_path = str(Path.home())
        logger.info(f"[stream][agno] 未指定 workspace_path，使用默认值: {workspace_path}")

    # 如果提供了 workspace_path，验证其有效性
    if workspace_path:
        is_valid, validation_error = validate_workspace_path(workspace_path)
        if not is_valid:
            err = (
                f"工作区验证失败: {validation_error}"
                if lang == "zh"
                else f"Workspace validation failed: {validation_error}"
            )
            return make_error_streaming_response(err, session_id)

    # 构建外部工具配置
    external_tools_config = _build_external_tools_config(
        external_tools, workspace_path, message.enable_file_delete
    )

    logger.info(
        f"[stream][agno] selected_tools={message.selected_tools}, external_tools={external_tools}, "
        f"workspace_path={workspace_path}"
    )

    # 获取用户真正的输入（用于保存和过滤对话历史）
    user_input_for_storage = message.get_user_input_for_storage()

    # 保存用户消息
    chat_service.add_message(
        session_id=session_id,
        role="user",
        content=user_input_for_storage,
    )

    # 创建 Agno Agent 服务
    agno_service = AgnoAgentService(
        lang=lang,
        selected_tools=message.selected_tools,
        external_tools=external_tools if external_tools else None,
        external_tools_config=external_tools_config if external_tools_config else None,
    )

    # 获取对话历史
    conversation_history = get_conversation_history(
        chat_service, session_id, user_input_for_storage
    )

    def agno_token_generator():
        storage_chunks: list[str] = []
        tool_events: list[dict[str, Any]] = []
        pending_tool_chunk = ""
        try:
            for chunk in agno_service.stream_response(
                message=message.message,
                conversation_history=conversation_history,
                session_id=session_id,
            ):
                yield chunk
                cleaned, pending_tool_chunk, parsed_events = _strip_tool_events(
                    chunk, pending_tool_chunk
                )
                if cleaned:
                    storage_chunks.append(cleaned)
                if parsed_events:
                    tool_events.extend(parsed_events)

            # 丢弃未完成的工具事件残片，避免写入历史
            storage_content = "".join(storage_chunks).strip()
            metadata = (
                json.dumps({"tool_events": tool_events}, ensure_ascii=False)
                if tool_events
                else None
            )

            if storage_content or tool_events:
                chat_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=storage_content,
                    metadata=metadata,
                )
                logger.info("[stream][agno] 消息已保存到数据库")
        except Exception as e:
            logger.error(f"[stream][agno] 生成失败: {e}")
            yield f"Agno Agent 处理失败: {e!s}"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Session-Id": session_id,
    }
    return StreamingResponse(
        agno_token_generator(), media_type="text/plain; charset=utf-8", headers=headers
    )
