# a2a — AI to Apartment

Scrapes rental listings across multiple websites, uses AI to extract structured data, then filters and ranks results by your preferences. Outputs a scored HTML report, JSON, and CSV.

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- A Gemini API key

## Setup

### 1. Create a fresh virtual environment

```bash
# Remove stale venv if it exists
rm -rf .venv

# Create a new venv and install all dependencies
uv sync
uv pip install -e ".[dev]"
```

### 2. Install Playwright browsers

```bash
uv run playwright install chromium firefox
```

### 3. Configure your API key

```bash
cp .env.example .env
```

Open `.env` and fill in your Gemini API key.

### 4. Configure your search

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your search parameters — city, budget, move-in date, requirements, and preferences. `config.yaml` is gitignored; `config.example.yaml` is the template.

## Run

```bash
uv run python -m src.main
```

The HTML report opens automatically when done. Results are also saved to `output/listings.json` and `output/listings.csv`.

## Run Tests

```bash
# All tests
uv run pytest tests/ -v

# Single test file
uv run pytest tests/test_filter.py -v

# Single test
uv run pytest tests/test_scorer.py::test_scorer_price_asc -v
```

## Configuration Reference

All behavior is controlled by `config.yaml`:

| Section        | Purpose                                                   |
| -------------- | --------------------------------------------------------- |
| `websites`     | Enable/disable sites, set scraping strategy per site      |
| `search`       | City, budget, bedrooms, move-in date, lease duration      |
| `requirements` | Hard filters — listings that fail are dropped entirely    |
| `preferences`  | Weighted scoring — higher weight = more impact on ranking |

## Pipeline

Five-stage async pipeline: **Scrape → Extract → Filter → Score → Output**

1. **Scrape** — fetches listing pages using Playwright, Camoufox (fingerprint evasion), or Zendriver (Cloudflare bypass), depending on the site
2. **Extract** — sends cleaned HTML to the Gemini API; returns structured `Listing` objects with geocoded distance
3. **Filter** — drops listings that fail any hard requirement in `config.yaml`
4. **Score** — ranks remaining listings by weighted preferences (distance, price, boolean fields)
5. **Output** — writes HTML report, JSON, and CSV to `output/`

## Supported Sites

| Site | Strategy |
|---|---|
| Kijiji | Playwright |
| Craigslist | Playwright |
| Rentals.ca | Playwright |
| Airbnb | Zendriver (Cloudflare bypass) |

## CLI Flags

```bash
uv run python -m src.main                 # full pipeline
uv run python -m src.main -s/--scrape-only      # scrape only, save raw HTML to cache and stop (no AI calls)
uv run python -m src.main -r/--resume           # skip scraping, resume extraction from scrape cache
uv run python -m src.main -p/--post-extract     # skip scrape + extract, re-run filter/score/output from extract cache
uv run python -m src.main -a/--all              # skip filter, output all extracted listings
```

Each stage writes a cache to `output/` (`scrape_cache.json`, `extract_cache.json`) so you can iterate on filters and preferences without re-running the expensive upstream stages.

## Known Limitations

- **Geocoding** — Nominatim (free) is rate-limited to 1 req/sec; slow for large result sets
- **Gemini API** — free-tier rate limits constrain throughput; see `ai.model` comments in `config.example.yaml` for current model RPM/TPM/RPD quotas
- **Rentals.ca neighbourhood slugs** — only Toronto neighbourhoods are currently defined in `_RENTALS_CA_NEIGHBOURHOODS` (`src/scraper/sites.py`); other cities fall back to the city-level URL

---

Scraping may violate the terms of service of the listed sites — this is a personal project for educational use, run at your own discretion.
