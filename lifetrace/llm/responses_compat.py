"""Responses API 兼容辅助函数。"""

from __future__ import annotations

from typing import Any

RESPONSES_API_MODE = "responses"
CHAT_COMPLETIONS_FALLBACK_MODE = "chat_completions_fallback"
HTTP_NOT_FOUND = 404

_UNSUPPORTED_ERROR_MARKERS = (
    "404",
    "not found",
    "unknown endpoint",
    "unsupported endpoint",
    "endpoint not supported",
    "no route",
    "/v1/responses",
)


def build_responses_input(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, str]]]:
    """把 Chat Completions 消息拆成 Responses 的 instructions 与 input。"""
    instructions: list[str] = []
    input_items: list[dict[str, str]] = []

    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        content = message.get("content")
        if content is None:
            continue

        content_text = str(content)
        if role == "system":
            instructions.append(content_text)
            continue

        input_items.append(
            {
                "role": role if role in {"user", "assistant"} else "user",
                "content": content_text,
            }
        )

    if not input_items:
        input_items.append({"role": "user", "content": ""})

    instruction_text = "\n\n".join(item for item in instructions if item.strip())
    return instruction_text or None, input_items


def extract_responses_text(response: Any) -> str:
    """从 Responses 响应中提取文本，兼容 output_text 和 output 文本块。"""
    output_text = _read_field(response, "output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    text_parts: list[str] = []
    output_items = _read_field(response, "output") or []
    if not isinstance(output_items, (list, tuple)):
        output_items = [output_items]

    for output_item in output_items:
        content_items = _read_field(output_item, "content") or []
        if not isinstance(content_items, (list, tuple)):
            content_items = [content_items]
        text_parts.extend(
            text
            for content_item in content_items
            if (text := _extract_content_text(content_item))
        )

    return "".join(text_parts)


def is_responses_unsupported_error(exc: Exception) -> bool:
    """判断异常是否表示兼容服务不支持 /v1/responses。"""
    status_code = getattr(exc, "status_code", None)
    if status_code == HTTP_NOT_FOUND:
        return True

    detail = f"{exc.__class__.__name__}: {exc}".lower()
    if isinstance(exc, AttributeError) and "responses" in detail:
        return True
    return any(marker in detail for marker in _UNSUPPORTED_ERROR_MARKERS)


def _extract_content_text(content_item: Any) -> str | None:
    text = _read_field(content_item, "text")
    if isinstance(text, str):
        return text
    if isinstance(text, dict):
        value = text.get("value")
        if isinstance(value, str):
            return value
    return None


def _read_field(item: Any, field_name: str) -> Any:
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)
