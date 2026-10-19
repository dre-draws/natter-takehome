"""Pipelined crawl: each listing page starts fetching its products as soon as it is parsed."""

import asyncio
import logging
from urllib.parse import urljoin, urlparse

from scraper import config, parsers, variants
from scraper.client import Fetcher
from scraper.models import Product

log = logging.getLogger(__name__)


async def crawl(fetcher: Fetcher) -> tuple[list[Product], int]:
    """Returns the products and the number of failed pages.

    Failed product and listing pages are logged and counted; home and category pages are fatal."""
    seen: set[str] = set()
    products: dict[str, list[Product]] = {}
    failed: list[str] = []

    async def fetch(url: str) -> str | None:
        try:
            return await fetcher.get(url)
        except Exception as e:
            log.error("failed to fetch %s: %r", url, e)
            failed.append(url)
            return None

    async def product(url: str) -> None:
        try:
            products[url] = variants.expand(parsers.parse_product(await fetcher.get(url), url))
        except Exception as e:
            log.error("failed to scrape %s: %r", url, e)
            failed.append(url)

    async def listing_page(url: str, html: str) -> None:
        found = parsers.parse_listing(html, url)
        if not found:
            log.warning("listing page %s has no products; pager misread?", url)
        new = [u for u in found if u not in seen]
        seen.update(new)
        await asyncio.gather(*(product(u) for u in new))

    async def more_page(url: str) -> None:
        html = await fetch(url)
        if html is not None:
            await listing_page(url, html)

    async def leaf(url: str, html: str | None = None) -> None:
        html = html if html is not None else await fetch(url)
        if html is None:  # no pager without page 1
            return
        last = parsers.parse_last_page(html)
        log.info("%s: %d pages", urlparse(url).path.removeprefix(config.STATIC_ROOT), last)
        await asyncio.gather(
            listing_page(url, html), *(more_page(f"{url}?page={n}") for n in range(2, last + 1))
        )

    async def category(url: str) -> None:
        html = await fetcher.get(url)
        subs = parsers.parse_subcategory_links(html, url)
        if subs:
            await asyncio.gather(*(leaf(s) for s in subs))
        else:
            await leaf(url, html)

    home = urljoin(config.BASE_URL, config.STATIC_ROOT)
    categories = parsers.parse_category_links(await fetcher.get(home), home)
    await asyncio.gather(*(category(c) for c in categories))
    log.info("found %d products", len(seen))
    # (len, url) sorts /product/9 before /product/10, keeping output stable between runs
    ordered = [p for u in sorted(products, key=lambda u: (len(u), u)) for p in products[u]]
    return ordered, len(failed)
