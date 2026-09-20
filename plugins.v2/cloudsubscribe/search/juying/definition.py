"""聚影搜索渠道自描述规范与表单声明。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...core.definitions import CheckinDefinition, FieldSpec, GroupSpec, SearchSourceDefinition
from .client import JuyingClient, JuyingError
from .provider import create_juying_provider
from .resource import JuyingResourceService
from .service import JuyingSearchService


class JuyingSourceDefinition(SearchSourceDefinition):
    """聚影搜索渠道规范。"""

    id = "juying"
    name = "聚影"
    icon = "mdi-movie-search-outline"
    order = 40

    @classmethod
    def create_client(cls, config: Dict[str, Any], context: Optional[Any] = None) -> Any:
        ctx = context or {}
        owner = ctx.get("storage_owner")
        username = str(cls.config_value(config, "juying_username", "") or "").strip()
        password = str(cls.config_value(config, "juying_password", "") or "")
        if not username or not password:
            return None
        return JuyingClient(
            base_url=str(cls.config_value(config, "juying_base_url", JuyingClient.BASE_URL) or JuyingClient.BASE_URL),
            username=username,
            password=password,
            proxy=ctx.get("proxy"),
            request_timeout=int(cls.config_value(config, "juying_timeout", 60) or 60),
            request_interval=float(cls.config_value(config, "juying_request_interval", 1.0) or 1.0),
            get_data_func=getattr(owner, "get_data", None),
            save_data_func=getattr(owner, "save_data", None),
        )

    @classmethod
    def get_checkin_definition(cls) -> Optional[CheckinDefinition]:
        return CheckinDefinition(
            key="juying",
            name="聚影",
            icon="mdi-movie-check-outline",
            credential_attrs=("_juying_username", "_juying_password"),
            credential_keys=("juying_username", "juying_password"),
            error_types=(JuyingError,),
            modes=("normal",),
            order=40,
            group=GroupSpec(
                tab="checkin",
                title="聚影签到",
                icon="mdi-movie-check-outline",
                fields=[
                    FieldSpec(
                        key="juying_checkin_enabled",
                        label="启用每日签到",
                        type="switch",
                        cols=12,
                    ),
                ],
            ),
        )

    @classmethod
    def get_config_groups(cls, context: Optional[Dict[str, Any]] = None) -> List[GroupSpec]:
        return [
            GroupSpec(
                tab="juying",
                title="聚影账号",
                icon="mdi-account-key-outline",
                hint="使用聚影网页登录账号访问官方 WebAPI",
                fields=[
                    FieldSpec(
                        key="juying_account_info",
                        type="account",
                        account_key="search:juying",
                        compact=True,
                        cols=12,
                    ),
                    FieldSpec(
                        key="juying_base_url",
                        label="服务地址",
                        placeholder="https://juying.tv",
                        cols=12,
                    ),
                    FieldSpec(
                        key="juying_username",
                        label="网页登录账号",
                        cols=6,
                    ),
                    FieldSpec(
                        key="juying_password",
                        label="网页登录密码",
                        type="password",
                        cols=6,
                    ),
                    FieldSpec(
                        key="test_juying",
                        label="测试搜索",
                        type="test-source",
                        source="juying",
                        cols=12,
                    ),
                ],
            ),
            GroupSpec(
                tab="juying",
                title="搜索与风控",
                icon="mdi-shield-search",
                hint="影片、资源和票据接口共用限速；缓存搜索结果和短时访问票据，减少重复请求。",
                fields=[
                    FieldSpec(
                        key="juying_result_limit",
                        label="候选上限",
                        type="number",
                        min=1,
                        max=20,
                        cols=4,
                    ),
                    FieldSpec(
                        key="juying_request_interval",
                        label="请求访问间隔",
                        hint="登录、影片查询、资源分页和票据兑换共用统一限速，并自动加入随机抖动。",
                        type="number",
                        min=0.5,
                        max=10,
                        step=0.5,
                        suffix="秒",
                        cols=4,
                    ),
                    FieldSpec(
                        key="juying_timeout",
                        label="搜索超时",
                        hint="单次搜索最大等待时间，超时自动中断并上报熔断，默认 60 秒",
                        type="number",
                        min=5,
                        max=120,
                        suffix="秒",
                        cols=4,
                    ),
                ],
            ),
        ]

    @classmethod
    def create_provider(
            cls, service: Any, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        ctx = context or {}
        owner = ctx.get("owner")
        resources = JuyingResourceService(client) if client else None
        r_types = getattr(owner, "_juying_resource_types", ())
        if not client or not resources or not r_types or not getattr(client, "is_configured", False):
            return None
        limit = int(cls.config_value(config, "juying_result_limit", 20) or 20)
        svc = JuyingSearchService(client, resources, r_types, limit)
        return create_juying_provider(
            svc,
            client,
            r_types,
            {"result_limit": limit, "resource_types": list(r_types)},
        )
