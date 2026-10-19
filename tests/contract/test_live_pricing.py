"""Clicks every enabled HDD swatch in a real browser and compares the rendered price with
`variants.expand`. Run with: pytest -m contract"""

import re
from decimal import Decimal

import pytest

from scraper import config
from scraper.models import RawProduct
from scraper.variants import expand

pytestmark = pytest.mark.contract

SAMPLE_PRODUCT_IDS = [31, 60, 114, 140]


@pytest.fixture(scope="module")
def page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


@pytest.mark.parametrize("product_id", SAMPLE_PRODUCT_IDS)
def test_rendered_price_matches_delta_table(page, product_id):
    page.goto(f"{config.BASE_URL}{config.STATIC_ROOT}/product/{product_id}")
    swatches = page.locator("button.swatch:not([disabled])")
    sizes = [int(v) for v in swatches.evaluate_all("els => els.map(e => e.value)")]
    assert sizes, "product has no HDD swatches; pick another sample id"
    base = Decimal(re.sub(r"[^\d.]", "", page.locator(".caption .price").inner_text()))
    expected = {
        p.name.split()[-2]: p.price
        for p in expand(RawProduct("u", "n", "d", base, hdd_sizes=sizes))
    }
    for size in sizes:
        page.locator(f"button.swatch[value='{size}']").click()
        shown = Decimal(re.sub(r"[^\d.]", "", page.locator(".caption .price").inner_text()))
        assert shown == expected[str(size)], f"{size} GB: site shows {shown}"
