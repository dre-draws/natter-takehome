import asyncio
import logging

import pytest
from helpers import ROOT, listing, page, product, swatch

from scraper.crawler import Crawler


class FakeFetcher:
    """Serves `pages` by URL, records every request, and fails on `broken` or unknown URLs."""

    def __init__(self, pages: dict, broken: tuple = ()):
        self.pages = pages
        self.broken = set(broken)
        self.requested: list[str] = []

    async def get(self, url: str) -> str:
        self.requested.append(url)
        if url in self.broken or url not in self.pages:
            raise RuntimeError(f"boom: {url}")
        return self.pages[url]


def make(pages: dict | None = None, broken: tuple = ()):
    fetcher = FakeFetcher(pages or {}, broken)
    return Crawler(fetcher), fetcher  # type: ignore[arg-type]


def p(i: int) -> str:
    return f"{ROOT}/product/{i}"


def product_pages(*ids: int) -> dict:
    return {p(i): product(f"P{i}", f"{i}.00") for i in ids}


LEAF = f"{ROOT}/cat/leaf"


# --- _fetch ---------------------------------------------------------------------------------


def test_fetch_returns_the_page():
    c, _ = make({LEAF: "html"})
    assert asyncio.run(c._fetch(LEAF)) == "html"
    assert c._failed == []


def test_fetch_failure_is_counted_and_returns_none(caplog):
    c, _ = make(broken=(LEAF,))
    assert asyncio.run(c._fetch(LEAF)) is None
    assert c._failed == [LEAF]
    assert "failed to fetch" in caplog.text


# --- _scrape_product ------------------------------------------------------------------------


def test_scrape_product_stores_one_entry_per_hdd_size():
    c, _ = make({p(1): product("P1", "100.00", swatch(128) + swatch(512))})
    asyncio.run(c._scrape_product(p(1)))
    assert [(x.name, float(x.price)) for x in c._products[p(1)]] == [
        ("P1 128 GB", 100.0),
        ("P1 512 GB", 140.0),
    ]


def test_scrape_product_with_unparseable_page_is_counted_not_stored():
    c, _ = make({p(1): page("nothing useful")})
    asyncio.run(c._scrape_product(p(1)))
    assert c._products == {} and c._failed == [p(1)]


def test_scrape_product_with_unknown_hdd_size_is_counted_not_stored():
    c, _ = make({p(1): product("P1", "1.00", swatch(2048))})
    asyncio.run(c._scrape_product(p(1)))
    assert c._products == {} and c._failed == [p(1)]


def test_scrape_product_fetch_failure_is_counted():
    c, _ = make(broken=(p(1),))
    asyncio.run(c._scrape_product(p(1)))
    assert c._failed == [p(1)]


# --- _scan_listing --------------------------------------------------------------------------


def test_scan_listing_skips_products_already_seen():
    c, f = make(product_pages(1, 2))
    c._seen.add(p(1))
    asyncio.run(c._scan_listing(LEAF, listing([1, 2], last=1)))
    assert f.requested == [p(2)]
    assert set(c._products) == {p(2)}


def test_scan_listing_marks_new_products_as_seen():
    c, _ = make(product_pages(1, 2))
    asyncio.run(c._scan_listing(LEAF, listing([1, 2], last=1)))
    assert c._seen == {p(1), p(2)}


def test_scan_listing_with_no_products_warns_and_fetches_nothing(caplog):
    c, f = make()
    with caplog.at_level(logging.WARNING):
        asyncio.run(c._scan_listing(LEAF, page("")))
    assert f.requested == []
    assert "no products" in caplog.text


# --- _crawl_page ----------------------------------------------------------------------------


def test_crawl_page_scans_the_listing_it_fetched():
    c, _ = make({LEAF: listing([1], last=1), **product_pages(1)})
    asyncio.run(c._crawl_page(LEAF))
    assert set(c._products) == {p(1)}


def test_crawl_page_failure_is_counted_and_scans_nothing():
    c, f = make(broken=(LEAF,))
    asyncio.run(c._crawl_page(LEAF))
    assert c._failed == [LEAF]
    assert f.requested == [LEAF]


