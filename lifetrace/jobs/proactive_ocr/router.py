"""
应用路由模块
识别窗口是否为微信/飞书
"""

from functools import lru_cache

from .models import AppType, FrameEvent, RoutedFrame, WindowMeta

# 微信相关进程名和窗口标题关键词（跨平台）
WECHAT_PROCESS_NAMES = [
    # Windows
    "weixin.exe",  # 微信主进程 (新版)
    "wechat.exe",  # 微信主进程 (旧版)
    "wechatappex.exe",  # 微信小程序
    "wechatbrowser.exe",  # 微信内置浏览器
    # macOS
    "wechat",  # macOS 应用名
    "微信",  # macOS 可能返回中文名
    # Linux
    "wechat",
    "electronic-wechat",
]

WECHAT_TITLE_KEYWORDS = [
    "微信",
    "wechat",
]

# 飞书相关进程名和窗口标题关键词（跨平台）
FEISHU_PROCESS_NAMES = [
    # Windows
    "feishu.exe",
    "lark.exe",
    "bytedance feishu",
    # macOS
    "feishu",  # macOS 应用名
    "lark",  # macOS 应用名
    "飞书",  # macOS 可能返回中文名
    # Linux
    "feishu",
    "lark",
    # Electron (需要结合标题确认)
    "electron",
]

FEISHU_TITLE_KEYWORDS = [
    "飞书",
    "feishu",
    "lark",
]


class AppRouter:
    """应用路由器"""

    def __init__(self):
        """初始化路由器"""
        self.wechat_processes = [p.lower() for p in WECHAT_PROCESS_NAMES]
        self.wechat_titles = [t.lower() for t in WECHAT_TITLE_KEYWORDS]
        self.feishu_processes = [p.lower() for p in FEISHU_PROCESS_NAMES]
        self.feishu_titles = [t.lower() for t in FEISHU_TITLE_KEYWORDS]

    def identify_app(self, window: WindowMeta) -> tuple[AppType, str]:  # noqa: C901
        """
        识别窗口对应的应用

        Args:
            window: 窗口元数据

        Returns:
            (应用类型, 识别原因)
        """
        process_name = window.process_name.lower()
        title = window.title.lower()

        # 优先通过进程名识别（更准确）
        for proc in self.wechat_processes:
            if proc in process_name:
                return AppType.WECHAT, f"process_match:{proc}"

        for proc in self.feishu_processes:
            if proc in process_name:
                # 飞书的Electron进程需要进一步通过标题确认
                if proc == "electron":
                    for keyword in self.feishu_titles:
                        if keyword in title:
                            return AppType.FEISHU, f"process_electron+title:{keyword}"
                else:
                    return AppType.FEISHU, f"process_match:{proc}"

        # 通过标题识别（兜底）
        for keyword in self.wechat_titles:
            if keyword in title:
                return AppType.WECHAT, f"title_match:{keyword}"

        for keyword in self.feishu_titles:
            if keyword in title:
                return AppType.FEISHU, f"title_match:{keyword}"

        return AppType.UNKNOWN, "no_match"

    def route(self, frame_event: FrameEvent) -> RoutedFrame | None:
        """
        路由帧事件

        Args:
            frame_event: 帧事件

        Returns:
            路由后的帧，如果是未知应用返回None
        """
        app_type, reason = self.identify_app(frame_event.window_meta)

        # 未知应用直接丢弃
        if app_type == AppType.UNKNOWN:
            return None

        return RoutedFrame(
            app_id=app_type,
            frame=frame_event.frame,
            window_meta=frame_event.window_meta,
            route_reason=reason,
        )

    def is_target_window(self, window: WindowMeta) -> bool:
        """
        检查窗口是否为目标应用

        Args:
            window: 窗口元数据

        Returns:
            是否为目标应用
        """
        app_type, _ = self.identify_app(window)
        return app_type != AppType.UNKNOWN

    def filter_target_windows(self, windows: list[WindowMeta]) -> list[tuple[WindowMeta, AppType]]:
        """
        筛选目标应用窗口

        Args:
            windows: 窗口列表

        Returns:
            (窗口, 应用类型) 列表
        """
        results = []
        for window in windows:
            app_type, _ = self.identify_app(window)
            if app_type != AppType.UNKNOWN:
                results.append((window, app_type))
        return results


# 单例实例


@lru_cache(maxsize=1)
def get_router() -> AppRouter:
    """获取路由器单例"""
    return AppRouter()
