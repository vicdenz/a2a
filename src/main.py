from __future__ import annotations

import argparse
import asyncio
import json
import os

from geopy.geocoders import Nominatim

from src.config import load_config
from src.extractor.gemini import extract_all
from src.output.generator import generate_output
from src.pipeline.filter import filter_listings
from src.pipeline.scorer import score_and_rank
from src.scraper.engine import scrape_all

_SCRAPE_CACHE = "output/scrape_cache.json"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="a2a — AI to Apartment")
    p.add_argument(
        "-s", "--scrape-only",
        action="store_true",
        help="Run scraping only — save scraped pages to cache and stop (no AI calls).",
    )
    p.add_argument(
        "-a", "--all",
        action="store_true",
        help="Skip requirements filter — output every extracted listing regardless of filters.",
    )
    p.add_argument(
        "-r", "--resume",
        action="store_true",
        help="Skip scraping — resume extraction from cached scrape data.",
    )
    return p.parse_args()


def _save_scrape_cache(raw_pages: list[tuple[str, str, str]]) -> None:
    """Save scraped pages to disk so extraction can resume without re-scraping."""
    os.makedirs(os.path.dirname(_SCRAPE_CACHE), exist_ok=True)
    data = [{"site": s, "url": u, "html": h} for s, u, h in raw_pages]
    with open(_SCRAPE_CACHE, "w") as f:
        json.dump(data, f)
    print(f"  Scrape cache saved: {_SCRAPE_CACHE} ({len(data)} pages)")


def _load_scrape_cache() -> list[tuple[str, str, str]] | None:
    """Load scraped pages from disk cache."""
    if not os.path.exists(_SCRAPE_CACHE):
        return None
    with open(_SCRAPE_CACHE) as f:
        data = json.load(f)
    pages = [(d["site"], d["url"], d["html"]) for d in data]
    print(f"  Loaded {len(pages)} pages from scrape cache")
    return pages


async def _geocode_anchor(address: str) -> tuple[float, float] | None:
    """Geocode the anchor address once at startup. Returns (lat, lng) or None."""
    try:
        geolocator = Nominatim(user_agent="a2a")
        loop = asyncio.get_event_loop()
        location = await loop.run_in_executor(None, geolocator.geocode, address)
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass
    return None


async def main(args: argparse.Namespace) -> None:
    print("=== a2a — AI to Apartment ===\n")

    # Step 0: Load config
    print("Loading configuration...")
    config = load_config()
    enabled_sites = [s for s in config.websites if s.enabled]
    print(f"  {len(enabled_sites)} sites enabled")
    print(f"  City: {config.search.city or '(not set)'}")
    print(f"  Max rent: {config.search.max_monthly_rent or '(not set)'}")

    # Geocode anchor address so scrapers can use lat/lng for radius-based search
    if config.search.anchor_address and config.search.anchor_lat is None:
        print(f"  Geocoding anchor: {config.search.anchor_address}...")
        coords = await _geocode_anchor(config.search.anchor_address)
        if coords:
            config.search.anchor_lat, config.search.anchor_lng = coords
            print(f"  Anchor coords: {config.search.anchor_lat:.4f}, {config.search.anchor_lng:.4f}")
        else:
            print("  Warning: could not geocode anchor address, radius search unavailable")

    # Step 1: Scrape (or load from cache)
    if args.resume:
        raw_pages = _load_scrape_cache()
        if not raw_pages:
            print(f"\nNo scrape cache found at {_SCRAPE_CACHE}. Run without --resume first.")
            return
    else:
        raw_pages = await scrape_all(config)

        # Always save cache after scraping so data isn't lost
        if raw_pages:
            _save_scrape_cache(raw_pages)

    total_scraped = len(raw_pages)

    if not raw_pages:
        print("\nNo listings scraped. Check your config and network connection.")
        return

    if args.scrape_only:
        print(f"\n=== Scrape-only mode: {total_scraped} pages collected ===")
        for site_name, url, _ in raw_pages:
            print(f"  [{site_name}] {url}")
        return

    # Step 2: Extract
    listings = await extract_all(raw_pages, config)

    if not listings:
        print("\nNo listings could be extracted. Check Gemini API key and model.")
        return

    # Step 3: Filter (skipped with --all)
    if args.all:
        print(f"\n=== Filter skipped (--all) — keeping all {len(listings)} listings ===")
        filtered = listings
    else:
        print(f"\n=== Filtering {len(listings)} listings ===")
        filtered = filter_listings(listings, config.requirements)

    # Step 4: Score & rank
    print(f"\n=== Scoring {len(filtered)} listings ===")
    ranked = score_and_rank(filtered, config.preferences, config.search)
    print(f"  Top score: {ranked[0].score if ranked else 'N/A'}")

    # Step 5: Output
    print(f"\n=== Generating output ===")
    generate_output(
        ranked,
        config.output,
        config.preferences,
        total_scraped=total_scraped,
        sites_count=len(enabled_sites),
    )

    print(f"\n=== Done! {len(ranked)} listings in report ===")


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