# --- _crawl_leaf ----------------------------------------------------------------------------


def test_crawl_leaf_fetches_pages_two_to_last_but_not_page_one_again():
    pages = {
        f"{LEAF}?page=2": listing([2], last=3),
        f"{LEAF}?page=3": listing([3], last=3),
        **product_pages(1, 2, 3),
    }
    c, f = make(pages)
    asyncio.run(c._crawl_leaf(LEAF, listing([1], last=3)))
    assert LEAF not in f.requested
    assert {f"{LEAF}?page=2", f"{LEAF}?page=3"} <= set(f.requested)
    assert set(c._products) == {p(1), p(2), p(3)}


def test_crawl_leaf_fetches_page_one_itself_when_not_given_html():
    c, f = make({LEAF: listing([1], last=1), **product_pages(1)})
    asyncio.run(c._crawl_leaf(LEAF))
    assert f.requested[0] == LEAF
    assert set(c._products) == {p(1)}


def test_crawl_leaf_without_page_one_gives_up_on_the_whole_leaf(caplog):
    c, f = make(broken=(LEAF,))
    with caplog.at_level(logging.WARNING):
        asyncio.run(c._crawl_leaf(LEAF))
    assert f.requested == [LEAF]  # no pager, so no way to know which other pages exist
    assert c._failed == [LEAF]
    assert "no products" not in caplog.text  # it stopped; it did not scan an empty page


def test_crawl_leaf_one_bad_page_does_not_stop_the_others():
    pages = {f"{LEAF}?page=3": listing([3], last=3), **product_pages(1, 3)}
    c, _ = make(pages, broken=(f"{LEAF}?page=2",))
    asyncio.run(c._crawl_leaf(LEAF, listing([1], last=3)))
    assert set(c._products) == {p(1), p(3)}
    assert c._failed == [f"{LEAF}?page=2"]


# --- _crawl_category ------------------------------------------------------------------------


def test_category_with_subcategories_ignores_its_own_featured_products():
    cat = f"{ROOT}/cat"
    html = page(f'<a class="subcategory-link" href="{LEAF}">l</a>') + listing([99], last=1)
    c, f = make({cat: html, LEAF: listing([1], last=1), **product_pages(1, 99)})
    asyncio.run(c._crawl_category(cat))
    assert p(99) not in f.requested
    assert set(c._products) == {p(1)}


def test_category_without_subcategories_lists_products_itself():
    cat = f"{ROOT}/flat"
    c, _ = make({cat: listing([1], last=1), **product_pages(1)})
    asyncio.run(c._crawl_category(cat))
    assert set(c._products) == {p(1)}


def test_category_fetch_failure_is_fatal():
    c, _ = make(broken=(f"{ROOT}/cat",))
    with pytest.raises(RuntimeError):
        asyncio.run(c._crawl_category(f"{ROOT}/cat"))


# --- run ------------------------------------------------------------------------------------


def home_with(*categories: str) -> str:
    return page("".join(f'<a class="category-link" href="{c}">c</a>' for c in categories))


def test_run_orders_products_numerically_by_url():
    cat = f"{ROOT}/flat"
    pages = {ROOT: home_with(cat), cat: listing([100, 10, 9], last=1), **product_pages(9, 10, 100)}
    c, _ = make(pages)
    products, failed = asyncio.run(c.run())
    assert [x.name for x in products] == ["P9", "P10", "P100"]
    assert failed == 0


def test_run_home_page_failure_is_fatal():
    c, _ = make(broken=(ROOT,))
    with pytest.raises(RuntimeError):
        asyncio.run(c.run())


def test_run_ignores_featured_products_on_the_home_page():
    cat = f"{ROOT}/flat"
    pages = {ROOT: home_with(cat) + listing([99], last=1), cat: listing([1], last=1)}
    c, f = make({**pages, **product_pages(1, 99)})
    products, _ = asyncio.run(c.run())
    assert [x.name for x in products] == ["P1"]
    assert p(99) not in f.requested
