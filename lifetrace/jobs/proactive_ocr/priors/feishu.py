"""
飞书先验配置
"""

import numpy as np

from .base import AppPrior, ROIResult, ThemeConfig


class FeishuPrior(AppPrior):
    """飞书应用先验"""

    @property
    def app_name(self) -> str:
        return "feishu"

    @property
    def themes(self) -> list[ThemeConfig]:
        return [
            ThemeConfig(
                name="light",
                chat_bg_color=(255, 255, 255),
                color_tolerance=10,
            ),
            ThemeConfig(
                name="dark",
                chat_bg_color=(30, 30, 30),  # 估计值，需要根据实际调整
                color_tolerance=10,
            ),
        ]

    def extract_chat_roi(self, image: np.ndarray) -> ROIResult:
        """
        提取飞书聊天区域

        飞书布局类似微信：左侧列表 + 右侧聊天
        """
        h, w = image.shape[:2]

        # 1. 先检测当前主题
        theme = self.detect_theme(image)
        theme_name = theme.name if theme else "unknown"

        # 2. 只用当前主题的背景色检测 ROI
        split_x = None
        if theme:
            sample_heights = [h - 80, h - 120, h - 160]
            split_x = self._find_bg_left_edge(
                image,
                bg_color=theme.chat_bg_color,
                tolerance=theme.color_tolerance,
                sample_heights=sample_heights,
            )

        # 兜底
        if split_x is None:
            split_x = int(w * 0.35)

        chat_region = image[:, split_x:, :]

        return ROIResult(
            image=chat_region,
            x=split_x,
            y=0,
            width=w - split_x,
            height=h,
            theme=theme_name,
        )
