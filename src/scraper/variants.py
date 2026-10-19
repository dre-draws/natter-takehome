
from scraper.config import HDD_PRICE_DELTAS
from scraper.models import Product, RawProduct


def expand(raw: RawProduct) -> list[Product]:
    """One Product per in-stock HDD size; colours only when there is a choice."""
    colors = raw.colors if len(raw.colors) > 1 else []
    unknown = [s for s in raw.hdd_sizes if s not in HDD_PRICE_DELTAS]
    if unknown:
        raise ValueError(f"no price delta for HDD size(s) {unknown} GB; update HDD_PRICE_DELTAS")
    if not raw.hdd_sizes:
        return [Product(raw.name, raw.description, raw.price, colors)]
    return [
        Product(
            f"{raw.name} {size} GB",
            raw.description,
            raw.price + HDD_PRICE_DELTAS[size],
            colors,
        )
        for size in raw.hdd_sizes
    ]
