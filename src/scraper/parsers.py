import re
from decimal import Decimal
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

from scraper.models import RawProduct

_PAGE_RE = re.compile(r"[?&]page=(\d+)")


class ParseError(Exception):
    pass


def _text(tree: LexborHTMLParser, selector: str, url: str) -> str:
    el = tree.css_first(selector)
    if el is None:
        raise ParseError(f"{url}: selector {selector!r} not found")
    return str(el.text(strip=True))


def _hrefs(tree: LexborHTMLParser, selector: str, base_url: str) -> list[str]:
    hrefs = (a.attributes.get("href") for a in tree.css(selector))
    return list(dict.fromkeys(urljoin(base_url, h) for h in hrefs if h))


def parse_category_links(html: str, base_url: str) -> list[str]:
    return _hrefs(LexborHTMLParser(html), "a.category-link", base_url)


def parse_subcategory_links(html: str, base_url: str) -> list[str]:
    return _hrefs(LexborHTMLParser(html), "a.subcategory-link", base_url)


def parse_listing(html: str, base_url: str) -> list[str]:
    return _hrefs(LexborHTMLParser(html), "a.title", base_url)


def parse_last_page(html: str) -> int:
    """The pager shows a window of pages but always links the last one."""
    pages = [
        int(m.group(1))
        for a in LexborHTMLParser(html).css(".pagination a.page-link")
        if (m := _PAGE_RE.search(a.attributes.get("href") or ""))
    ]
    return max(pages, default=1)


def parse_price(text: str) -> Decimal:
    return Decimal(re.sub(r"[^\d.]", "", text))


def parse_product(html: str, url: str) -> RawProduct:
    tree = LexborHTMLParser(html)
    # disabled swatch = out of stock
    hdd_sizes = [
        int(b.attributes["value"] or 0)
        for b in tree.css("button.swatch")
        if "disabled" not in b.attributes
    ]
    colors = [
        v
        for o in tree.css("select[aria-label=color] option")
        if (v := o.attributes.get("value"))  # skips the "Select color" placeholder
    ]
    return RawProduct(
        url=url,
        # scoped to .caption: the sidebar nav also carries itemprop="name" ("Home")
        name=_text(tree, ".caption [itemprop=name]", url),
        description=_text(tree, ".caption [itemprop=description]", url),
        price=parse_price(_text(tree, ".caption [itemprop=price]", url)),
        hdd_sizes=hdd_sizes,
        colors=colors,
    )
