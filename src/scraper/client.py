import asyncio
import logging
from typing import Self
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx

from scraper import config

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class Fetcher:
    def __init__(self, concurrency: int, transport: httpx.AsyncBaseTransport | None = None):
        self._sem = asyncio.Semaphore(concurrency)
        self._robots: RobotFileParser | None = None
        self._crawl_delay = 0.0
        self._next_start = 0.0
        self._pace_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            headers={"User-Agent": config.USER_AGENT},
            timeout=config.TIMEOUT_SECONDS,
            follow_redirects=True,
            http2=True,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def load_robots(self) -> None:
        """Enforce robots.txt on every later request. A 4xx means no rules; anything else that
        stops us reading the file raises, so we never crawl blind."""
        try:
            text = await self.get(urljoin(config.BASE_URL, "/robots.txt"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 and e.response.status_code != 429:
                return
            raise
        self._robots = RobotFileParser()
        self._robots.parse(text.splitlines())
        self._crawl_delay = float(self._robots.crawl_delay(config.USER_AGENT) or 0)
        log.info("robots.txt loaded (crawl-delay %.1fs)", self._crawl_delay)

    async def _pace(self) -> None:
        if not self._crawl_delay:
            return
        async with self._pace_lock:
            loop = asyncio.get_running_loop()
            await asyncio.sleep(max(0.0, self._next_start - loop.time()))
            self._next_start = loop.time() + self._crawl_delay

    async def get(self, url: str) -> str:
        if self._robots and not self._robots.can_fetch(config.USER_AGENT, url):
            raise RobotsDisallowed(url)
        for attempt in range(1, config.MAX_ATTEMPTS + 1):
            try:
                await self._pace()
                async with self._sem:
                    resp = await self._client.get(url)
                if resp.status_code < 500 and resp.status_code != 429:
                    resp.raise_for_status()
                    return resp.text
                err: Exception = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            except httpx.TransportError as e:
                err = e
            if attempt == config.MAX_ATTEMPTS:
                raise err
            delay = config.BACKOFF_SECONDS * 2 ** (attempt - 1)
            log.warning("GET %s failed (%s), retry %d in %.1fs", url, err, attempt, delay)
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")
