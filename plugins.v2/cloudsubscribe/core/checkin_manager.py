"""统一管理并动态发现全部具备签到能力的提供者契约。"""

from typing import Any, Dict, List, Optional
from app.log import logger

from .definitions import CheckinDefinition
from ..drive.scanner import DriverRegistry, get_driver_definitions
from ..search.scanner import SearchSourceRegistry, get_search_source_definitions


def get_checkin_definitions() -> Dict[str, CheckinDefinition]:
    """动态扫描并收集网盘与搜索渠道中声明的全部签到提供方自描述。"""
    collected: List[CheckinDefinition] = []

    # 1. 扫描网盘驱动
    for driver_cls in get_driver_definitions():
        try:
            defn = driver_cls.get_checkin_definition()
            if defn and isinstance(defn, CheckinDefinition):
                collected.append(defn)
        except Exception as err:
            logger.warning(f"获取网盘 {getattr(driver_cls, 'id', '')} 签到定义失败: {err}")

    # 2. 扫描搜索渠道
    for source_cls in get_search_source_definitions():
        try:
            defn = source_cls.get_checkin_definition()
            if defn and isinstance(defn, CheckinDefinition):
                collected.append(defn)
        except Exception as err:
            logger.warning(f"获取渠道 {getattr(source_cls, 'id', '')} 签到定义失败: {err}")

    # 3. 按 order 排序并构建字典
    collected.sort(key=lambda item: item.order)
    return {item.key: item for item in collected}


def get_checkin_schemas() -> Dict[str, Any]:
    """生成供前端动态渲染签到时间线与各渠道配置卡片的 schemas。"""
    definitions = list(get_checkin_definitions().values())
    providers: List[Dict[str, Any]] = [defn.to_provider_spec() for defn in definitions]
    groups: List[Dict[str, Any]] = [
        defn.group.to_dict() for defn in definitions if defn.group is not None
    ]
    return {
        "providers": providers,
        "groups": groups,
    }
