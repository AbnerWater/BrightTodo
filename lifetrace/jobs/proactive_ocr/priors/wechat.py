"""
微信先验配置
"""

import numpy as np

from .base import AppPrior, ROIResult, ThemeConfig


class WeChatPrior(AppPrior):
    """微信应用先验"""

    @property
    def app_name(self) -> str:
        return "wechat"

    @property
    def themes(self) -> list[ThemeConfig]:
        return [
            ThemeConfig(
                name="dark",
                chat_bg_color=(25, 25, 25),
                color_tolerance=5,
            ),
            ThemeConfig(
                name="light",
                chat_bg_color=(237, 237, 237),
                color_tolerance=5,
            ),
        ]

    def extract_chat_roi(self, image: np.ndarray) -> ROIResult:
        """
        提取微信聊天区域

        微信布局：左侧联系人列表 + 右侧聊天区域
        聊天区域背景色：深色(25,25,25) 或 亮色(237,237,237)
        """
        h, w = image.shape[:2]

        # 1. 先检测当前主题（在右下角采样）
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

        # 兜底：使用固定比例
        if split_x is None:
            split_x = int(w * 0.35)

        # 裁切
        chat_region = image[:, split_x:, :]

        return ROIResult(
            image=chat_region,
            x=split_x,
            y=0,
            width=w - split_x,
            height=h,
            theme=theme_name,
        )
