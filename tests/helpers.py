"""HTML builders for a miniature fake site, shared by the crawler tests."""

from scraper import config

ROOT = "https://webscraper.io" + config.STATIC_ROOT


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
