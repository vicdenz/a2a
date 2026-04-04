# Apartment Finder

Scrapes rental listings across multiple websites, uses Claude AI to extract structured data, then filters and ranks results by your preferences. Outputs a scored HTML report, JSON, and CSV.

## Setup

```bash
# Install dependencies (requires uv)
uv pip install -e ".[dev]"

# Install Playwright browsers
uv run playwright install chromium firefox

# Copy and fill in your Anthropic API key
cp .env.example .env
```

Edit `config.yaml` with your search parameters (city, budget, move-in date, requirements, preferences).

## Run

```bash
uv run python -m src.main
```

The HTML report opens automatically when done. Results are also saved to `output/listings.json` and `output/listings.csv`.

## Configuration

All behavior is controlled by `config.yaml`:

- **`websites`** — enable/disable sites, change scraping strategy per site
- **`search`** — city, budget, bedrooms, move-in date, lease duration
- **`requirements`** — hard filters (anything failing is dropped entirely)
- **`preferences`** — weighted scoring (higher weight = more impact on ranking)

## Known Limitations

- **Facebook Marketplace** — disabled by default; requires manually exporting session cookies from a logged-in browser into `config.yaml`
- **Airbnb** — Cloudflare bypass succeeds ~75% of the time; expect fewer results than other sites
- **Geocoding** — Nominatim (free) is rate-limited to 1 req/sec; slow for large result sets
- **API cost** — ~$2–8 USD per full run at 50 listings × 8 sites (pay-as-you-go via Anthropic API)
