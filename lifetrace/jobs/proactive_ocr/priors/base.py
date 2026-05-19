"""
先验配置基类
定义应用先验的通用接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class ThemeConfig:
    """主题配置"""

    name: str  # 主题名称: "dark" / "light"
    chat_bg_color: tuple[int, int, int]  # 聊天区域背景色 RGB
    color_tolerance: int = 5  # 颜色容差


@dataclass
class ROIResult:
    """ROI 提取结果"""

    image: np.ndarray  # 裁切后的图像
    x: int  # 左边界 x 坐标
    y: int  # 上边界 y 坐标
    width: int  # 宽度
    height: int  # 高度
    theme: str  # 检测到的主题


class AppPrior(ABC):
    """应用先验基类"""

    @property
    @abstractmethod
    def app_name(self) -> str:
        """应用名称"""
        pass

    @property
    @abstractmethod
    def themes(self) -> list[ThemeConfig]:
        """支持的主题列表"""
        pass

    def detect_theme(self, image: np.ndarray) -> ThemeConfig | None:
        """
        检测当前图像的主题

        Args:
            image: 窗口截图 (RGB)

        Returns:
            检测到的主题配置，未匹配返回 None
        """
        h, w = image.shape[:2]

        # 在底部区域采样检测主题
        sample_y = min(h - 100, h - 1)
        sample_x = w - 50  # 右下角通常是纯背景

        if sample_y < 0 or sample_x < 0:
            return self.themes[0] if self.themes else None

        # 取采样点颜色
        pixel = image[sample_y, sample_x].astype(np.float32)

        # 匹配主题
        for theme in self.themes:
            target = np.array(theme.chat_bg_color, dtype=np.float32)
            if np.all(np.abs(pixel - target) <= theme.color_tolerance):
                return theme

        # 默认返回第一个主题
        return self.themes[0] if self.themes else None

    @abstractmethod
    def extract_chat_roi(self, image: np.ndarray) -> ROIResult:
        """
        提取聊天区域 ROI

        Args:
            image: 完整窗口截图 (RGB)

        Returns:
            ROI 提取结果
        """
        pass

    def _find_bg_left_edge(
        self,
        image: np.ndarray,
        bg_color: tuple[int, int, int],
        tolerance: int,
        sample_heights: list[int],
    ) -> int | None:
        """
        找到背景色区域的左边界

        Args:
            image: 图像
            bg_color: 目标背景色
            tolerance: 颜色容差
            sample_heights: 采样高度列表

        Returns:
            左边界 x 坐标
        """
        h, _ = image.shape[:2]
        target = np.array(bg_color, dtype=np.float32)

        # 过滤有效采样高度
        valid_heights = [y for y in sample_heights if 0 < y < h]
        if not valid_heights:
            valid_heights = [h // 2]

        left_edges = []

        for y in valid_heights:
            row = image[y, :, :]
            left_x = self._scan_row_left_edge(row, target, tolerance)
            if left_x is not None:
                left_edges.append(left_x)

        return min(left_edges) if left_edges else None

    def _scan_row_left_edge(
        self, row: np.ndarray, target_color: np.ndarray, tolerance: int
    ) -> int | None:
        """从右向左扫描一行，找到目标颜色区域的左边界"""
        w = row.shape[0]

        in_target_region = False
        last_target_x = None

        for x in range(w - 1, -1, -1):
            pixel = row[x].astype(np.float32)
            is_target = np.all(np.abs(pixel - target_color) <= tolerance)

            if is_target:
                in_target_region = True
                last_target_x = x
            elif in_target_region:
                return last_target_x

        if in_target_region:
            return 0

        return None
