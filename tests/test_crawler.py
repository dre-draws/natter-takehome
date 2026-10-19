import asyncio

import httpx
import pytest

from scraper import config
from scraper.client import Fetcher
from scraper.crawler import crawl

ROOT = "https://webscraper.io" + config.STATIC_ROOT


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(config, "BACKOFF_SECONDS", 0)


def page(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def product(name: str, price: str, swatches: str = "") -> str:
    return page(
        f'<div class="caption"><h4 itemprop="offers"><span itemprop="price">${price}</span></h4>'
        f'<h4 itemprop="name">{name}</h4><p itemprop="description">d</p></div>{swatches}'
    )


def swatch(size: int) -> str:
    return f'<button class="swatch" value="{size}">{size}</button>'


def listing(ids: list, last: int) -> str:
    links = "".join(f'<a class="title" href="{config.STATIC_ROOT}/product/{i}">x</a>' for i in ids)
    pager = f'<ul class="pagination"><a class="page-link" href="?page={last}">{last}</a></ul>'
    return page(links + (pager if last > 1 else ""))


def products_site(ids: list) -> dict:
    return {f"{ROOT}/product/{i}": product(f"P{i}", f"{i}.00") for i in ids}


SITE = {
    ROOT: page(f'<a class="category-link" href="{ROOT}/cat">c</a>'),
    f"{ROOT}/cat": page(f'<a class="subcategory-link" href="{ROOT}/cat/leaf">l</a>'),
    f"{ROOT}/cat/leaf": listing([1, 2], last=3),
    f"{ROOT}/cat/leaf?page=2": listing([3], last=3),
    f"{ROOT}/cat/leaf?page=3": listing([2, 4], last=3),  # 2 repeats: must be deduped
    **products_site([1, 2, 3, 4]),
}


def run(site: dict, broken: dict = None):
    """Crawl `site`; `broken` maps a URL suffix to the status code to serve instead."""
    broken = broken or {}

    def handler(req):
        url = str(req.url)
        for suffix, status in broken.items():
            if url.endswith(suffix):
                return httpx.Response(status)
        return httpx.Response(200, text=site[url]) if url in site else httpx.Response(404)

    async def go():
        async with Fetcher(4, transport=httpx.MockTransport(handler)) as f:
            return await crawl(f)

    return asyncio.run(go())


def test_crawl_follows_pagination_and_dedupes():
    products, failed = run(SITE)
    assert [p.name for p in products] == ["P1", "P2", "P3", "P4"]
    assert failed == 0


def test_category_without_subcategories_lists_products_itself():
    site = {
        ROOT: page(f'<a class="category-link" href="{ROOT}/flat">c</a>'),
        f"{ROOT}/flat": listing([1, 2], last=1),
        **products_site([1, 2]),
    }
    products, failed = run(site)
    assert [p.name for p in products] == ["P1", "P2"] and failed == 0


def test_failed_product_is_counted_not_swallowed():
    products, failed = run(SITE, broken={"/product/3": 404})
    assert len(products) == 3 and failed == 1


def test_failed_listing_page_is_counted_and_the_rest_survives():
    products, failed = run(SITE, broken={"page=2": 500})
    assert [p.name for p in products] == ["P1", "P2", "P4"] and failed == 1


def test_failed_first_listing_page_loses_that_leaf_but_not_the_run():
    products, failed = run(SITE, broken={"/cat/leaf": 500})
    assert products == [] and failed == 1


def test_unknown_hdd_size_fails_that_product_only():
    site = {**SITE, f"{ROOT}/product/1": product("P1", "1.00", swatch(128) + swatch(2048))}
    products, failed = run(site)
    assert [p.name for p in products] == ["P2", "P3", "P4"] and failed == 1


def test_hdd_products_are_expanded():
    site = {**SITE, f"{ROOT}/product/1": product("P1", "100.00", swatch(128) + swatch(256))}
    products, _ = run(site)
    assert [(p.name, float(p.price)) for p in products[:2]] == [
        ("P1 128 GB", 100.0),
        ("P1 256 GB", 120.0),
    ]


def test_transient_5xx_is_retried():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else httpx.Response(200, text="ok")

    async def go():
        async with Fetcher(1, transport=httpx.MockTransport(handler)) as f:
            return await f.get(ROOT)

    assert asyncio.run(go()) == "ok"
