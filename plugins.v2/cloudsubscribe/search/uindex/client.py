import html
import re
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from app.log import logger

from ..cloudflare import click_challenge_frame, is_cloudflare_challenge, launch_challenge_context
from ..http_client import (
    RequestGate,
    gated_idempotent_request,
    normalize_proxies,
    request_error_summary,
    requests,
)
from ...utils.cache import create_platform_ttl_cache


class UIndexError(RuntimeError):
    """UIndex 请求或解析失败。"""


_SIZE_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*(TB|GB|MB|KB|B)", re.IGNORECASE)
_MAGNET_REGEX = re.compile(r"magnet:\?xt=urn:btih:[a-zA-Z0-9]{32,40}[^\s\"'<>]*", re.IGNORECASE)
_HASH_REGEX = re.compile(r"urn:btih:([a-zA-Z0-9]{32,40})", re.IGNORECASE)


def parse_size_str(size_text: str) -> int:
    """解析字符串大小为字节数。"""
    match = _SIZE_REGEX.search(size_text or "")
    if not match:
        return 0
    val, unit = float(match.group(1)), match.group(2).upper()
    units = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }
    return int(val * units.get(unit, 1))


class UIndexClient:
    """通过 UIndex 检索磁力资源。"""

    DEFAULT_BASE_URL = "https://uindex.org"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(
            self,
            base_url: str = DEFAULT_BASE_URL,
            proxy: Optional[str] = None,
            timeout: int = 20,
            request_interval: float = 1.0,
            request_timeout: Optional[int] = None,
    ) -> None:
        self._raw_base_url = str(base_url or self.DEFAULT_BASE_URL).strip()
        self.base_url = self._raw_base_url.rstrip("/") or self.DEFAULT_BASE_URL
        self._proxy = str(proxy or "").strip()
        effective_timeout = request_timeout if request_timeout is not None else timeout
        self.timeout = max(5, int(effective_timeout or 20))
        self.request_interval = max(0.2, float(request_interval or 1.0))
        self._gate = RequestGate.shared(
            "UIndex",
            f"{self.base_url}|{self._proxy}",
            request_interval=self.request_interval,
            minimum_interval=0.2,
            serial_requests=False,
        )
        self._cache = create_platform_ttl_cache("uindex_search", ttl=1800, maxsize=500)
        self._cache_lock = threading.Lock()

    @property
    def proxy(self) -> str:
        return self._proxy

    def update_config(
            self,
            base_url: Optional[str] = None,
            proxy: Optional[str] = None,
            timeout: Optional[int] = None,
            request_interval: Optional[float] = None,
            request_timeout: Optional[int] = None,
    ) -> None:
        if base_url is not None:
            raw = str(base_url).strip()
            self._raw_base_url = raw or self.DEFAULT_BASE_URL
            self.base_url = self._raw_base_url.rstrip("/") or self.DEFAULT_BASE_URL
        if proxy is not None:
            self._proxy = str(proxy or "").strip()
        effective_timeout = request_timeout if request_timeout is not None else timeout
        if effective_timeout is not None:
            self.timeout = max(5, int(effective_timeout or 20))
        if request_interval is not None:
            self.request_interval = max(0.2, float(request_interval or 1.0))
        self._gate = RequestGate.shared(
            "UIndex",
            f"{self.base_url}|{self._proxy}",
            request_interval=self.request_interval,
            minimum_interval=0.2,
            serial_requests=False,
        )

    def _fetch_page_with_browser(self, url: str) -> str:
        """按需在独立纯净线程中通过 CloakBrowser 穿透 Cloudflare 盾并获取搜索页面 HTML。"""

        def _worker() -> str:
            import asyncio
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass

            context = launch_challenge_context(self._proxy)
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                started = time.monotonic()
                deadline = started + 30
                clicked = False
                while time.monotonic() < deadline:
                    try:
                        title = page.title()
                    except Exception:
                        page.wait_for_timeout(500)
                        continue

                    if "Just a moment" not in title:
                        try:
                            content = page.content()
                            if len(content) > 5000:
                                return content
                        except Exception:
                            page.wait_for_timeout(500)
                            continue

                    if not clicked:
                        clicked = click_challenge_frame(page)
                    page.wait_for_timeout(500)

                try:
                    final_content = page.content()
                    if "Just a moment" not in page.title():
                        return final_content
                except Exception:
                    pass
                raise TimeoutError("Cloudflare 验证等待超时")
            finally:
                try:
                    context.close()
                except Exception as err:
                    logger.debug(f"关闭 UIndex 浏览器上下文异常：{err}")

        result_holder = [None]
        error_holder = [None]

        def _runner():
            try:
                result_holder[0] = _worker()
            except BaseException as err:
                error_holder[0] = err

        thread = threading.Thread(target=_runner, name="UIndex-Cloak-Thread", daemon=True)
        thread.start()
        thread.join(timeout=35)
        if thread.is_alive():
            raise UIndexError("CloakBrowser 渲染执行超时")
        if error_holder[0] is not None:
            raise UIndexError(f"CloakBrowser 渲染页面失败：{error_holder[0]}") from error_holder[0]
        return result_holder[0]

    def search(self, query: str) -> List[Dict[str, Any]]:
        keyword = str(query or "").strip()
        if not keyword:
            return []
        cache_key = keyword.casefold()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return [dict(item) for item in cached]

        url = f"{self.base_url}/search.php?search={quote(keyword)}"
        proxies = normalize_proxies(self._proxy)

        # 1. 优先执行标准 HTTP 快速请求（不需要 CF 时零浏览器开销）
        is_cf_blocked = False
        page_html = ""
        try:
            response = gated_idempotent_request(
                self._gate,
                requests.request,
                "GET",
                url,
                headers=self._HEADERS,
                proxies=proxies,
                timeout=self.timeout,
            )
            status_code = getattr(response, "status_code", 0)
            page_text = getattr(response, "text", "") or ""

            # 智能判断是否受到 Cloudflare Managed Challenge 拦截
            is_cf_blocked = is_cloudflare_challenge(
                page_text, status_code, getattr(response, "headers", {})
            )

            if not is_cf_blocked:
                if status_code != 200:
                    raise UIndexError(f"UIndex 请求异常：HTTP {status_code}")
                page_html = page_text
        except requests.exceptions.RequestException as error:
            logger.debug(f"UIndex 直连请求异常：{request_error_summary(error)}，准备尝试浏览器渲染")
            is_cf_blocked = True

        # 2. 仅在检测到需要过 CF 盾时，才按需调起 CloakBrowser 浏览器过盾
        if is_cf_blocked:
            logger.info(f"UIndex 检测到 Cloudflare 盾防护，按需调用 CloakBrowser 浏览器过盾渲染：{keyword}")
            page_html = self._fetch_page_with_browser(url)

        results = self._parse_search_page(page_html)
        with self._cache_lock:
            self._cache[cache_key] = results
        return [dict(item) for item in results]

    def _parse_search_page(self, page_html: str) -> List[Dict[str, Any]]:
        """解析搜索列表 HTML。"""
        results = []
        if not page_html:
            return results

        # 匹配每一行 <tr>...</tr>
        row_regex = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
        for row_match in row_regex.finditer(page_html):
            row_content = row_match.group(1)
            # 必须包含磁力链接或带有 btih 的内容
            mag_match = _MAGNET_REGEX.search(row_content)
            if not mag_match:
                continue

            magnet_url = html.unescape(mag_match.group(0))
            hash_match = _HASH_REGEX.search(magnet_url)
            if not hash_match:
                continue
            info_hash = hash_match.group(1).upper()

            # 提取标题
            # 优先从详情链接文本或 title 属性提取
            title = ""
            title_match = re.search(r"<a[^>]+href=[\"'][^\"']*details\.php[^\"']*[\"'][^>]*>(.*?)</a>", row_content,
                                    re.IGNORECASE | re.DOTALL)
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
            if not title:
                # 尝试从 magnet 的 dn 参数提取
                dn_match = re.search(r"dn=([^&]+)", magnet_url)
                if dn_match:
                    from urllib.parse import unquote
                    title = unquote(dn_match.group(1))

            if not title:
                title = f"UIndex 资源 {info_hash[:8]}"

            # 提取文件大小
            size_bytes = parse_size_str(row_content)

            # 提取做种数
            seeders = 0
            seed_match = re.search(r"class=[\"'][^\"']*seeders?[^\"']*[\"'][^>]*>(\d+)</td>", row_content,
                                   re.IGNORECASE)
            if seed_match:
                seeders = int(seed_match.group(1))

            results.append({
                "url": magnet_url,
                "title": html.unescape(title).strip(),
                "size": size_bytes,
                "seeders": seeders,
                "info_hash": info_hash,
                "resource_type": "magnet",
                "source": "uindex",
                "source_url": f"{self.base_url}/search.php",
            })

        return results

    def clear_cache(self) -> int:
        with self._cache_lock:
            count = len(self._cache)
            self._cache.clear()
            return count
