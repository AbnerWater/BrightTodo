"""
先验注册表
管理所有应用的先验配置
"""

from ..models import AppType
from .base import AppPrior
from .feishu import FeishuPrior
from .wechat import WeChatPrior

# 全局先验注册表
_prior_registry: dict[AppType, AppPrior] = {}


def _init_default_priors():
    """初始化默认先验"""
    register_prior(AppType.WECHAT, WeChatPrior())
    register_prior(AppType.FEISHU, FeishuPrior())


def register_prior(app_type: AppType, prior: AppPrior):
    """
    注册应用先验

    Args:
        app_type: 应用类型
        prior: 先验配置实例
    """
    _prior_registry[app_type] = prior


def get_prior(app_type: AppType) -> AppPrior | None:
    """
    获取应用先验

    Args:
        app_type: 应用类型

    Returns:
        先验配置实例，未注册返回 None
    """
    # 懒加载初始化
    if not _prior_registry:
        _init_default_priors()

    return _prior_registry.get(app_type)


def list_priors() -> dict[AppType, AppPrior]:
    """列出所有已注册的先验"""
    if not _prior_registry:
        _init_default_priors()
    return _prior_registry.copy()
