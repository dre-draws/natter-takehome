from decimal import Decimal

from scraper.cli import build_output
from scraper.models import RawProduct
from scraper.variants import expand


def raw(**kw):
    base = dict(url="u", name="Laptop", description="d", price=Decimal("100.10"))
    return RawProduct(**{**base, **kw})


def test_one_product_per_hdd_with_price_delta():
    out = expand(raw(hdd_sizes=[128, 512]))
    assert [(p.name, p.price) for p in out] == [
        ("Laptop 128 GB", Decimal("100.10")),
        ("Laptop 512 GB", Decimal("140.10")),
    ]


def test_no_hdd_passes_through():
    assert [p.name for p in expand(raw())] == ["Laptop"]


def test_colours_only_when_multiple():
    assert expand(raw(colors=["Red"]))[0].colors == []
    assert expand(raw(colors=["Red", "Blue"]))[0].colors == ["Red", "Blue"]


def test_total_is_exact_sum_of_results():
    out = build_output(expand(raw(price=Decimal("0.10"), hdd_sizes=[128, 128, 128])))
    assert out["total"] == 0.3  # float addition would give 0.30000000000000004
    assert "colors" not in out["results"][0]
