"""盘链网页登录、资源查询与分享链接解析。"""

import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.log import logger

from ..http_client import (
    RequestGate,
    gated_idempotent_request,
    gated_request,
    normalize_proxies,
    request_error_summary,
    requests,
)
from ..types import (
    normalize_resource_type,
    resource_type_from_url,
)


def _format_datetime(value: Any) -> str:
    """将时间字符串格式化为可读时间（YYYY-MM-DD HH:MM:SS），不做二次时区偏移。"""
    if not value:
        return ""
    val_str = str(value).strip()
    if not val_str:
        return ""
    if "T" in val_str:
        val_str = val_str.replace("T", " ")
    if val_str.endswith("Z"):
        val_str = val_str[:-1].strip()
    if "." in val_str:
        val_str = val_str.split(".")[0].strip()
    return val_str


class PinglianError(RuntimeError):
    """盘链登录、查询或链接解析失败。"""

    def __init__(self, message: str, code: str = "pinglian_error"):
        super().__init__(message)
        self.code = code


class PinglianClient:
    BASE_URL = "https://pinglian.lol"
    _SESSION_DATA_KEY = "pinglian_auth_session"
    _LOGIN_LOCK = threading.RLock()
    _HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        ),
    }

    def __init__(
            self,
            username: str,
            password: str,
            base_url: str = BASE_URL,
            proxy: Any = None,
            request_timeout: int = 30,
            request_interval: float = 1.0,
            get_data_func: Optional[Callable] = None,
            save_data_func: Optional[Callable] = None,
    ):
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self.username = str(username or "").strip()
        self.password = str(password or "")
        self._proxies = normalize_proxies(proxy)
        self._request_timeout = max(5, min(int(request_timeout or 30), 120))
        self._session = self._create_session()
        self._request_gate = RequestGate.shared(
            "盘链",
            f"{self.base_url}|{self.username.casefold()}|{self._proxies}",
            request_interval=request_interval, minimum_interval=0.5
        )
        self._get_data_func = get_data_func
        self._save_data_func = save_data_func
        self._lock = threading.RLock()
        self._authenticated = False
        self._restore_session()

    @property
    def _timeout(self) -> tuple[int, int]:
        return min(15, self._request_timeout), self._request_timeout

    @classmethod
    def _create_session(cls):
        session = requests.Session(impersonate="chrome")
        session.headers.update(cls._HEADERS)
        return session

    def _session_request(self, *args, **kwargs):
        return self._session.request(*args, **kwargs)

    def _reset_transport(self, error: BaseException, attempt: int) -> None:
        cookies = self._session.cookies.get_dict()
        try:
            self._session.close()
        except Exception:
            pass
        self._session = self._create_session()
        for name, value in cookies.items():
            self._session.cookies.set(name, value)
        logger.debug(
            f"盘链连接异常后重建 HTTP 会话："
            f"{type(error).__name__}，重试={attempt}"
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    @staticmethod
    def _is_json(response) -> bool:
        return "application/json" in str(
            response.headers.get("content-type") or ""
        ).casefold()

    def _restore_session(self) -> None:
        if not self._get_data_func:
            return
        try:
            data = self._get_data_func(self._SESSION_DATA_KEY) or {}
            if (
                    not isinstance(data, dict)
                    or str(data.get("username") or "").strip() != self.username
            ):
                return
            cookies = data.get("cookies") or {}
            if isinstance(cookies, dict):
                for name, value in cookies.items():
                    if str(name or "").strip() and str(value or ""):
                        self._session.cookies.set(str(name), str(value))
                self._authenticated = bool(cookies)
                if cookies:
                    logger.debug("盘链已恢复持久化登录状态")
        except Exception as error:
            logger.debug(f"盘链恢复持久化登录状态失败：{error}")

    def _save_session(self) -> None:
        if not self._save_data_func:
            return
        try:
            cookies = self._session.cookies.get_dict()
            self._save_data_func(
                self._SESSION_DATA_KEY,
                {
                    "username": self.username,
                    "cookies": cookies,
                    "updated_at": int(time.time()),
                } if cookies else {},
            )
        except Exception as error:
            logger.debug(f"盘链持久化登录状态失败：{error}")

    def _clear_session(self) -> None:
        self._authenticated = False
        self._session.cookies.clear()
        self._save_session()

    def _check_auth_status(self) -> bool:
        """检查当前已保存的会话状态是否仍然有效。"""
        try:
            response = gated_idempotent_request(
                self._request_gate,
                self._session_request,
                "GET",
                f"{self.base_url}/api/auth/status",
                headers={
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/",
                },
                proxies=self._proxies,
                timeout=self._timeout,
            )
            if response.status_code == 200 and self._is_json(response):
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else {}
                if isinstance(data, dict):
                    if data.get("is_admin") or (
                        data.get("role") == "user"
                        and int(data.get("user_id") or 0) > 0
                    ):
                        return True
        except Exception as error:
            logger.debug(f"盘链鉴权状态检查异常：{error}")
        return False

    def _login(self, force: bool = False) -> None:
        if not self.is_configured:
            raise PinglianError("盘链账号或密码未配置", "pinglian_not_configured")
        if self._authenticated and not force:
            return
        with self._LOGIN_LOCK:
            if self._authenticated and not force:
                return
            if force:
                self._clear_session()
            elif self._authenticated and self._check_auth_status():
                return

            try:
                response = gated_request(
                    self._request_gate,
                    self._session_request,
                    "POST",
                    f"{self.base_url}/api/auth/login",
                    data={
                        "username": self.username,
                        "password": self.password,
                        "remember": "1",
                    },
                    headers={
                        "Origin": self.base_url,
                        "Referer": f"{self.base_url}/login",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    proxies=self._proxies,
                    timeout=self._timeout,
                )
            except requests.exceptions.RequestException as error:
                raise PinglianError(
                    f"盘链登录失败：{request_error_summary(error)}",
                    "pinglian_login_failed",
                ) from error

            if response.status_code != 200 or not self._is_json(response):
                raise PinglianError(
                    f"盘链登录失败（HTTP {response.status_code}）",
                    "pinglian_login_failed",
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise PinglianError(
                    "盘链登录响应格式异常", "pinglian_schema_changed"
                ) from error

            if not isinstance(payload, dict) or not payload.get("success"):
                error_msg = str(
                    (payload or {}).get("message")
                    or "盘链账号或密码错误"
                )
                raise PinglianError(error_msg, "pinglian_login_failed")

            self._authenticated = True
            self._save_session()
            logger.info("盘链登录成功并已更新会话")

    def _request(
            self,
            method: str,
            path: str,
            retry_auth: bool = True,
            **kwargs,
    ):
        if not path.startswith("/api/auth/login"):
            self._login()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Origin", self.base_url)
        headers.setdefault("Referer", f"{self.base_url}/")
        try:
            response = gated_idempotent_request(
                self._request_gate,
                self._session_request,
                method,
                f"{self.base_url}{path}",
                on_retry=self._reset_transport,
                headers=headers,
                proxies=self._proxies,
                timeout=self._timeout,
                **kwargs,
            )
        except requests.exceptions.RequestException as error:
            raise PinglianError(
                f"盘链请求失败：{request_error_summary(error)}",
                "pinglian_request_failed",
            ) from error

        auth_failed = response.status_code in (401, 403)
        payload = None
        if self._is_json(response):
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                error_type = str(payload.get("error_type") or "").strip()
                message = str(payload.get("message") or "").strip()
                if (
                    error_type in ("ADMIN_AUTH_REQUIRED", "AUTH_REQUIRED")
                    or "请先登录" in message
                    or str(payload.get("code") or "") == "-1"
                ):
                    auth_failed = True
        else:
            response_path = str(urlparse(str(response.url or "")).path or "")
            auth_failed = auth_failed or "/login" in response_path

        if auth_failed and retry_auth:
            self._clear_session()
            self._login(force=True)
            return self._request(method, path, retry_auth=False, **kwargs)

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after") or ""
            try:
                cooldown = max(30, min(120, int(float(retry_after))))
            except (TypeError, ValueError):
                cooldown = 30
            self._request_gate.activate_cooldown(
                cooldown, status=429, reason="盘链 HTTP 429"
            )
            raise PinglianError("盘链请求过于频繁，请稍后重试", "pinglian_rate_limited")

        if response.status_code >= 400:
            raise PinglianError(
                f"盘链请求失败（HTTP {response.status_code}）",
                "pinglian_request_failed",
            )
        return response, payload

    def request_json(
            self,
            path: str,
            method: str = "GET",
            params: Optional[Dict[str, Any]] = None,
            **kwargs,
    ) -> Dict[str, Any]:
        response, payload = self._request(
            method, path, params=params, **kwargs
        )
        if not self._is_json(response) or not isinstance(payload, dict):
            raise PinglianError(
                "盘链返回了非 JSON 页面，接口可能已改版", "pinglian_schema_changed"
            )
        if payload.get("success") is False:
            message = str(payload.get("message") or "盘链接口调用失败")
            error_type = str(payload.get("error_type") or "pinglian_api_error")
            raise PinglianError(message, error_type)
        return payload

    @staticmethod
    def apply_password(resource_type: str, target: str, password: str) -> str | bytes:
        password = str(password or "").strip()
        if not password:
            return target
        parsed = urlparse(target)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        key = {
            "115": "password", "123": "pwd", "guangya": "code", "baidu": "pwd"
        }.get(resource_type)
        if key and key not in query:
            query[key] = password
            return urlunparse(parsed._replace(query=urlencode(query)))
        if resource_type in {"quark", "alipan", "tianyi"}:
            return f"{target} 提取码: {password}"
        return target

    def resolve_resource(
            self,
            token: str = "",
            resource_type: str = "",
            password: str = "",
            link_id: str = "",
            **kwargs,
    ) -> Dict[str, str | bytes]:
        """按两步解锁流程换取盘链的真实网盘直链。"""
        target_id = str(link_id or token or "").strip()
        expected_type = normalize_resource_type(resource_type)
        if not target_id:
            raise PinglianError("盘链资源标识无效", "pinglian_invalid_token")

        # 第一步：获取解锁凭证 (link-ticket)
        try:
            ticket_payload = self.request_json(
                "/api/videos/link-ticket",
                method="POST",
                json={"link_id": int(target_id) if target_id.isdigit() else target_id},
            )
        except Exception as error:
            raise PinglianError(
                f"获取盘链资源解锁凭证失败：{error}", "pinglian_ticket_failed"
            ) from error

        ticket_data = ticket_payload.get("data") if isinstance(ticket_payload, dict) else {}
        ticket = str((ticket_data or {}).get("ticket") or "").strip()
        ticket_code = str((ticket_data or {}).get("code") or "").strip()
        if not ticket:
            raise PinglianError("盘链未返回有效解锁凭证", "pinglian_ticket_empty")

        # 第二步：使用凭证换取实际网盘链接 (link-open)
        try:
            open_payload = self.request_json(
                f"/api/videos/link-open/{target_id}",
                method="GET",
                params={"t": ticket},
            )
        except Exception as error:
            raise PinglianError(
                f"打开盘链真实链接失败：{error}", "pinglian_open_failed"
            ) from error

        open_data = open_payload.get("data") if isinstance(open_payload, dict) else {}
        target_url = str((open_data or {}).get("url") or "").strip()
        if not target_url:
            raise PinglianError("盘链未返回有效分享链接", "pinglian_empty_link")

        actual_type = resource_type_from_url(target_url)
        final_type = actual_type or expected_type

        # 密码提取优先级：link-open 返回的密码 > ticket 附带的 code > 参数传入的 password
        resolved_pwd = str(
            (open_data or {}).get("password")
            or (open_data or {}).get("code")
            or ticket_code
            or password
            or ""
        ).strip()

        return {
            "url": self.apply_password(final_type, target_url, resolved_pwd),
            "resource_type": final_type,
        }

    def get_account_info(self) -> Dict[str, Any]:
        """从新版个人中心及配额接口读取账户、会员与配额信息。"""
        profile_payload = self.request_json("/api/me/profile")
        profile = profile_payload.get("data") if isinstance(profile_payload, dict) else {}
        if not isinstance(profile, dict):
            raise PinglianError("盘链个人中心数据格式异常", "pinglian_schema_changed")

        name = str(profile.get("username") or self.username).strip()
        vip_level = profile.get("vip_level")
        level_str = f"VIP{vip_level}" if vip_level else "普通用户"

        quota = {}
        try:
            quota_payload = self.request_json("/api/videos/link-quota")
            quota = quota_payload.get("data") if isinstance(quota_payload, dict) else {}
        except Exception as error:
            logger.debug(f"盘链读取配额信息失败：{error}")

        quota_text = ""
        if isinstance(quota, dict) and quota:
            if quota.get("unlimited"):
                quota_text = "不限次数"
            elif "limit" in quota and "used" in quota:
                quota_text = f"{quota.get('used', 0)}/{quota.get('limit', 0)} 次"
            elif quota.get("remaining") is not None:
                quota_text = f"{quota.get('remaining')} 次"

        details: Dict[str, str] = {}
        if profile.get("created_at"):
            details["注册日期"] = _format_datetime(profile.get("created_at"))
        if profile.get("vip_expires_at"):
            details["VIP 到期"] = _format_datetime(profile.get("vip_expires_at"))
        if profile.get("account_count") is not None:
            details["关联网盘数"] = f"{int(profile.get('account_count') or 0)} 个"

        remaining_quota = (
            quota.get("remaining") if isinstance(quota, dict) else None
        )
        points = quota_text or (int(remaining_quota) if remaining_quota is not None else 0)

        return {
            "name": name,
            "email": str(profile.get("email") or ""),
            "level": level_str,
            "points": points,
            "quota_text": quota_text,
            "expires_at": _format_datetime(profile.get("vip_expires_at")),
            "registered_at": _format_datetime(profile.get("created_at")),
            "invite_count": "",
            "details": details,
        }

    def clear_cache(self) -> Dict[str, int]:
        return {"session": int(self._authenticated)}

    def close(self) -> None:
        with self._lock:
            self._session.close()
