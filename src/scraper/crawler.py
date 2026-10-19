"""Pipelined crawl: each listing page starts fetching its products as soon as it is parsed."""

import asyncio
import logging
from urllib.parse import urljoin, urlparse

from scraper import config, parsers, variants
from scraper.client import Fetcher
from scraper.models import Product

log = logging.getLogger(__name__)


class Crawler:
    """Failed product and listing pages are logged and counted; home and category are fatal."""

    def __init__(self, fetcher: Fetcher):
        self._fetcher = fetcher
        self._seen: set[str] = set()
        self._products: dict[str, list[Product]] = {}
        self._failed: list[str] = []

    async def run(self) -> tuple[list[Product], int]:
        """Returns the products and the number of failed pages."""
        home = urljoin(config.BASE_URL, config.STATIC_ROOT)
        categories = parsers.parse_category_links(await self._fetcher.get(home), home)
        await asyncio.gather(*(self._crawl_category(c) for c in categories))
        log.info("found %d products", len(self._seen))
        # (len, url) sorts /product/9 before /product/10, keeping output stable between runs
        urls = sorted(self._products, key=lambda u: (len(u), u))
        return [p for u in urls for p in self._products[u]], len(self._failed)

    async def _crawl_category(self, url: str) -> None:
        html = await self._fetcher.get(url)
        subs = parsers.parse_subcategory_links(html, url)
        if subs:
            await asyncio.gather(*(self._crawl_leaf(s) for s in subs))
        else:
            await self._crawl_leaf(url, html)

    async def _crawl_leaf(self, url: str, html: str | None = None) -> None:
        html = html if html is not None else await self._fetch(url)
        if html is None:  # no pager without page 1
            return
        last = parsers.parse_last_page(html)
        log.info("%s: %d pages", urlparse(url).path.removeprefix(config.STATIC_ROOT), last)
        await asyncio.gather(
            self._scan_listing(url, html),
            *(self._crawl_page(f"{url}?page={n}") for n in range(2, last + 1)),
        )

    async def _crawl_page(self, url: str) -> None:
        html = await self._fetch(url)
        if html is not None:
            await self._scan_listing(url, html)

    async def _scan_listing(self, url: str, html: str) -> None:
        found = parsers.parse_listing(html, url)
        if not found:
            log.warning("listing page %s has no products; pager misread?", url)
        new = [u for u in found if u not in self._seen]
        self._seen.update(new)
        await asyncio.gather(*(self._scrape_product(u) for u in new))

    async def _scrape_product(self, url: str) -> None:
        try:
            raw = parsers.parse_product(await self._fetcher.get(url), url)
            self._products[url] = variants.expand(raw)
        except Exception as e:
            log.error("failed to scrape %s: %r", url, e)
            self._failed.append(url)

    async def _fetch(self, url: str) -> str | None:
        try:
            return await self._fetcher.get(url)
        except Exception as e:
            log.error("failed to fetch %s: %r", url, e)
            self._failed.append(url)
            return None


async def crawl(fetcher: Fetcher) -> tuple[list[Product], int]:
    return await Crawler(fetcher).run()
