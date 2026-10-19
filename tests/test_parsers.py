from decimal import Decimal
from pathlib import Path

import pytest

from scraper import parsers

FIX = Path(__file__).parent / "fixtures"
BASE = "https://webscraper.io/test-sites/e-commerce/static"


def read(name: str) -> str:
    return (FIX / name).read_text()


def test_listing_urls_are_absolute():
    urls = parsers.parse_listing(read("listing_laptops_p1.html"), BASE + "/computers/laptops")
    assert len(urls) == 6
    assert urls[0] == BASE + "/product/31"


def test_last_page_read_from_windowed_pager():
    assert parsers.parse_last_page(read("listing_laptops_p1.html")) == 20


def test_last_page_defaults_to_one_without_pager():
    assert parsers.parse_last_page("<html></html>") == 1


def test_laptop_product_with_hdd_swatches():
    p = parsers.parse_product(read("product_laptop.html"), "u")
    assert (p.name, p.price) == ("Packard 255 G2", Decimal("416.99"))
    assert p.hdd_sizes == [128, 256, 512]  # 1024 is disabled -> out of stock
    assert p.colors == []


def test_phone_colours_exclude_placeholder():
    p = parsers.parse_product(read("product_phone_colors.html"), "u")
    assert p.name == "Nokia 123"
    assert p.colors == ["Gold", "White", "Black"]
    assert p.hdd_sizes == []


def test_missing_selector_fails_loudly():
    with pytest.raises(parsers.ParseError):
        parsers.parse_product("<html></html>", "u")
