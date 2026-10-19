BASE_URL = "https://webscraper.io"
STATIC_ROOT = "/test-sites/e-commerce/static"
USER_AGENT = "natter-takehome-scraper/0.1"

# The site throttles above ~20 HTTP/1.1 connections; over HTTP/2 throughput plateaus around 30.
DEFAULT_CONCURRENCY = 30
TIMEOUT_SECONDS = 15.0
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 0.5

# Product HTML only carries the 128 GB price; the storefront JS adds these deltas on swatch click.
# tests/contract/test_live_pricing.py checks them against the live site.
HDD_PRICE_DELTAS = {128: 0, 256: 20, 512: 40, 1024: 60}
