"""
OCR引擎封装模块
基于 RapidOCR (ONNX Runtime) 的轻量级OCR实现
"""

import re
import time

import numpy as np

from lifetrace.util.logging_config import get_logger

from .models import BBox, OcrLine, OcrRawResult

logger = get_logger()

try:
    from rapidocr_onnxruntime import RapidOCR

    RAPIDOCR_AVAILABLE = True
except ImportError:
    RapidOCR = None
    RAPIDOCR_AVAILABLE = False
    logger.error("rapidocr-onnxruntime not available")

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False
    logger.warning("opencv-python not available, image resizing disabled")


class OcrEngine:
    """OCR引擎封装类"""

    def __init__(
        self,
        det_limit_side_len: int = 640,
        det_limit_type: str = "max",
        rec_batch_num: int = 1,
        use_gpu: bool = False,
        resize_max_side: int = 0,  # 预缩放最大边长，0表示不缩放
    ):
        """
        初始化OCR引擎

        Args:
            det_limit_side_len: 检测输入图像的边长限制，减小可降低内存占用
            det_limit_type: 边长限制类型，"max"限制最大边，"min"限制最小边
            rec_batch_num: 识别批次大小，减小可降低内存峰值
            use_gpu: 是否使用GPU（需要安装CUDA版本onnxruntime）
            resize_max_side: 输入图像预缩放的最大边长，0表示不缩放
        """
        if not RAPIDOCR_AVAILABLE:
            raise ImportError(
                "rapidocr-onnxruntime not available. Install with: uv add rapidocr-onnxruntime"
            )
        if RapidOCR is None:
            raise ImportError("RapidOCR backend is not available")

        # 配置参数
        init_params = {
            "det_limit_side_len": det_limit_side_len,
            "det_limit_type": det_limit_type,
            "rec_batch_num": rec_batch_num,
        }

        # GPU配置
        if use_gpu:
            init_params["use_cuda"] = True

        self.engine = RapidOCR(**init_params)

        self.det_limit_side_len = det_limit_side_len
        self.det_limit_type = det_limit_type
        self.rec_batch_num = rec_batch_num
        self.resize_max_side = resize_max_side

    def _resize_image(self, image: np.ndarray, max_side: int) -> tuple:
        """
        等比例缩小图像

        Returns:
            (缩放后图像, 缩放比例)
        """
        if not CV2_AVAILABLE:
            logger.warning("OpenCV not available, skipping image resize")
            return image, 1.0
        if cv2 is None:
            logger.warning("OpenCV not available, skipping image resize")
            return image, 1.0

        cv2_local = cv2

        h, w = image.shape[:2]
        max_dim = max(h, w)

        if max_dim <= max_side:
            return image, 1.0

        scale = max_side / max_dim
        new_w = int(w * scale)
        new_h = int(h * scale)

        resized = cv2_local.resize(image, (new_w, new_h), interpolation=cv2_local.INTER_AREA)
        return resized, scale

    def ocr(self, image: np.ndarray) -> OcrRawResult:
        """
        对图像执行OCR识别

        Args:
            image: 输入图像，numpy数组，RGB格式

        Returns:
            OcrRawResult: OCR识别结果
        """
        start_time = time.time()

        # 预缩放图像
        scale = 1.0
        if self.resize_max_side > 0:
            image, scale = self._resize_image(image, self.resize_max_side)

        # 执行OCR
        result, elapse = self.engine(image)

        latency_ms = (time.time() - start_time) * 1000

        # 解析 elapse 时间
        det_time_ms = 0.0
        rec_time_ms = 0.0
        cls_time_ms = 0.0

        if elapse:
            # elapse 可能是字符串或字典
            if isinstance(elapse, str):
                # 解析字符串格式
                det_match = re.search(r"det[:\s]+(\d+\.?\d*)s?", elapse)
                rec_match = re.search(r"rec[:\s]+(\d+\.?\d*)s?", elapse)
                cls_match = re.search(r"cls[:\s]+(\d+\.?\d*)s?", elapse)

                if det_match:
                    det_time_ms = float(det_match.group(1)) * 1000
                if rec_match:
                    rec_time_ms = float(rec_match.group(1)) * 1000
                if cls_match:
                    cls_time_ms = float(cls_match.group(1)) * 1000
            elif isinstance(elapse, dict):
                det_time_ms = elapse.get("det", 0) * 1000
                rec_time_ms = elapse.get("rec", 0) * 1000
                cls_time_ms = elapse.get("cls", 0) * 1000

        # 解析结果
        lines = []
        if result:
            for item in result:
                # item格式: [bbox, text, score]
                # bbox格式: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                bbox_points = item[0]
                text = item[1]
                score = item[2]

                # 转换bbox为BBox格式（考虑缩放）
                x_coords = [float(p[0]) for p in bbox_points]
                y_coords = [float(p[1]) for p in bbox_points]
                x_min = int(min(x_coords) / scale)
                y_min = int(min(y_coords) / scale)
                x_max = int(max(x_coords) / scale)
                y_max = int(max(y_coords) / scale)

                bbox = BBox(
                    x=x_min,
                    y=y_min,
                    width=x_max - x_min,
                    height=y_max - y_min,
                )

                lines.append(OcrLine(text=text, score=float(score), bbox_px=bbox))

        return OcrRawResult(
            lines=lines,
            engine="rapidocr-onnxruntime",
            latency_ms=latency_ms,
            det_time_ms=det_time_ms,
            rec_time_ms=rec_time_ms,
            cls_time_ms=cls_time_ms,
            model_version="1.4.4",
            device="cpu",
        )

    def ocr_simple(self, image: np.ndarray) -> list[tuple[str, float]]:
        """
        简化版OCR，只返回文本和置信度

        Args:
            image: 输入图像

        Returns:
            [(text, score), ...] 文本和置信度列表
        """
        result = self.ocr(image)
        return [(line.text, line.score) for line in result.lines]


# 单例实例
_engine_state: dict[str, OcrEngine | None] = {"instance": None}


def get_ocr_engine(
    det_limit_side_len: int = 640,
    det_limit_type: str = "max",
    rec_batch_num: int = 1,
    resize_max_side: int = 0,
) -> OcrEngine:
    """获取OCR引擎单例"""
    instance = _engine_state["instance"]
    if instance is None:
        instance = OcrEngine(
            det_limit_side_len=det_limit_side_len,
            det_limit_type=det_limit_type,
            rec_batch_num=rec_batch_num,
            resize_max_side=resize_max_side,
        )
        _engine_state["instance"] = instance
    return instance
