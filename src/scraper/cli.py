import argparse
import asyncio
import json
import logging
import sys
import time
from decimal import Decimal
from typing import Any

from scraper import config
from scraper.client import Fetcher
from scraper.crawler import crawl
from scraper.models import Product

log = logging.getLogger(__name__)


def build_output(products: list[Product]) -> dict[str, Any]:
    total = sum((p.price for p in products), Decimal(0))
    return {"results": [p.to_json() for p in products], "total": float(total)}


async def run(concurrency: int) -> int:
    start = time.perf_counter()
    async with Fetcher(concurrency) as fetcher:
        await fetcher.load_robots()
        products, failed = await crawl(fetcher)
    elapsed = time.perf_counter() - start
    log.info("%d results, %d failed pages, %.1fs", len(products), failed, elapsed)
    json.dump(build_output(products), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scrape the webscraper.io static e-commerce site.")
    ap.add_argument("--concurrency", type=int, default=config.DEFAULT_CONCURRENCY)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return asyncio.run(run(args.concurrency))
