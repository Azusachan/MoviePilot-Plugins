"""Dian115 门户登录、浏览器会话与受控请求客户端。"""

import asyncio
import base64
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from urllib.parse import unquote, urljoin, urlparse, urlsplit

from app.log import logger
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from ..http_client import (
    AccountActionGate,
    RequestGate,
    gated_idempotent_request,
    normalize_proxies,
    requests,
)


class Dian115Error(RuntimeError):
    """Dian115 请求或协议错误。"""

    def __init__(self, message: str, code: str = "", status_code: int = 0):
        super().__init__(message)
        self.code = str(code or "")
        self.status_code = int(status_code or 0)


class Dian115Client:
    """维护登录 Cookie、浏览器证明和全接口统一限速。"""

    BASE_URL = "https://m.dian115.com"
    _IMPERSONATE = "chrome124"
    _USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    _SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'
    _SEC_CH_UA_FULL_VERSION = '"124.0.6367.207"'
    _SEC_CH_UA_FULL_VERSION_LIST = (
        '"Chromium";v="124.0.6367.207", '
        '"Google Chrome";v="124.0.6367.207", '
        '"Not-A.Brand";v="99.0.0.0"'
    )
    _PROOF_MARGIN_SECONDS = 15
    _BROWSER_LOGIN_TIMEOUT_SECONDS = 90
    _RISK_COOLDOWN_SECONDS = 60
    _SERVER_ERROR_COOLDOWN_SECONDS = 5
    _PORTAL_COOKIES = ("__Host-portal_token", "__Host-portal_browser")
    _SESSION_DATA_KEY = "dian115_auth_session"
    _TOKEN_REFRESH_MARGIN = 12 * 3600
    _PROOF_RETRY_CODES = ("browser_proof_required", "browser_proof_invalid")
    _LOGIN_LOCK = threading.RLock()

    @staticmethod
    def _normalize_request_interval(value: float) -> float:
        """将配置值归一化为与 RequestGate 初始化完全一致的范围。"""
        return max(0.2, min(float(value or 1.0), 10.0))

    @staticmethod
    def _normalize_unlocks_per_minute(value: int) -> int:
        """将解锁频率归一化为与 AccountActionGate 初始化一致的范围。"""
        return max(1, min(int(value or 6), 10))

    def __init__(
            self,
            email: str,
            password: str,
            base_url: str = BASE_URL,
            proxy: Any = None,
            request_interval: float = 1.0,
            unlocks_per_minute: int = 6,
            timeout: int = 30,
            get_data_func: Optional[Callable] = None,
            save_data_func: Optional[Callable] = None,
    ):
        self._email = str(email or "").strip()
        self.base_url = str(base_url or self.BASE_URL).rstrip("/")
        self._password = str(password or "").strip()
        self._proxies = normalize_proxies(proxy)
        self._timeout = max(5, min(int(timeout or 30), 120))
        self._visitor_id = str(uuid.uuid4())
        self._session = requests.Session(impersonate=self._IMPERSONATE)
        self._session.headers.update({
            "user-agent": self._USER_AGENT,
            "sec-ch-ua": self._SEC_CH_UA,
            "sec-ch-ua-full-version": self._SEC_CH_UA_FULL_VERSION,
            "sec-ch-ua-full-version-list": self._SEC_CH_UA_FULL_VERSION_LIST,
        })
        self._proof: Optional[tuple[str, float]] = None
        self._browser_private_key = ec.generate_private_key(ec.SECP256R1())
        self._browser_session_expires_at = 0.0
        self._portal_browser_cookie: str = ""
        self._server_time_offset_ms = 0
        self._authenticated = False
        self._get_data_func = get_data_func
        self._save_data_func = save_data_func
        self._lock = threading.RLock()
        self._request_gate = RequestGate.shared(
            "Dian115",
            f"{self.base_url}|{self._email.casefold()}|{self._proxies}",
            request_interval=self._normalize_request_interval(request_interval),
            minimum_interval=0.2,
            risk_cooldown_seconds=self._RISK_COOLDOWN_SECONDS,
            server_error_cooldown_seconds=self._SERVER_ERROR_COOLDOWN_SECONDS,
            challenge_detector=self._is_challenge_response,
        )
        self._unlock_gate = AccountActionGate.shared(
            "Dian115 解锁接口",
            f"dian115:{self._email.casefold()}",
            max_actions=self._normalize_unlocks_per_minute(unlocks_per_minute),
            maximum_actions=10,
        )
        self._restore_auth_cookie()

    @property
    def is_configured(self) -> bool:
        return bool(self._email and self._password)

    def matches_config(
            self, email: str, password: str, proxy: Any,
            request_interval: float, unlocks_per_minute: int,
    ) -> bool:
        return (
                self._email == str(email or "").strip()
                and self._password == str(password or "").strip()
                and self._proxies == normalize_proxies(proxy)
                and self._request_gate.request_interval
                == self._normalize_request_interval(request_interval)
                and self._unlock_gate.max_actions
                == self._normalize_unlocks_per_minute(unlocks_per_minute)
        )

    def close(self) -> None:
        with self._lock:
            self._session.close()
            self._proof = None
            self._browser_session_expires_at = 0.0
            self._portal_browser_cookie = ""
            self._authenticated = False

    def _clear_portal_cookies(self) -> None:
        for name in self._PORTAL_COOKIES:
            self._session.cookies.delete(name)
        self._browser_session_expires_at = 0.0
        self._portal_browser_cookie = ""
        self._server_time_offset_ms = 0
        self._save_auth_cookie("")

    def _restore_auth_cookie(self) -> None:
        if not self._get_data_func:
            return
        try:
            data = self._get_data_func(self._SESSION_DATA_KEY) or {}
            if (
                    not isinstance(data, dict)
                    or str(data.get("email") or "").strip().lower()
                    != self._email.lower()
            ):
                return
            token = str(data.get("token") or "").strip()
            cookies_dict = data.get("cookies") or {}
            if isinstance(cookies_dict, dict) and cookies_dict:
                for k, v in cookies_dict.items():
                    if k and v:
                        # 避免旧会话或浏览器公钥污染
                        if k == "__Host-portal_browser":
                            continue
                        self._session.cookies.set(k, v, domain="m.dian115.com", path="/")
            elif token:
                self._session.cookies.set("__Host-portal_token", token, domain="m.dian115.com", path="/", )

            # 避免旧 UA 导致 Cloudflare 指纹失配拦截
            self._session.headers["user-agent"] = self._USER_AGENT

            if token or (isinstance(cookies_dict, dict) and "__Host-portal_token" in cookies_dict):
                self._authenticated = True
                logger.debug("Dian115 已恢复持久化登录状态及凭证")
        except Exception as error:
            logger.debug(f"Dian115 恢复持久化登录状态失败：{error}")

    def _save_auth_cookie(
            self,
            token: str = "",
            cookies: Optional[Dict[str, str]] = None,
            user_agent: str = "",
    ) -> None:
        if not self._save_data_func:
            return
        try:
            value = str(token or "").strip()
            cookies_dict = dict(cookies or {})
            cookies_dict.pop("__Host-portal_browser", None)
            self._save_data_func(
                self._SESSION_DATA_KEY,
                {
                    "email": self._email,
                    "token": value,
                    "cookies": cookies_dict,
                    "user_agent": user_agent or self._session.headers.get("user-agent", ""),
                    "updated_at": int(time.time()),
                } if (value or cookies_dict) else {},
            )
        except Exception as error:
            logger.debug(f"Dian115 持久化登录状态失败：{error}")

    @staticmethod
    def _extract_token(raw: str) -> str:
        """自动提取 __Host-portal_token。"""
        if not raw:
            return ""
        text = str(raw).strip()
        if "eyJ" in text:
            for part in text.replace(",", ";").split(";"):
                part = part.strip()
                for prefix in ("__Host-portal_token=", "portal_token="):
                    if part.startswith(prefix):
                        return part.split("=", 1)[1].strip()
        return text

    @staticmethod
    def _jwt_claims(token: str) -> dict:
        """解析 JWT payload（不校验签名），提取到期时间。"""
        try:
            parts = (token or "").split(".")
            if len(parts) < 2:
                return {}
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            data = json.loads(base64.urlsafe_b64decode(payload))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _token_remaining(self) -> Optional[float]:
        """返回当前持久化 Token 剩余有效秒数，无法解析返回 None。"""
        token = self._session.cookies.get("__Host-portal_token") or ""
        exp = self._jwt_claims(token).get("exp")
        if not isinstance(exp, (int, float)):
            return None
        return float(exp) - time.time()

    def _token_from_response(self, response) -> str:
        """从响应中提取可能更新的 __Host-portal_token。"""
        if response is None:
            return ""
        # 1. 尝试从响应 cookies 或 session cookies 提取
        for jar in (getattr(response, "cookies", None), getattr(self._session, "cookies", None)):
            if not jar:
                continue
            for key in ("__Host-portal_token", "portal_token"):
                try:
                    val = jar.get(key) if hasattr(jar, "get") else None
                    if val:
                        return str(val)
                except Exception:
                    pass
            try:
                for c in jar:
                    name = getattr(c, "name", "") or ""
                    val = getattr(c, "value", "") or ""
                    if "portal_token" in name and val:
                        return val
            except Exception:
                pass
        # 2. 从 Set-Cookie 响应头解析
        try:
            headers = getattr(response, "headers", {}) or {}
            sc = headers.get("set-cookie") or headers.get("Set-Cookie") or ""
            if sc:
                extracted = self._extract_token(sc)
                if extracted and extracted != sc:
                    return extracted
        except Exception:
            pass
        # 3. 从 JSON 响应体提取
        try:
            data = response.json() or {}
        except Exception:
            data = {}
        return self._token_from_obj(data)

    def _token_from_obj(self, obj: Any) -> str:
        if isinstance(obj, dict):
            for key in ("token", "portal_token", "__Host-portal_token", "access_token", "jwt"):
                val = obj.get(key)
                if isinstance(val, str) and val.count(".") >= 2 and "eyJ" in val:
                    return val
            for val in obj.values():
                found = self._token_from_obj(val)
                if found:
                    return found
        elif isinstance(obj, list):
            for val in obj:
                found = self._token_from_obj(val)
                if found:
                    return found
        elif isinstance(obj, str) and obj.count(".") >= 2 and "eyJ" in obj:
            return self._extract_token(obj) or obj
        return ""

    def _headers(self, current_path: str) -> Dict[str, str]:
        """对齐标准浏览器请求头与 UA Client Hints。"""
        path = current_path if str(current_path).startswith("/") else "/"
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "user-agent": self._session.headers.get("user-agent") or self._USER_AGENT,
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": self._SEC_CH_UA,
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": self._SEC_CH_UA_FULL_VERSION,
            "sec-ch-ua-full-version-list": self._SEC_CH_UA_FULL_VERSION_LIST,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-model": '""',
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": '"19.0.0"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-gpc": "1",
            "referer": urljoin(f"{self.base_url}/", path.lstrip("/")),
        }

    @staticmethod
    def _is_challenge_response(response) -> bool:
        content_type = str(response.headers.get("content-type") or "").lower()
        cf_mitigated = str(
            response.headers.get("cf-mitigated") or ""
        ).strip().lower()
        return cf_mitigated == "challenge" or "text/html" in content_type

    def _raw_request(self, method: str, path: str, **kwargs):
        cooldown_remaining = self._request_gate.cooldown_remaining
        if cooldown_remaining > 0:
            status = self._request_gate.cooldown_status
            raise Dian115Error(
                f"Dian115 处于风控冷却期，跳过请求"
                f"（剩余 {int(cooldown_remaining + 0.999)} 秒）",
                code=("rate_limited" if status in {0, 403, 429}
                      else "server_cooldown"),
                status_code=status,
            )
        try:
            def request():
                return gated_idempotent_request(
                    self._request_gate,
                    self._session.request,
                    method,
                    urljoin(f"{self.base_url}/", path.lstrip("/")),
                    proxies=self._proxies,
                    timeout=self._timeout,
                    **kwargs,
                )

            if (
                    str(method or "").strip().upper() == "POST"
                    and path == "/api/portal/unlock"
            ):
                return self._unlock_gate.run(request)
            return request()
        except requests.exceptions.RequestException as error:
            raise Dian115Error(f"Dian115 请求失败：{error}") from error

    @staticmethod
    def _payload(response) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise Dian115Error(
                f"Dian115 返回非 JSON 响应，HTTP {response.status_code}",
                status_code=response.status_code,
            ) from error
        if not isinstance(payload, dict):
            raise Dian115Error("Dian115 返回结构异常")
        return payload

    @classmethod
    def _raise_response_error(cls, response, payload: Dict[str, Any]) -> None:
        code = str(payload.get("code") or "")
        message = str(
            payload.get("msg") or payload.get("message")
            or f"HTTP {response.status_code}"
        )
        raise Dian115Error(message, code=code, status_code=response.status_code)

    @staticmethod
    def _base64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    def _browser_proof(self, current_path: str, refresh: bool = False) -> tuple[str, bool]:
        now = time.time()
        cached = self._proof
        if not refresh and cached and cached[1] > now + self._PROOF_MARGIN_SECONDS:
            return cached[0], False
        headers = self._headers(current_path)
        token = self._session.cookies.get("__Host-portal_token")
        if token:
            headers["Cookie"] = f"__Host-portal_token={token}"
        response = self._raw_request(
            "GET", "/api/portal/auth/browser-challenge", headers=headers
        )
        payload = self._payload(response)
        proof = str(payload.get("proof") or "")
        if response.status_code != 200 or payload.get("code") != "ok" or not proof:
            self._raise_response_error(response, payload)
        ttl = max(30, int(payload.get("ttl") or 600))
        self._proof = (proof, now + ttl)
        # 证明刷新后必须重置 session 状态以重新向服务端登记公钥
        self._browser_session_expires_at = 0.0
        return proof, True

    def _public_jwk(self) -> Dict[str, str]:
        numbers = self._browser_private_key.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "x": self._base64url(numbers.x.to_bytes(32, "big")),
            "y": self._base64url(numbers.y.to_bytes(32, "big")),
        }

    def _ensure_browser_session(
            self, current_path: str, proof: str, refresh: bool = False
    ) -> None:
        now = time.time()
        if (
                not refresh
                and self._browser_session_expires_at
                > now + self._PROOF_MARGIN_SECONDS
                and self._portal_browser_cookie
        ):
            return
        headers = self._headers(current_path)
        headers.update({
            "content-type": "application/json",
            "x-portal-browser-proof": proof,
        })
        token = self._session.cookies.get("__Host-portal_token")
        if token:
            headers["Cookie"] = f"__Host-portal_token={token}"
        response = self._raw_request(
            "POST",
            "/api/portal/auth/browser-session",
            headers=headers,
            json={"public_jwk": self._public_jwk()},
        )
        payload = self._payload(response)
        if response.status_code != 200 or payload.get("code") not in {"ok", None}:
            self._raise_response_error(response, payload)

        # 提取 Set-Cookie 中的 __Host-portal_browser 会话标记
        browser_cookie = ""
        if hasattr(response, "cookies") and response.cookies:
            try:
                browser_cookie = response.cookies.get("__Host-portal_browser") or ""
            except Exception:
                pass
        if not browser_cookie:
            sc = (getattr(response, "headers", {})
                  .get("set-cookie") or getattr(response, "headers", {})
                  .get("Set-Cookie") or "")
            for part in str(sc).split(","):
                if "__Host-portal_browser=" in part:
                    browser_cookie = part.split("__Host-portal_browser=")[1].split(";")[0].strip()
                    break

        if browser_cookie:
            self._portal_browser_cookie = browser_cookie
            self._session.cookies.set(
                "__Host-portal_browser",
                browser_cookie,
                domain="m.dian115.com",
                path="/",
            )

        if payload.get("enabled") is False:
            self._browser_session_expires_at = now + 1800
            return
        server_time_ms = payload.get("server_time_ms")
        try:
            self._server_time_offset_ms = int(server_time_ms) - round(now * 1000)
        except (TypeError, ValueError):
            self._server_time_offset_ms = 0
        ttl = max(60, int(payload.get("ttl") or 1800))
        expires_at = str(payload.get("expires_at") or "").strip()
        if expires_at:
            try:
                expiry = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                expiry = now + ttl
        else:
            expiry = now + ttl
        self._browser_session_expires_at = max(now + 60, expiry)

    def _browser_signature(self, method: str, api_path: str) -> Dict[str, str]:
        timestamp = str(round(time.time() * 1000 + self._server_time_offset_ms))
        nonce = self._base64url(os.urandom(24))
        path = urlsplit(str(api_path or "/")).path or "/"
        canonical = (
            "portal-browser-request/v1\n"
            f"{str(method or 'GET').strip().upper()}\n"
            f"{path}\n{timestamp}\n{nonce}"
        ).encode("utf-8")
        der_signature = self._browser_private_key.sign(
            canonical, ec.ECDSA(hashes.SHA256())
        )
        r_value, s_value = decode_dss_signature(der_signature)
        signature = self._base64url(
            r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big")
        )
        return {
            "x-portal-browser-ts": timestamp,
            "x-portal-browser-nonce": nonce,
            "x-portal-browser-sig": signature,
        }

    def _authorized_headers(
            self,
            method: str,
            api_path: str,
            current_path: str,
            refresh_proof: bool = False,
    ) -> Dict[str, str]:
        headers = self._headers(current_path)
        proof, is_new_proof = self._browser_proof(
            current_path, refresh=refresh_proof
        )
        headers["x-portal-browser-proof"] = proof
        self._ensure_browser_session(
            current_path, proof, refresh=(refresh_proof or is_new_proof)
        )
        headers.update(self._browser_signature(method, api_path))
        # 显式构造 Cookie 请求头，确保 curl_cffi 可靠携带 __Host- 前缀凭证
        cookie_parts = []
        token = self._session.cookies.get("__Host-portal_token")
        if token:
            cookie_parts.append(f"__Host-portal_token={token}")
        if self._portal_browser_cookie:
            cookie_parts.append(f"__Host-portal_browser={self._portal_browser_cookie}")
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)
        return headers

    def _browser_proxy(self) -> Optional[Dict[str, str]]:
        proxies = self._proxies or {}
        proxy = proxies.get("https") or proxies.get("http")
        if not proxy:
            return None
        parsed = urlparse(str(proxy))
        if not parsed.scheme or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        server = f"{parsed.scheme}://{host}"
        if parsed.port:
            server += f":{parsed.port}"
        result = {"server": server}
        if parsed.username:
            result["username"] = unquote(parsed.username)
        if parsed.password:
            result["password"] = unquote(parsed.password)
        return result

    def _login_with_browser(self) -> None:
        executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="Dian115-BrowserLogin"
        )
        try:
            executor.submit(
                asyncio.run, self._login_with_browser_async()
            ).result()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    async def _login_with_browser_async(self) -> None:
        try:
            from app.core.config import settings
            from cloakbrowser import launch_context_async
        except ImportError as error:
            raise Dian115Error(
                "Dian115 登录需要CloakBrowser，请先准备浏览器仿真环境",
                code="browser_unavailable",
            ) from error

        context = None
        page = None
        timeout_ms = self._BROWSER_LOGIN_TIMEOUT_SECONDS * 1000
        try:
            browser_options = {
                "headless": True,
                "proxy": self._browser_proxy(),
                "humanize": getattr(settings, "CLOAKBROWSER_HUMANIZE", True),
                # Dian115 Turnstile 在 default 预设下会提交后停留登录页。
                "human_preset": "careful",
            }
            context = await launch_context_async(**browser_options)
            page = await context.new_page()
            # 浏览器导航无法直接套同步 requests 门控，先占用同一账号请求槽。
            self._request_gate.run(lambda: None)
            await page.goto(
                f"{self.BASE_URL}/login",
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )
            await page.wait_for_selector("input[type='email']", timeout=30000)
            await page.fill("input[type='email']", self._email)
            await page.fill("input[type='password']", self._password)

            # 等待 Cloudflare Turnstile frame 渲染并精确定位复选框坐标
            cf_frame = None
            for _ in range(30):
                await asyncio.sleep(1)
                for f in page.frames:
                    if "challenges.cloudflare.com" in f.url or "turnstile" in f.url:
                        cf_frame = f
                        break
                if cf_frame:
                    break

            clicked = False
            if cf_frame:
                try:
                    frame_el = await cf_frame.frame_element()
                    box = await frame_el.bounding_box()
                    if box and box.get("width", 0):
                        # 点击 Turnstile 复选框区域（左侧约 30px，垂直居中）
                        click_x = box["x"] + 30
                        click_y = box["y"] + box["height"] / 2
                        await page.mouse.click(click_x, click_y)
                        clicked = True
                except Exception as click_err:
                    logger.debug(f"通过 frame_element 点击 Turnstile 异常: {click_err}")

            if not clicked:
                widget_rect = await page.evaluate(
                    """() => {
                        const input = document.querySelector(
                            'input[name="cf-turnstile-response"]'
                        );
                        const rect = input?.parentElement?.getBoundingClientRect();
                        return rect && {
                            x: rect.x, y: rect.y,
                            width: rect.width, height: rect.height
                        };
                    }"""
                )
                if widget_rect and widget_rect.get("width", 0):
                    await page.mouse.click(
                        widget_rect["x"] + 30,
                        widget_rect["y"] + widget_rect["height"] / 2,
                    )

            try:
                await page.wait_for_function(
                    """() => Boolean(
                        document.querySelector(
                            'input[name="cf-turnstile-response"]'
                        )?.value
                    )""",
                    timeout=60000,
                )
            except Exception as error:
                raise Dian115Error(
                    "Dian115 Turnstile 人机验证未通过，"
                    "请检查 CloakBrowser 网络和指纹",
                    code="turnstile_failed",
                ) from error
            try:
                submit_btn = await page.wait_for_selector("button[type='submit'], button:has-text('登录')",
                                                          timeout=8000)
                if submit_btn:
                    await submit_btn.click()
                else:
                    await page.keyboard.press("Enter")
            except Exception:
                await page.keyboard.press("Enter")

            deadline = time.monotonic() + 35
            while "/login" in str(page.url or ""):
                if time.monotonic() >= deadline:
                    error_text = await page.evaluate(
                        """() => {
                            const el = document.querySelector('.error, .alert, [role="alert"], .text-danger, .text-red');
                            return el ? el.innerText.trim() : '';
                        }"""
                    )
                    if error_text:
                        raise Dian115Error(
                            f"Dian115 登录失败：{error_text}",
                            code="browser_login_failed",
                        )
                    raise Dian115Error(
                        "Dian115 浏览器登录后未离开登录页",
                        code="browser_login_failed",
                    )
                await page.wait_for_timeout(300)

            all_cookies = await context.cookies()
            saved_cookies = {}
            token_val = ""
            for cookie in all_cookies:
                c_name = cookie.get("name")
                c_val = cookie.get("value")
                c_domain = cookie.get("domain", "m.dian115.com")
                c_path = cookie.get("path", "/")
                if c_name and c_val:
                    if c_name == "__Host-portal_browser":
                        continue
                    saved_cookies[c_name] = c_val
                    self._session.cookies.set(
                        c_name,
                        c_val,
                        domain=c_domain.lstrip("."),
                        path=c_path,
                    )
                    if c_name == "__Host-portal_token":
                        token_val = c_val

            if not token_val:
                raise Dian115Error(
                    "Dian115 浏览器登录未返回认证 Cookie (__Host-portal_token)",
                    code="browser_login_failed",
                )
            self._session.headers["user-agent"] = self._USER_AGENT
            self._save_auth_cookie(
                token=token_val,
                cookies=saved_cookies,
                user_agent=self._USER_AGENT,
            )
            self._authenticated = True
            logger.debug("Dian115 CloakBrowser 登录成功，已更新全量认证凭证")
        except Dian115Error:
            raise
        except Exception as error:
            raise Dian115Error(
                f"Dian115 浏览器登录失败：{error}",
                code="browser_login_failed",
            ) from error
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    def _login(self, allow_browser_login: bool = True) -> None:
        if not self.is_configured:
            raise Dian115Error("Dian115 未配置邮箱或密码")
        with self._LOGIN_LOCK:
            self._restore_auth_cookie()
            # Token 智能续期：当前已认证且 Token 未过期时，检查是否即将过期
            remain = self._token_remaining()
            token_valid = self._authenticated and (remain is None or remain > 0)
            token_soon = remain is not None and remain <= self._TOKEN_REFRESH_MARGIN
            if token_valid and not token_soon:
                return
            if token_soon and token_valid:
                logger.debug("Dian115 Token 即将过期，尝试自动续期")
            api_path = "/api/portal/auth/login"
            try:
                headers = self._authorized_headers(
                    "POST", api_path, "/login", refresh_proof=True
                )
                headers["content-type"] = "application/json"
                response = self._raw_request(
                    "POST",
                    api_path,
                    headers=headers,
                    json={"email": self._email, "password": self._password},
                )
                # 尝试持久化响应中的新 Token
                new_token = self._token_from_response(response)
                if new_token:
                    self._save_auth_cookie(new_token)
                payload = self._payload(response)
                if response.status_code != 200 or payload.get("code") != "ok":
                    self._raise_response_error(response, payload)
                if not payload.get("user"):
                    raise Dian115Error("Dian115 登录成功响应缺少用户信息")
                self._save_auth_cookie(
                    self._session.cookies.get_dict().get("__Host-portal_token", "")
                )
                self._authenticated = True
                logger.debug("Dian115 HTTP 登录成功")
            except Dian115Error as error:
                # 如果是续期场景且当前 Token 仍有效，失败时继续沿用
                if token_soon and token_valid:
                    logger.warning(f"Dian115 自动续期失败，继续沿用当前 Token：{error}")
                    return
                is_cloudflare = (
                        error.code == "turnstile_failed"
                        or (error.status_code == 403 and not error.code)
                )
                if not is_cloudflare:
                    raise
                if not allow_browser_login:
                    raise Dian115Error(
                        "Dian115 登录触发 Cloudflare",
                        code="browser_login_forbidden",
                        status_code=error.status_code,
                    ) from error
                logger.debug("Dian115 登录触发 Cloudflare，切换 CloakBrowser")
                self._clear_portal_cookies()
                self._login_with_browser()

    def _request_json(
            self,
            method: str,
            api_path: str,
            current_path: str,
            retry_login: bool = True,
            retry_proof: bool = True,
            allow_browser_login: bool = True,
            **kwargs,
    ) -> Dict[str, Any]:
        with self._lock:
            if not self._authenticated:
                self._login(allow_browser_login=allow_browser_login)
            headers = self._authorized_headers(method, api_path, current_path)
            supplied_headers = dict(kwargs.pop("headers", {}) or {})
            headers.update(supplied_headers)
            response = self._raw_request(method, api_path, headers=headers, **kwargs)

            # 尝试持久化响应中站点可能下发的新 Token
            new_token = self._token_from_response(response)
            if new_token:
                old_token = self._session.cookies.get("__Host-portal_token") or ""
                if new_token != old_token:
                    self._save_auth_cookie(new_token)

            payload = self._payload(response)
            if (
                    response.status_code == 200
                    and payload.get("code") in {"ok", 0, "0", None}
            ):
                return payload
            code = str(payload.get("code") or "")

            # 挑战证明失效时重置并重试
            if retry_proof and code in self._PROOF_RETRY_CODES:
                logger.debug(
                    f"Dian115 挑战证明失效（{code}），重新握手后重试：{api_path}"
                )
                self._proof = None
                self._browser_session_expires_at = 0.0
                self._portal_browser_cookie = ""
                self._browser_private_key = ec.generate_private_key(ec.SECP256R1())
                return self._request_json(
                    method,
                    api_path,
                    current_path,
                    retry_login=retry_login,
                    retry_proof=False,
                    allow_browser_login=allow_browser_login,
                    **kwargs,
                )

            # 认证失效时自动重新登录重试一次（不拦截证明失效）
            if retry_login and code not in self._PROOF_RETRY_CODES and (
                    response.status_code in {401, 403}
                    or code in {
                        "unauthorized", "auth_required",
                        "invalid_token", "token_revoked", "no_token",
                    }
            ):
                logger.debug(
                    f"Dian115 登录态失效，刷新后重试：{api_path}"
                )
                self._clear_portal_cookies()
                self._authenticated = False
                self._proof = None
                self._browser_session_expires_at = 0.0
                self._portal_browser_cookie = ""
                self._login(allow_browser_login=allow_browser_login)
                return self._request_json(
                    method,
                    api_path,
                    current_path,
                    retry_login=False,
                    allow_browser_login=allow_browser_login,
                    **kwargs,
                )

            # 终极保底：若 Python 客户端签名仍受阻或突发 Cloudflare 拦截，走 CloakBrowser 无头浏览器通道
            if allow_browser_login and (
                    code in self._PROOF_RETRY_CODES
                    or response.status_code in {403, 429}
                    or self._is_challenge_response(response)
            ):
                logger.debug(
                    f"Dian115 Python 端请求受阻（code={code}, status={response.status_code}），"
                    f"启动 CloakBrowser 浏览器保底通道：{api_path}"
                )
                try:
                    return self._request_via_browser(
                        method=method,
                        api_path=api_path,
                        current_path=current_path,
                        params=kwargs.get("params"),
                        json_data=kwargs.get("json"),
                    )
                except Exception as browser_err:
                    logger.debug(f"Dian115 浏览器通道保底失败：{browser_err}")

            self._raise_response_error(response, payload)

    def _request_via_browser(
            self,
            method: str,
            api_path: str,
            current_path: str = "/",
            params: Optional[Dict[str, Any]] = None,
            json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="Dian115-BrowserFallback"
        )
        try:
            return executor.submit(
                asyncio.run,
                self._request_via_browser_async(
                    method, api_path, current_path, params, json_data
                ),
            ).result()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    async def _request_via_browser_async(
            self,
            method: str,
            api_path: str,
            current_path: str = "/",
            params: Optional[Dict[str, Any]] = None,
            json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from app.core.config import settings
        from cloakbrowser import launch_context_async
        from urllib.parse import urlencode

        url = urljoin(f"{self.base_url}/", api_path.lstrip("/"))
        if params:
            url = f"{url}?{urlencode(params)}"

        browser_options = {
            "headless": True,
            "proxy": self._browser_proxy(),
            "humanize": getattr(settings, "CLOAKBROWSER_HUMANIZE", True),
            "human_preset": "careful",
        }
        context = await launch_context_async(**browser_options)
        try:
            page = await context.new_page()
            token = self._session.cookies.get("__Host-portal_token")
            if token:
                await context.add_cookies([{
                    "name": "__Host-portal_token",
                    "value": token,
                    "domain": "m.dian115.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                }])
            target_page_url = urljoin(f"{self.base_url}/", current_path.lstrip("/"))
            await page.goto(target_page_url, wait_until="domcontentloaded", timeout=30000)

            fetch_script = """async ({ url, method, body }) => {
                const options = {
                    method: method,
                    headers: {
                        'accept': 'application/json, text/plain, */*'
                    }
                };
                if (body) {
                    options.headers['content-type'] = 'application/json';
                    options.body = JSON.stringify(body);
                }
                const resp = await window.fetch(url, options);
                const text = await resp.text();
                return { status: resp.status, text: text };
            }"""
            res = await page.evaluate(fetch_script, {"url": url, "method": method, "body": json_data})
            status = res.get("status")
            text = res.get("text") or "{}"
            try:
                data = json.loads(text)
            except Exception:
                data = {"raw": text}
            if status != 200 or (isinstance(data, dict) and data.get("code") not in {"ok", 0, "0", None}):
                raise Dian115Error(
                    f"浏览器保底请求返回异常: {text[:200]}",
                    code=str(data.get("code") or ""),
                    status_code=status,
                )
            logger.debug(f"Dian115 浏览器通道兜底成功：{api_path}")
            return data
        finally:
            await context.close()

    def request_json(
            self,
            method: str,
            api_path: str,
            current_path: str,
            allow_browser_login: bool = True,
            **kwargs,
    ) -> Dict[str, Any]:
        """执行带登录态和浏览器证明的门户 JSON 请求。"""
        return self._request_json(
            method,
            api_path,
            current_path,
            allow_browser_login=allow_browser_login,
            **kwargs,
        )

    def get_account_info(
            self, allow_browser_login: bool = True
    ) -> Dict[str, Any]:
        """读取当前 Dian115 账户及可用积分。"""
        payload = self.request_json(
            "GET",
            "/api/portal/me",
            "/me",
            allow_browser_login=allow_browser_login,
        )
        user = payload.get("user") if isinstance(payload, dict) else None
        if not isinstance(user, dict) or "points" not in user:
            raise Dian115Error(
                "Dian115 账户接口缺少积分字段", code="schema_changed"
            )
        try:
            points = int(user.get("points") or 0)
        except (TypeError, ValueError) as error:
            raise Dian115Error(
                "Dian115 账户积分格式异常", code="schema_changed"
            ) from error
        return {
            "name": str(
                user.get("nickname") or user.get("username")
                or user.get("email") or "Dian115 用户"
            ),
            "email": str(user.get("email") or ""),
            "username": str(user.get("username") or ""),
            "avatar": str(user.get("avatar_url") or ""),
            "points": max(0, points),
            "role": str(user.get("role") or ""),
            "is_vip": bool(user.get("vip")),
            "vip_until": str(user.get("vip_until") or ""),
            "unlock_count": max(0, int(payload.get("unlock_count") or 0)),
            "consecutive_signin": max(
                0, int(user.get("consecutive_signin") or 0)
            ),
            "created_at": str(user.get("created_at") or ""),
            "last_login_at": str(user.get("last_login_at") or ""),
        }

    @staticmethod
    def _game_item(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
        items = payload.get("items") if isinstance(payload, dict) else None
        item = items.get(key) if isinstance(items, dict) else None
        if not isinstance(item, dict):
            raise Dian115Error(
                f"Dian115 娱乐状态缺少 {key} 字段", code="schema_changed"
            )
        return item

    def get_game_status(self) -> Dict[str, Any]:
        """读取每日转盘次数；签到链路禁止触发浏览器登录。"""
        return self.request_json(
            "GET",
            "/api/portal/games/status",
            "/me/lottery",
            allow_browser_login=False,
        )

    def signin(self, mode: str = "normal") -> Dict[str, Any]:
        """通过门户签到接口执行普通或运气签到。"""
        normalized_mode = str(mode or "normal").strip().lower()
        if normalized_mode not in {"normal", "lucky"}:
            raise Dian115Error("Dian115 签到模式无效", code="invalid_mode")
        try:
            payload = self.request_json(
                "POST",
                "/api/portal/signin",
                "/me/signin",
                allow_browser_login=False,
                json={"mode": normalized_mode},
            )
        except Dian115Error as error:
            if error.code != "already_signed":
                raise
            return {
                "success": True,
                "already_checked_in": True,
                "status": "今日已签到",
                "message": "今日已签到",
                "mode": normalized_mode,
                "award_points": 0,
                "status_code": error.status_code,
                "error_code": error.code,
            }
        return {
            "success": True,
            "already_checked_in": False,
            "status": "签到成功",
            "message": str(payload.get("message") or "签到成功"),
            "mode": normalized_mode,
            "award_points": payload.get("award"),
            "new_balance": payload.get("new_balance"),
            "signin_days": payload.get("streak_after"),
            "lucky_tier": payload.get("lucky_tier"),
            "multiplier": payload.get("multiplier"),
            "status_code": 200,
            "error_code": "",
        }

    def run_lottery(self, target_count: int) -> Dict[str, Any]:
        """将幸运转盘补齐到当天目标次数，目标值硬限制为 20。"""
        target_plays = max(0, min(int(target_count or 0), 20))
        wheel_results = []
        wheel_error: Optional[Dian115Error] = None
        used_before = 0
        max_plays = 20
        play_count = 0
        if target_plays:
            wheel = self._game_item(self.get_game_status(), "daily_wheel")
            try:
                used_before = max(0, int(wheel.get("used_today") or 0))
                max_plays = max(
                    0, min(int(wheel.get("max_plays") or 0), 20)
                )
            except (TypeError, ValueError) as error:
                raise Dian115Error(
                    "Dian115 转盘次数格式异常", code="schema_changed"
                ) from error
            play_count = max(
                0, min(target_plays, max_plays) - used_before
            )
            for _ in range(play_count):
                try:
                    wheel_results.append(self.request_json(
                        "POST",
                        "/api/portal/lottery/wheel",
                        "/me/lottery",
                        allow_browser_login=False,
                    ))
                except Dian115Error as error:
                    wheel_error = error
                    break
        wheel_cost = 0
        wheel_award = 0
        wheel_vip_days = 0
        for item in wheel_results:
            prize = item.get("prize") if isinstance(item, dict) else None
            prize = prize if isinstance(prize, dict) else {}
            try:
                wheel_cost += max(0, int(item.get("cost") or 0))
                wheel_award += int(prize.get("points") or 0)
                wheel_vip_days += max(0, int(prize.get("vip_days") or 0))
            except (TypeError, ValueError):
                continue
        executed = len(wheel_results)
        success = wheel_error is None
        message = f"转盘 {executed}/{target_plays} 次"
        if target_plays and executed == 0 and used_before >= target_plays:
            message = f"今日转盘已完成 {used_before} 次"
        elif wheel_error:
            message = f"{message}，中断：{wheel_error}"
        balances = [
            item.get("new_balance")
            for item in wheel_results
            if isinstance(item, dict) and item.get("new_balance") is not None
        ]
        return {
            "success": success,
            "status": "转盘完成" if success else "转盘未完成",
            "message": message,
            "new_balance": balances[-1] if balances else None,
            "points_change": wheel_award - wheel_cost,
            "status_code": int(getattr(wheel_error, "status_code", 0) or 200),
            "error_code": str(getattr(wheel_error, "code", "") or ""),
            "target_count": target_plays,
            "max_plays": max_plays,
            "used_before": used_before,
            "planned": play_count,
            "executed": executed,
            "used_after": used_before + executed,
            "cost_points": wheel_cost,
            "award_points": wheel_award,
            "vip_days": wheel_vip_days,
        }
