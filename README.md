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

Edit `config.yaml` with your search parameters — city, budget, move-in date, requirements, and preferences.

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

| Site | Strategy | Status |
|---|---|---|
| Kijiji | Playwright | Working |
| Craigslist | Playwright | Working (radius search via lat/lon) |
| Rentals.ca | Playwright | Working |
| Airbnb | Zendriver (Cloudflare bypass) | Working (~75% success rate) |
| Facebook Marketplace | Camoufox | Requires session cookies |

## CLI Flags

```bash
uv run python -m src.main          # full pipeline
uv run python -m src.main -s       # scrape only (no AI calls)
uv run python -m src.main -a       # skip filter, output all extracted listings
```

## Known Limitations

- **Facebook Marketplace** — disabled by default; requires manually exporting session cookies from a logged-in browser into `config.yaml`
- **Airbnb** — Cloudflare bypass succeeds ~75% of the time; expect fewer results than other sites
- **Geocoding** — Nominatim (free) is rate-limited to 1 req/sec; slow for large result sets
- **Gemini API** — free tier is 10 RPM; extraction runs at ~8 RPM to stay under the limit
