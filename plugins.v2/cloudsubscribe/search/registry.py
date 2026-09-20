"""搜索渠道注册表组装。"""

from typing import Any

from ..core.search import SearchRegistry
from .scanner import SearchSourceRegistry


def create_search_registry(
        owner: Any,
        **extra_context: Any,
) -> SearchRegistry:
    """根据当前配置自动扫描并组装可用搜索渠道。"""
    registry = SearchRegistry()
    resource_types = tuple(getattr(owner, "_resource_type_order_config", ()))
    context = {
        "owner": owner,
        "storage_owner": getattr(owner, "_plugin", None) or owner,
        "resource_types": resource_types,
        "proxy": getattr(owner, "_search_proxy", None),
        **extra_context,
    }

    for def_cls in SearchSourceRegistry.get_definitions():
        try:
            client = def_cls.create_client(owner.__dict__, context)
            service = def_cls.create_service(client, owner.__dict__, context)
            provider = def_cls.create_provider(service, client, owner.__dict__, context)
            if provider:
                registry.register(provider, replace=True)
            else:
                from app.log import logger as _logger
                _logger.debug(f"搜索渠道 [{def_cls.id}] create_provider 返回 None，已跳过注册")
        except Exception as _err:
            from app.log import logger as _logger
            _logger.debug(f"搜索渠道 [{def_cls.id}] 注册失败：{_err}")

    return registry
