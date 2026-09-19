import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from app.log import logger

from ..cloudflare import click_challenge_frame, launch_challenge_context


class HDHavenTurnstile:
    _HTML = """<!doctype html><html><head><meta charset="utf-8">
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" defer></script>
    </head><body><div id="verification" style="margin:80px"></div></body></html>"""

    _START = """({siteKey, action}) => {
        const previous = window.hdhavenVerification;
        if (previous?.widget !== undefined) window.turnstile.remove(previous.widget);
        const state = {token: '', error: '', interactive: false};
        window.hdhavenVerification = state;
        state.widget = window.turnstile.render('#verification', {
            sitekey: siteKey, action: action || 'login', theme: 'light', language: 'zh-CN',
            appearance: 'interaction-only', execution: 'execute',
            'response-field': false,
            callback: token => { state.token = token; },
            'error-callback': code => { state.error = String(code || 'verification_failed'); },
            'expired-callback': () => { state.error = 'token_expired'; },
            'timeout-callback': () => { state.error = 'verification_timeout'; },
            'before-interactive-callback': () => { state.interactive = true; }
        });
        window.turnstile.execute(state.widget);
    }"""

    def __init__(self, base_url: str = "https://hdhaven.com", proxy: Any = None):
        self._base_url = base_url.rstrip("/")
        self._proxy = proxy
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="HDHaven-Turnstile")
        self._context = None
        self._page = None

    def token(self, site_key: str, action: str = "login", timeout: int = 30) -> str:
        if not site_key:
            raise ValueError("HDHaven 求解 Turnstile 需要有效的 site_key")
        return self._executor.submit(self._token, str(site_key).strip(), action).result(timeout=timeout)

    def _prepare_page(self) -> None:
        if self._page is not None and not self._page.is_closed():
            return
        self._close_browser()
        self._context = launch_challenge_context(self._proxy)
        self._page = self._context.new_page()
        url = f"{self._base_url}/login"
        self._page.route(url, lambda route: route.fulfill(
            status=200, content_type="text/html", body=self._HTML
        ))
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._page.wait_for_function(
            "() => typeof window.turnstile?.render === 'function'", timeout=30000
        )

    def _token(self, site_key: str, action: str) -> str:
        started = time.monotonic()
        deadline = started + 45
        reused = self._page is not None and not self._page.is_closed()
        try:
            self._prepare_page()
            self._page.evaluate(self._START, {"siteKey": site_key, "action": action})
            clicked = False
            while time.monotonic() < deadline:
                state = self._page.evaluate("() => window.hdhavenVerification || {}")
                if state.get("token"):
                    token = str(state["token"])
                    self._page.evaluate("""() => {
                        try {
                            if (window.hdhavenVerification?.widget !== undefined) {
                                window.turnstile.remove(window.hdhavenVerification.widget);
                            }
                        } catch (e) {}
                        window.hdhavenVerification = null;
                    }""")
                    logger.debug(
                        f"HDHaven Turnstile 就绪：action={action}，复用={reused}，"
                        f"耗时={time.monotonic() - started:.2f}s"
                    )
                    return token
                if state.get("error"):
                    raise RuntimeError(f"Cloudflare Turnstile 验证失败：{state['error']}")
                if state.get("interactive") and not clicked:
                    clicked = click_challenge_frame(self._page)
                self._page.wait_for_timeout(200)
            raise TimeoutError("Cloudflare Turnstile 验证超时")
        except Exception:
            try:
                self._close_browser()
            except Exception as error:
                logger.debug(f"HDHaven 关闭验证浏览器失败：{type(error).__name__}")
            raise

    def _close_browser(self) -> None:
        context, self._context = self._context, None
        self._page = None
        if context is not None:
            try:
                context.close()
            except Exception:
                pass

    def close(self) -> None:
        """关闭求解器与浏览器进程。"""
        try:
            self._executor.submit(self._close_browser).result(timeout=5)
        except Exception:
            pass
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)
