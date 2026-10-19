import asyncio
import time

import httpx
import pytest

from scraper import config
from scraper.client import Fetcher, RobotsDisallowed

ROBOTS = "User-agent: *\nDisallow: /private/\n"


def fetcher(handler, concurrency=4):
    return Fetcher(concurrency, transport=httpx.MockTransport(handler))


def serve(robots_response):
    def handler(req):
        if req.url.path == "/robots.txt":
            return robots_response
        return httpx.Response(200, text="ok")

    return handler


def get_all(handler, *paths):
    async def go():
        async with fetcher(handler) as f:
            await f.load_robots()
            return [await f.get(f"https://webscraper.io{p}") for p in paths]

    return asyncio.run(go())


def test_disallowed_path_is_refused_and_allowed_path_is_fetched():
    handler = serve(httpx.Response(200, text=ROBOTS))
    assert get_all(handler, "/public/a") == ["ok"]
    with pytest.raises(RobotsDisallowed):
        get_all(handler, "/private/a")


def test_missing_robots_means_no_restrictions():
    assert get_all(serve(httpx.Response(404)), "/private/a") == ["ok"]


def test_unreadable_robots_stops_the_run(monkeypatch):
    monkeypatch.setattr(config, "BACKOFF_SECONDS", 0)
    with pytest.raises(httpx.HTTPStatusError):
        get_all(serve(httpx.Response(503)), "/public/a")


def test_crawl_delay_spaces_requests_even_when_concurrent():
    async def go():
        async with fetcher(serve(httpx.Response(200, text="User-agent: *\nCrawl-delay: 2\n"))) as f:
            await f.load_robots()
            assert f._crawl_delay == 2.0
            f._crawl_delay = 0.05  # same code path, without waiting seconds in a test
            start = time.perf_counter()
            await asyncio.gather(*(f.get(f"https://webscraper.io/p/{i}") for i in range(4)))
            return time.perf_counter() - start

    assert asyncio.run(go()) >= 0.15  # 4 requests, 3 gaps of 0.05s
