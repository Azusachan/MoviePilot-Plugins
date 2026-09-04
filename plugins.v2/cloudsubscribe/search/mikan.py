"""Mikan public search, with explicit magnets and conservative title matching."""

import re
import time
from threading import RLock
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.log import logger
from .magnet import media_titles, normalize_magnets
from .matching import title_matches, unique_texts, extract_season
from ..core.search import SearchCapability, SearchPolicy, SearchProvider


def release_matches(title, expected, season):
    explicit_season = extract_season(title)
    if explicit_season and season and explicit_season != season:
        return False
    if season and season > 1 and not explicit_season:
        return False
    clean = re.sub(r"^(?:\s*\[[^\]]*\]\s*)+", "", title)
    clean = re.split(r"\s*\[|\s+-\s+\d|\s+\(\d{2}", clean, maxsplit=1)[0]
    return any(title_matches(part.strip(), expected) for part in clean.split(" / "))


def parse_rows(html, base_url):
    results = []
    seen = set()
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("tr"):
        episode = row.select_one('a[href*="/Home/Episode/"]')
        magnet = row.select_one('[data-clipboard-text^="magnet:"], [data-magnet^="magnet:"], a[href^="magnet:"]')
        if not episode or not magnet:
            continue
        title = episode.get_text(" ", strip=True)
        uri = magnet.get("data-clipboard-text") or magnet.get("data-magnet") or magnet["href"]
        xt = parse_qs(urlparse(uri).query).get("xt", [""])[0]
        if not re.fullmatch(r"urn:btih:(?:[a-fA-F0-9]{40}|[A-Z2-7a-z]{32})", xt):
            continue
        key = xt.lower()
        if key in seen or not title:
            continue
        seen.add(key)
        results.append({
            "id": "mikan-" + key.rsplit(":", 1)[-1],
            "title": title,
            "url": uri + ("&dn=" + quote(title) if "dn" not in parse_qs(urlparse(uri).query) else ""),
            "resource_type": "magnet",
            "source_url": urljoin(base_url, episode["href"]),
        })
    return results


class MikanSearchService:
    def __init__(self, config=None, proxy=None):
        config = config or {}
        self.base_url = str(config.get("mikan_base_url") or "https://mikanani.me").rstrip("/")
        if urlparse(self.base_url).scheme not in {"http", "https"}:
            raise ValueError("蜜柑服务地址必须为 HTTP(S)")
        self.limit = max(1, min(int(config.get("mikan_result_limit") or 80), 200))
        self.timeout = max(5, min(int(config.get("mikan_timeout") or 30), 60))
        self.interval = max(1, min(float(config.get("mikan_request_interval") or 2), 30))
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self.lock = RLock()
        self.last_request = 0
        self.cache = {}

    def _rows(self, keyword):
        with self.lock:
            cached = self.cache.get(keyword)
            if cached and time.monotonic() - cached[0] < 300:
                return cached[1]
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            response = requests.get(
                self.base_url + "/Home/Search", params={"searchstr": keyword},
                timeout=self.timeout, proxies=self.proxy,
                headers={"User-Agent": "MoviePilot-CloudSubscribe-Mikan/1.0"},
            )
            response.raise_for_status()
            rows = parse_rows(response.text, self.base_url)
            if not rows and "<table" not in response.text.lower():
                raise ValueError("蜜柑未返回搜索结果表格，可能为验证页或页面结构变化")
            if len(self.cache) >= 128:
                self.cache.pop(next(iter(self.cache)))
            self.cache[keyword] = (time.monotonic(), rows)
            return rows

    def search(self, query):
        titles = unique_texts([getattr(query.subscribe, "name", "")] + media_titles(query.mediainfo))
        results = []
        for keyword in titles[:3]:
            rows = self._rows(keyword)
            matched = [row for row in rows if release_matches(row["title"], titles, query.season)]
            logger.info(f"[MIKAN] 关键词={keyword}，返回={len(rows)}，标题匹配={len(matched)}")
            results.extend(matched)
        normalized = normalize_magnets(results, "mikan")
        limit = min(self.limit, query.result_limit) if query.result_limit else self.limit
        logger.info(f"[MIKAN] 去重后候选={len(normalized)}，返回上限={limit}")
        return normalized[:limit]

    def clear_cache(self):
        with self.lock:
            count = len(self.cache)
            self.cache.clear()
            return count


def create_mikan_provider(config=None, proxy=None):
    service = MikanSearchService(config, proxy)
    return SearchProvider(
        key="mikan", name="蜜柑", resource_types=frozenset({"magnet"}),
        services={SearchCapability.RESOURCE_SEARCH: service, SearchCapability.CACHE_MAINTENANCE: service},
        policy=SearchPolicy(cache_context={"base_url": service.base_url, "limit": service.limit}),
    )
