"""Proactive OCR 路由"""

import sys

from fastapi import APIRouter, HTTPException

from lifetrace.jobs.proactive_ocr.service import get_proactive_ocr_service
from lifetrace.util.logging_config import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/proactive-ocr", tags=["proactive-ocr"])


@router.post("/start")
async def start_proactive_ocr():
    """启动主动OCR监控服务"""
    try:
        service = get_proactive_ocr_service()
        service.start()
        return {
            "success": True,
            "message": "Proactive OCR service started",
            "status": service.get_status(),
        }
    except Exception as e:
        logger.error(f"Failed to start proactive OCR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start service: {e!s}") from e


@router.post("/stop")
async def stop_proactive_ocr():
    """停止主动OCR监控服务"""
    try:
        service = get_proactive_ocr_service()
        service.stop()
        return {
            "success": True,
            "message": "Proactive OCR service stopped",
            "status": service.get_status(),
        }
    except Exception as e:
        logger.error(f"Failed to stop proactive OCR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop service: {e!s}") from e


@router.post("/capture")
async def capture_once():
    """手动触发一次捕获和OCR处理"""
    try:
        service = get_proactive_ocr_service()
        result = service.run_once()

        if result is None:
            return {
                "success": False,
                "message": "No target window detected or capture failed",
            }

        return {
            "success": True,
            "message": "Capture and OCR completed",
            "result": result,
        }
    except Exception as e:
        logger.error(f"Failed to capture: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Capture failed: {e!s}") from e


@router.get("/status")
async def get_proactive_ocr_status():
    """获取主动OCR服务状态"""
    try:
        service = get_proactive_ocr_service()
        status = service.get_status()
        return {
            "success": True,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Failed to get status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e!s}") from e


@router.get("/health")
async def health_check():
    """健康检查"""
    service = get_proactive_ocr_service()
    status = service.get_status()

    return {
        "status": "ok",
        "platform": sys.platform,
        "windows_available": sys.platform == "win32",
        "service_running": status["is_running"],
    }
