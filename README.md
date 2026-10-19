# E-commerce scraper

Scrapes <https://webscraper.io/test-sites/e-commerce/static> and prints one JSON document to stdout.

```json
{
  "results": [
    { "name": "Packard 255 G2 256 GB", "description": "...", "price": 436.99 },
    { "name": "Nokia 123", "description": "...", "price": 24.99, "colors": ["Gold", "White", "Black"] }
  ],
  "total": 345701.52
}
```

- Every product is collected: 147 products across laptops, tablets and phones, giving 423 results.
  Products are de-duplicated by URL, so one that appears in more than one place (for example the
  featured items on the home and category pages) is fetched and counted once.
- A product with several in-stock HDD sizes becomes one result per size, with the size in the name
  (`Packard 255 G2 128 GB`, `... 256 GB`, ...).
- `colors` is only present when there are two or more colour options.
- `total` is the sum of the `price` of every entry in `results`.

## Run

Requires Python 3.12+. On macOS there is no bare `python` command and the system `python3` is
usually older, so install a current one first (`brew install python@3.12`) and use `python3.12`
to create the virtualenv. Inside the activated venv, `python` and `pip` work as normal.

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

python -m scraper > out.json         # JSON goes to out.json; the terminal stays quiet
python -m scraper -v > out.json      # same, with a progress summary shown in the terminal
python -m scraper                    # print the JSON to the terminal instead
python -m scraper --concurrency 10   # default is 30
```

The default of 30 concurrent requests finishes in about 2 seconds, which is a short burst against
the target host. For a recurring or shared-infrastructure job, lower it (`--concurrency 5` takes
roughly 5 s) to be gentler.

With Docker:

```bash
docker build -t scraper .
docker run --rm scraper > out.json     # JSON goes to out.json; the terminal stays quiet
docker run --rm scraper -v > out.json  # same, with progress logs shown in the terminal
docker run --rm scraper                # print the JSON to the terminal instead
```

**robots.txt.** The scraper reads `https://webscraper.io/robots.txt` at startup and refuses any URL
it disallows for this user agent, counting it as a failed page. A `Crawl-delay`, if present, spaces
out request starts across all workers. A 4xx response for the file means no restrictions; if it
cannot be read at all (5xx, network error) the run stops rather than crawl without the rules.

**Exit code.** It is non-zero if any product or listing page failed (including pages blocked by
`robots.txt`), or a product had an unrecognised HDD size. The JSON for everything that did succeed
is still printed, so a partial scrape is never mistaken for a complete one. A failure on the home
page or a category page is fatal, since nothing can be crawled without them.

## Develop

```bash
pytest                      # unit tests: offline, run against saved HTML fixtures
pytest -m contract          # live site + real browser (needs `playwright install chromium`)
ruff check . && mypy src
```

Runtime dependencies are pinned in `requirements.lock`, which the Dockerfile installs from.
After changing `pyproject.toml`, regenerate it from a clean venv:

```bash
pip install . && pip freeze --exclude scraper > requirements.lock
```

## How it works

| Module | Role |
| --- | --- |
| `config.py` | URLs, concurrency, timeouts, retry settings, HDD price table |
| `client.py` | Async `httpx` client over HTTP/2: concurrency cap, timeouts, retry with backoff on 5xx, 429 and network errors, `robots.txt` enforcement and crawl-delay |
| `crawler.py` | Home -> categories -> subcategories -> listing pages -> product pages, pipelined: a listing page's products start downloading as soon as it is parsed |
| `parsers.py` | Pure HTML -> data functions (`selectolax`). Raises `ParseError` on a missing selector rather than emitting bad data |
| `variants.py` | Expands a product into one result per in-stock HDD size |
| `models.py` | `RawProduct` (as scraped) and `Product` (as output) |
| `cli.py` | Argument parsing, JSON output, exit code |

**De-duplication.** Products are discovered from subcategory listings, never from the featured items
on the home or category pages. The crawler also tracks every product URL it has seen and skips
repeats, so a product linked from several pages is fetched once and cannot inflate `total`. Two
different products that share a name are not duplicates: each has its own URL and is kept.

**Pagination.** The pager shows only a window of pages (`2..10 ... 19 20`) but always links the
last one. The page count is read from page 1 and every other page is fetched in parallel, rather
than by following "next".

**Performance.** About 180 requests finish in ~2 s. Two changes mattered most: parsing with
`selectolax` instead of BeautifulSoup (~0.2 ms vs ~9 ms per page, and parsing runs on the same
thread as the network I/O), and removing the waits between crawl stages. HTTP/2 mattered too: over
HTTP/1.1 the site slows down sharply (10 s+, no errors) above ~20 concurrent connections, while
HTTP/2 multiplexing has no such cliff.

## Decisions

- **Variant prices are not in the HTML.** The page shows the 128 GB price, and the site's own
  JavaScript adds +20/+40/+60 for 256/512/1024 GB when a swatch is clicked.
  `config.HDD_PRICE_DELTAS` encodes that table. To avoid trusting it blindly,
  `tests/contract/test_live_pricing.py` clicks the swatches in a real browser and fails if the
  site disagrees.
- **Disabled swatches are skipped.** The site marks them as unavailable, so they are not
  emitted as products.
- **`total` sums every entry in `results`.** Summing distinct price values instead would silently
  drop products that happen to share a price.
- **Prices are `Decimal`** until they are written out, so the total has no floating-point drift.
- **Unknown HDD sizes are skipped, not guessed.** A size missing from `HDD_PRICE_DELTAS` is logged,
  counted as a failure and left out of the results.

## Trade-offs and future work

- Test fixtures are hand-saved HTML. A script to refresh them would help when the site changes.
- No on-disk cache. The site sends `Cache-Control: max-age=300` but no `ETag`, so there is nothing
  to revalidate against; fine for ~180 requests, not for a recurring crawl.
- `robots.txt` handling uses the stdlib `urllib.robotparser`, which ignores wildcard rules
  (`Disallow: /x*?page=`) and non-integer `Crawl-delay` values. None of the current rules for this
  site depend on either; a stricter parser would be needed for a site that does.
- Rate limiting is the concurrency cap plus `Crawl-delay`; there is no per-second request budget.
- If the site ever rendered prices client-side, the fallback would be Playwright for the product
  stage; the parser and variant layers would not change.
