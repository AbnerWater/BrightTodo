"""
ROI (Region of Interest) 提取模块
使用应用先验配置裁切感兴趣的区域
"""

from functools import lru_cache

import numpy as np

from .models import AppType, BBox
from .priors import get_prior
from .priors.base import ROIResult


class ROIExtractor:
    """ROI 提取器 - 使用先验配置"""

    def extract_chat_region(self, image: np.ndarray, app_type: AppType) -> tuple[np.ndarray, BBox]:
        """
        提取聊天区域

        Args:
            image: 完整窗口图像 (RGB)
            app_type: 应用类型

        Returns:
            (裁切后的图像, 裁切区域的BBox)
        """
        # 获取应用先验
        prior = get_prior(app_type)

        if prior is None:
            # 无先验配置，返回原图
            h, w = image.shape[:2]
            return image, BBox(x=0, y=0, width=w, height=h)

        # 使用先验提取 ROI（每次都会动态检测主题）
        result = prior.extract_chat_roi(image)

        bbox = BBox(
            x=result.x,
            y=result.y,
            width=result.width,
            height=result.height,
        )

        return result.image, bbox

    def extract_with_details(self, image: np.ndarray, app_type: AppType) -> ROIResult | None:
        """
        提取 ROI 并返回详细信息（包括检测到的主题）

        Args:
            image: 完整窗口图像 (RGB)
            app_type: 应用类型

        Returns:
            ROI 提取结果，包含主题信息
        """
        prior = get_prior(app_type)

        if prior is None:
            return None

        return prior.extract_chat_roi(image)


# 单例实例


@lru_cache(maxsize=1)
def get_roi_extractor() -> ROIExtractor:
    """获取 ROI 提取器单例"""
    return ROIExtractor()
