"""
数据模型定义
定义系统中使用的核心数据结构
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AppType(Enum):
    """应用类型枚举"""

    WECHAT = "wechat"
    FEISHU = "feishu"
    UNKNOWN = "unknown"


@dataclass
class BBox:
    """边界框"""

    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple:
        """转换为元组格式 (x1, y1, x2, y2)"""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @classmethod
    def from_tuple(cls, t: tuple) -> "BBox":
        """从元组创建 (x1, y1, x2, y2)"""
        return cls(x=t[0], y=t[1], width=t[2] - t[0], height=t[3] - t[1])


@dataclass
class WindowMeta:
    """窗口元数据"""

    hwnd: int  # 窗口句柄
    title: str  # 窗口标题
    process_name: str  # 进程名
    pid: int  # 进程ID
    rect: BBox  # 窗口位置和大小
    is_visible: bool = True  # 是否可见
    is_minimized: bool = False  # 是否最小化


@dataclass
class ImageFrame:
    """图像帧"""

    data: Any  # 图像数据 (numpy array)
    width: int
    height: int
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    capture_id: str = ""


@dataclass
class FrameEvent:
    """帧事件"""

    frame: ImageFrame
    window_meta: WindowMeta
    capture_id: str


@dataclass
class RoutedFrame:
    """路由后的帧"""

    app_id: AppType
    frame: ImageFrame
    window_meta: WindowMeta
    route_reason: str = ""


@dataclass
class OcrLine:
    """OCR识别的单行文本"""

    text: str
    score: float
    bbox_px: BBox


@dataclass
class OcrRawResult:
    """OCR原始结果"""

    lines: list[OcrLine]
    engine: str = "rapidocr"
    latency_ms: float = 0
    det_time_ms: float = 0  # 检测耗时
    rec_time_ms: float = 0  # 识别耗时
    cls_time_ms: float = 0  # 方向分类耗时
    model_version: str = "1.0"
    device: str = "cpu"
