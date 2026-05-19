"""Proactive OCR module for detecting and processing WeChat/Feishu windows"""

from lifetrace.util.logging_config import get_logger
from lifetrace.util.settings import settings

from .service import get_proactive_ocr_service

__all__ = ["get_proactive_ocr_service"]


def execute_proactive_ocr_task():
    """
    执行主动OCR任务
    由调度器定期调用，检查配置并启动/停止服务
    """
    logger = get_logger()
    service = get_proactive_ocr_service()
    enabled = settings.get("jobs.proactive_ocr.enabled", False)

    # 如果配置启用但服务未运行，启动服务
    if enabled and not service.is_running:
        try:
            service.start()
            logger.info("ProactiveOCR: Task triggered service start")
        except Exception as e:
            logger.error(f"ProactiveOCR: Failed to start service: {e}", exc_info=True)
    # 如果配置禁用但服务正在运行，停止服务
    elif not enabled and service.is_running:
        try:
            service.stop()
            logger.info("ProactiveOCR: Task triggered service stop")
        except Exception as e:
            logger.error(f"ProactiveOCR: Failed to stop service: {e}", exc_info=True)
