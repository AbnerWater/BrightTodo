"""
Proactive OCR Service
主动检测并处理 WeChat/Feishu 窗口的 OCR 服务
"""

import hashlib
import sys
import threading
import time
from functools import lru_cache
from typing import Any

from PIL import Image

from lifetrace.llm.todo_extraction_service import todo_extraction_service
from lifetrace.storage import ocr_mgr, screenshot_mgr
from lifetrace.util.logging_config import get_logger
from lifetrace.util.path_utils import get_screenshots_dir
from lifetrace.util.settings import settings
from lifetrace.util.utils import ensure_dir

from .capture import get_capture
from .models import AppType
from .ocr_engine import get_ocr_engine
from .roi import get_roi_extractor
from .router import get_router

logger = get_logger()


class ProactiveOCRService:
    """Proactive OCR 服务"""

    def __init__(self):
        self.is_running = False
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # 从配置读取参数
        self.interval = settings.get("jobs.proactive_ocr.interval", 1.0)
        self.use_roi = settings.get("jobs.proactive_ocr.use_roi", True)
        self.resize_max_side = settings.get("jobs.proactive_ocr.resize_max_side", 800)
        self.det_limit_side_len = settings.get("jobs.proactive_ocr.det_limit_side_len", 640)
        self.min_confidence = settings.get("jobs.proactive_ocr.min_confidence", 0.8)

        # 初始化组件
        self.router = get_router()
        self.capture = get_capture(fps=1.0 / self.interval)
        self.roi_extractor = get_roi_extractor()
        self.ocr_engine = get_ocr_engine(
            det_limit_side_len=self.det_limit_side_len,
            resize_max_side=self.resize_max_side,
        )

        # 统计信息
        self.stats = {
            "total_captures": 0,
            "successful_ocrs": 0,
            "failed_captures": 0,
            "last_capture_time": None,
        }

        logger.info(
            f"ProactiveOCR: Service initialized (interval={self.interval}s, "
            f"use_roi={self.use_roi}, resize_max_side={self.resize_max_side})"
        )

    def start(self):
        """启动监控服务"""
        if self.is_running:
            logger.warning("ProactiveOCR: Service is already running")
            return

        self.is_running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="ProactiveOCRMonitor"
        )
        self._monitor_thread.start()
        logger.info(
            f"ProactiveOCR: Service started (interval={self.interval}s, "
            f"apps=['wechat', 'feishu'], platform={sys.platform})"
        )

    def stop(self):
        """停止监控服务"""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)

        logger.info("ProactiveOCR: Service stopped")

    def _monitor_loop(self):
        """监控循环"""
        while self.is_running and not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"ProactiveOCR: Error in monitor loop: {e}", exc_info=True)

            # 等待间隔时间
            self._stop_event.wait(self.interval)

    def run_once(self) -> dict[str, Any] | None:
        """
        执行一次检测和处理

        Returns:
            处理结果字典，如果未检测到目标窗口返回 None
        """
        # 获取前台窗口（跨平台）
        window = self.capture.get_foreground_window()
        if not window:
            return None

        # 检查是否为目标应用
        app_type, _reason = self.router.identify_app(window)
        if app_type == AppType.UNKNOWN:
            return None

        logger.info(
            f"ProactiveOCR: Detected foreground window: hwnd={window.hwnd}, "
            f'app={app_type.value}, title="{window.title[:50]}"'
        )

        # 检查窗口是否最小化
        if window.is_minimized:
            logger.debug("ProactiveOCR: Window is minimized, skipping capture")
            return None

        logger.debug(f"ProactiveOCR: Window size: {window.rect.width}x{window.rect.height}")

        # 捕获窗口截图
        timings = {}
        t0 = time.perf_counter()
        frame = self.capture.capture_window(window)
        timings["capture"] = (time.perf_counter() - t0) * 1000

        if frame is None:
            logger.error("ProactiveOCR: Capture window failed")
            self.stats["failed_captures"] += 1
            return None

        logger.info(
            f"ProactiveOCR: Capture completed in {timings['capture']:.0f}ms "
            f"({frame.width}x{frame.height})"
        )

        # ROI 裁切
        image_to_ocr = frame.data
        theme = None

        if self.use_roi:
            t0 = time.perf_counter()
            roi_result = self.roi_extractor.extract_with_details(frame.data, app_type)
            timings["roi"] = (time.perf_counter() - t0) * 1000

            if roi_result:
                image_to_ocr = roi_result.image
                theme = roi_result.theme
                logger.info(
                    f"ProactiveOCR: ROI extracted - theme={theme}, "
                    f"region={roi_result.width}x{roi_result.height} "
                    f"(from x={roi_result.x}), time={timings['roi']:.1f}ms"
                )

        # 执行 OCR 识别
        logger.debug("ProactiveOCR: Starting OCR recognition...")
        t0 = time.perf_counter()
        ocr_result = self.ocr_engine.ocr(image_to_ocr)
        timings["ocr_total"] = (time.perf_counter() - t0) * 1000

        logger.info(
            f"ProactiveOCR: OCR completed in {timings['ocr_total']:.0f}ms "
            f"(det={ocr_result.det_time_ms:.0f}ms, rec={ocr_result.rec_time_ms:.0f}ms)"
        )

        # 过滤低置信度结果
        valid_lines = [line for line in ocr_result.lines if line.score >= self.min_confidence]
        logger.info(
            f"ProactiveOCR: Found {len(valid_lines)} text blocks "
            f"(confidence >={self.min_confidence})"
        )

        if len(valid_lines) > 0:
            # 提取文本内容
            text_content = "\n".join([line.text for line in valid_lines])
            logger.debug(f"ProactiveOCR: Text preview: {text_content[:100]}...")

            # 保存截图和 OCR 结果到数据库
            screenshot_id = self._save_to_database(
                frame, window, app_type, text_content, ocr_result, valid_lines
            )

            if screenshot_id:
                self.stats["successful_ocrs"] += 1
                logger.info(
                    f"ProactiveOCR: Saved screenshot_id={screenshot_id}, "
                    f"ocr_result with {len(valid_lines)} lines"
                )

        self.stats["total_captures"] += 1
        self.stats["last_capture_time"] = time.time()

        total_time = sum(timings.values())
        logger.debug(f"ProactiveOCR: Total time: {total_time:.0f}ms")

        return {
            "app_type": app_type.value,
            "window_title": window.title,
            "text_lines": len(valid_lines),
            "timings": timings,
        }

    def _save_to_database(
        self,
        frame,
        window,
        app_type: AppType,
        text_content: str,
        ocr_result,
        valid_lines,
    ) -> int | None:
        """保存截图和 OCR 结果到数据库"""
        try:
            # 保存图像文件
            screenshots_dir = get_screenshots_dir()
            ensure_dir(str(screenshots_dir))

            # 生成文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"proactive_{app_type.value}_{timestamp}_{frame.capture_id}.png"
            file_path = str(screenshots_dir / filename)

            # 保存图像（PIL Image）
            img = Image.fromarray(frame.data)
            img.save(file_path)

            # 计算文件哈希
            with open(file_path, "rb") as f:
                file_hash = hashlib.md5(f.read(), usedforsecurity=False).hexdigest()

            # 添加截图记录
            screenshot_id = screenshot_mgr.add_screenshot(
                file_path=file_path,
                file_hash=file_hash,
                width=frame.width,
                height=frame.height,
                metadata={
                    "screen_id": 0,
                    "app_name": app_type.value,
                    "window_title": window.title,
                    "proactive_ocr": True,
                    "hwnd": window.hwnd,
                    "pid": window.pid,
                },
            )

            if not screenshot_id:
                logger.error("ProactiveOCR: Failed to save screenshot to database")
                return None

            # 计算平均置信度
            avg_confidence = (
                sum(line.score for line in valid_lines) / len(valid_lines) if valid_lines else 0.0
            )

            # 添加 OCR 结果
            ocr_result_id = ocr_mgr.add_ocr_result(
                screenshot_id=screenshot_id,
                text_content=text_content,
                confidence=avg_confidence,
                language="ch",
                processing_time=ocr_result.latency_ms / 1000.0,
            )

            if ocr_result_id:
                logger.debug(f"ProactiveOCR: Saved OCR result_id={ocr_result_id}")
                # 可选：自动触发基于 OCR 文本的待办提取
                try:
                    auto_extract = settings.get(
                        "jobs.proactive_ocr.params.auto_extract_todos", False
                    )
                    min_text_length = settings.get(
                        "jobs.proactive_ocr.params.min_text_length",
                        10,
                    )
                    if auto_extract and len((text_content or "").strip()) >= min_text_length:
                        logger.info(
                            "ProactiveOCR: auto_extract_todos 开启，开始基于 OCR 文本提取待办"
                        )
                        # 我们仅调用提取逻辑，不在此处直接写 todo，结果由上层或日志查看
                        extraction_result = todo_extraction_service.extract_todos_from_ocr_text(
                            ocr_result_id=ocr_result_id,
                            text_content=text_content,
                            app_name=app_type.value,
                            window_title=window.title,
                        )

                        if extraction_result.get("skipped"):
                            logger.info(
                                "ProactiveOCR: OCR 文本待办提取已跳过 - "
                                f"reason={extraction_result.get('reason')}, "
                                f"ocr_result_id={extraction_result.get('ocr_result_id')}"
                            )
                        else:
                            todos_count = len(extraction_result.get("todos") or [])
                            error_message = extraction_result.get("error_message")
                            created_count = extraction_result.get("created_count")
                            if error_message:
                                logger.warning(
                                    "ProactiveOCR: OCR 文本待办提取完成但存在错误 - "
                                    f"error={error_message}, "
                                    f"ocr_result_id={extraction_result.get('ocr_result_id')}, "
                                    f"todos_count={todos_count}, "
                                    f"created_count={created_count}"
                                )
                            else:
                                logger.info(
                                    "ProactiveOCR: OCR 文本待办提取完成 - "
                                    f"ocr_result_id={extraction_result.get('ocr_result_id')}, "
                                    f"todos_count={todos_count}, "
                                    f"created_count={created_count}"
                                )
                except Exception as e:
                    logger.error(f"ProactiveOCR: 自动待办提取失败（已忽略）: {e}", exc_info=True)

                return screenshot_id

            return None

        except Exception as e:
            logger.error(f"ProactiveOCR: Failed to save to database: {e}", exc_info=True)
            return None

    def get_status(self) -> dict[str, Any]:
        """获取服务状态"""
        return {
            "is_running": self.is_running,
            "interval": self.interval,
            "use_roi": self.use_roi,
            "platform": sys.platform,
            "stats": self.stats.copy(),
        }


# 单例实例


@lru_cache(maxsize=1)
def get_proactive_ocr_service() -> ProactiveOCRService:
    """获取 Proactive OCR 服务单例"""
    return ProactiveOCRService()
