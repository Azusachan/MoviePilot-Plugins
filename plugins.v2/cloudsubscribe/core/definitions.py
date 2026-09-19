"""自描述驱动与搜索渠道扩展规范（Service Provider Interface）。"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any, Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple, Type


@dataclass
class FieldSpec:
    """表单字段规范定义，用于动态下发前端渲染。"""

    key: str
    label: str = ""
    type: str = "text"  # text, password, number, switch, select, cloud-directory, account, test-source 等
    hint: str = ""
    cols: int = 12
    placeholder: str = ""
    default: Any = None
    options: Optional[List[Dict[str, Any]]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    suffix: str = ""
    show_condition: Optional[str] = None
    scan_provider: Optional[str] = None
    drive_provider: Optional[str] = None
    account_key: Optional[str] = None
    source: Optional[str] = None
    test_source: Optional[str] = None
    compact: bool = False
    items: Optional[List[Dict[str, Any]]] = None
    lines: Optional[List[str]] = None
    multiple: bool = False
    searchable: bool = False
    disabled: bool = False
    readonly: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "key": self.key,
            "label": self.label,
            "type": self.type,
            "cols": self.cols,
        }
        if self.hint:
            data["hint"] = self.hint
        if self.placeholder:
            data["placeholder"] = self.placeholder
        if self.default is not None:
            data["default"] = self.default
        raw_options = self.items if self.items is not None else self.options
        if raw_options is not None:
            data["items"] = raw_options
            data["options"] = raw_options
        if self.lines is not None:
            data["lines"] = self.lines
        if self.multiple:
            data["multiple"] = self.multiple
        if self.searchable:
            data["searchable"] = self.searchable
        if self.disabled:
            data["disabled"] = self.disabled
        if self.readonly:
            data["readonly"] = self.readonly
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        if self.step is not None:
            data["step"] = self.step
        if self.suffix:
            data["suffix"] = self.suffix
        if self.show_condition:
            data["show"] = self.show_condition
        if self.scan_provider:
            data["scanProvider"] = self.scan_provider
        if self.drive_provider:
            data["driveProvider"] = self.drive_provider
        if self.account_key:
            data["accountKey"] = self.account_key
        if self.source:
            data["source"] = self.source
        if self.test_source:
            data["testSource"] = self.test_source
        if self.compact:
            data["compact"] = self.compact
        if self.extra:
            data.update(self.extra)
        return data


@dataclass
class GroupSpec:
    """配置分组规范定义。"""

    tab: str = ""
    title: str = ""
    icon: str = ""
    hint: str = ""
    hide_heading: bool = False
    before_tabs: bool = False
    show_condition: Optional[str] = None
    fields: List[FieldSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "title": self.title,
            "fields": [f.to_dict() for f in self.fields],
        }
        if self.tab:
            data["tab"] = self.tab
        if self.icon:
            data["icon"] = self.icon
        if self.hint:
            data["hint"] = self.hint
        if self.hide_heading:
            data["hideHeading"] = self.hide_heading
        if self.before_tabs:
            data["beforeTabs"] = self.before_tabs
        if self.show_condition:
            data["show"] = self.show_condition
        return data


@dataclass(frozen=True)
class CheckinDefinition:
    """签到提供方自描述契约。"""

    key: str
    name: str
    icon: str = "mdi-calendar-check-outline"
    credential_attrs: Tuple[str, ...] = ()
    credential_keys: Tuple[str, ...] = ()
    error_types: Tuple[Type[Exception], ...] = (Exception,)
    modes: Tuple[str, ...] = ("normal",)
    order: int = 100
    group: Optional[GroupSpec] = None

    def to_provider_spec(self) -> Dict[str, Any]:
        """供前端 checkin-timeline 消费的提供者规格。"""
        return {
            "key": self.key,
            "name": self.name,
            "icon": self.icon,
            "enabledKey": f"{self.key}_checkin_enabled",
            "modeKey": f"{self.key}_checkin_mode",
            "credentialKeys": list(self.credential_keys),
        }


class DriverDefinition:
    """网盘驱动自描述规范基类。"""

    id: str = ""
    name: str = ""
    icon: str = "mdi-cloud-outline"
    order: int = 100
    qrcode_service_type: Any = None
    qrcode_credentials: Mapping[str, str] = {}
    qrcode_required_credentials: Tuple[str, ...] = ()
    qrcode_hint: str = "请扫描二维码完成登录"
    qrcode_channels: Tuple[Mapping[str, str], ...] = ()

    @classmethod
    def get_config_groups(cls, context: Optional[Dict[str, Any]] = None) -> List[GroupSpec]:
        """返回该驱动配置表单的分组与字段定义。"""
        return []

    @classmethod
    def get_checkin_definition(cls) -> Optional[CheckinDefinition]:
        """如果该网盘支持签到，返回其自描述契约。"""
        return None

    @classmethod
    def create_qrcode_service(cls) -> Any:
        """按客户端方法形态自动选择类服务或无凭据实例。"""
        service_type = cls.qrcode_service_type
        if service_type is None:
            return None
        creator = getattr(service_type, "create_qrcode_login", None)
        if not callable(creator):
            return None
        parameters = tuple(inspect.signature(creator).parameters.values())
        if parameters and parameters[0].name == "self":
            return service_type()
        return service_type

    @classmethod
    def qrcode_meta(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "hint": cls.qrcode_hint,
            "channels": [dict(item) for item in cls.qrcode_channels],
        }

    @classmethod
    def qrcode_config_values(cls, result: Mapping[str, Any]) -> Dict[str, str]:
        missing = [
            key for key in cls.qrcode_required_credentials
            if not str(result.get(key) or "").strip()
        ]
        if missing:
            raise RuntimeError(f"扫码成功但未获得凭据：{', '.join(missing)}")
        return {
            config_key: str(result.get(result_key) or "").strip()
            for result_key, config_key in cls.qrcode_credentials.items()
            if str(result.get(result_key) or "").strip()
        }

    @classmethod
    def create_client(cls, config: Dict[str, Any], context: Optional[Any] = None) -> Any:
        """从全局配置字典中构建驱动客户端实例。"""
        raise NotImplementedError

    @classmethod
    def create_provider(
            cls, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        """将客户端包装为标准的 CloudDriveProvider 实例。"""
        raise NotImplementedError

    @classmethod
    def get_account_info(
            cls, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Dict[str, Any]:
        """读取该驱动的实时账户信息。"""
        return {"connected": bool(client), "error": ""}


class SearchSourceDefinition:
    """搜索渠道自描述规范基类。"""

    id: str = ""
    name: str = ""
    icon: str = "mdi-magnify"
    order: int = 100

    @staticmethod
    def config_value(config: Mapping[str, Any], key: str, default: Any = None) -> Any:
        value = config.get(f"_{key}")
        if value is None:
            value = config.get(key)
        return default if value is None else value

    @classmethod
    def get_config_groups(cls, context: Optional[Dict[str, Any]] = None) -> List[GroupSpec]:
        """返回该搜索渠道表单的分组与字段定义。"""
        return []

    @classmethod
    def get_checkin_definition(cls) -> Optional[CheckinDefinition]:
        """如果该搜索渠道支持签到，返回其自描述契约。"""
        return None

    @classmethod
    def get_config_keys(cls) -> FrozenSet[str]:
        cached = cls.__dict__.get("_config_keys_cache")
        if cached is not None:
            return cached
        keys = {
            field.key
            for group in cls.get_config_groups()
            for field in group.fields
            if field.key and not field.key.startswith("test_")
        }
        cls._config_keys_cache = frozenset(keys)
        return cls._config_keys_cache

    @classmethod
    def configure_owner(
            cls, owner: Any, config: Mapping[str, Any]
    ) -> None:
        """归一化渠道运行参数并初始化渠道私有状态。"""

    @classmethod
    def get_search_timeout(
            cls, config: Mapping[str, Any], default: float = 60.0
    ) -> float:
        """返回渠道搜索超时；未声明独立配置时使用全局值。"""
        key = f"{cls.id}_timeout"
        if key not in cls.get_config_keys():
            return float(default)
        try:
            value = float(cls.config_value(config, key, default) or default)
        except (TypeError, ValueError):
            value = float(default)
        return max(5.0, min(value, 120.0))

    @classmethod
    def build_test_context(
            cls, config: Dict[str, Any], context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """返回隔离测试处理器所需的渠道专属依赖。"""
        return {}

    @classmethod
    def close_test_resources(cls) -> None:
        """释放 Definition 持有的可复用测试资源。"""

    @classmethod
    def create_client(cls, config: Dict[str, Any], context: Optional[Any] = None) -> Any:
        """构建底层搜索 API 客户端。"""
        return None

    @classmethod
    def create_service(
            cls, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        """构建搜索业务服务。"""
        return None

    @classmethod
    def create_provider(
            cls, service: Any, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Any:
        """构建标准 SearchProvider 实例以接入 SearchRegistry。"""
        raise NotImplementedError

    @classmethod
    def get_account_info(
            cls, client: Any, config: Dict[str, Any], context: Optional[Any] = None
    ) -> Dict[str, Any]:
        """读取该搜索源的账户信息。"""
        return {"connected": bool(client), "error": ""}
