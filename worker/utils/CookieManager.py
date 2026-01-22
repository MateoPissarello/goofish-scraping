import asyncio
import logging
import time
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_COOKIE_AGE = 600  # 10 minutos


class CookieManager:
    def __init__(
        self,
        fetch_cookies: Callable[[str, bool], Awaitable[dict]],
        use_proxy: bool,
    ):
        self._fetch_cookies = fetch_cookies
        self.use_proxy = use_proxy
        self._cookies = None
        self._lock = asyncio.Lock()

    async def ensure(self, url: str) -> dict:
        if (
            self._cookies is None
            or time.time() - self._cookies["fetched_at"] > MAX_COOKIE_AGE
        ):
            async with self._lock:
                if (
                    self._cookies is None
                    or time.time() - self._cookies["fetched_at"] > MAX_COOKIE_AGE
                ):
                    cookies = await self._fetch_cookies(url, use_proxy=self.use_proxy)
                    self._cookies = {
                        "value": cookies,
                        "fetched_at": time.time(),
                    }
        return self._cookies["value"]

    async def refresh(self, url: str) -> dict:
        async with self._lock:
            logger.info("Refrescando cookies...")
            cookies = await self._fetch_cookies(url, use_proxy=self.use_proxy)
            self._cookies = {
                "value": cookies,
                "fetched_at": time.time(),
            }
        return self._cookies["value"]
