from __future__ import annotations

import argparse
import asyncio
import json
import os

from geopy.geocoders import Nominatim

from src.config import load_config
from src.extractor.gemini import extract_all
from src.extractor.schema import Listing
from src.output.generator import generate_output
from src.pipeline.filter import filter_listings
from src.pipeline.scorer import score_and_rank
from src.scraper.engine import scrape_all

_SCRAPE_CACHE = "output/scrape_cache.json"
_EXTRACT_CACHE = "output/extract_cache.json"


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
        help="Mark all listings as passing the filter (skip filter logic entirely).",
    )
    p.add_argument(
        "-r", "--resume",
        action="store_true",
        help="Skip scraping — resume extraction from cached scrape data.",
    )
    p.add_argument(
        "-p", "--post-extract",
        action="store_true",
        help="Skip scraping and extraction — run filter/score/output from cached extracted data.",
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
    try:
        with open(_SCRAPE_CACHE) as f:
            data = json.load(f)
        pages = [(d["site"], d["url"], d["html"]) for d in data]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Cache file corrupt ({e}) — delete {_SCRAPE_CACHE} and re-run")
        return None
    print(f"  Loaded {len(pages)} pages from scrape cache")
    return pages


def _save_extract_cache(listings: list[Listing]) -> None:
    """Save extracted listings to disk so filter/score/output can re-run without AI calls."""
    os.makedirs(os.path.dirname(_EXTRACT_CACHE), exist_ok=True)
    data = [l.model_dump(mode="json") for l in listings]
    with open(_EXTRACT_CACHE, "w") as f:
        json.dump(data, f)
    print(f"  Extract cache saved: {_EXTRACT_CACHE} ({len(data)} listings)")


def _load_extract_cache() -> list[Listing] | None:
    """Load extracted listings from disk cache."""
    if not os.path.exists(_EXTRACT_CACHE):
        return None
    try:
        with open(_EXTRACT_CACHE) as f:
            data = json.load(f)
        listings = [Listing(**d) for d in data]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Cache file corrupt ({e}) — delete {_EXTRACT_CACHE} and re-run")
        return None
    print(f"  Loaded {len(listings)} listings from extract cache")
    return listings


async def _geocode_anchor(address: str) -> tuple[float, float] | None:
    """Geocode the anchor address once at startup. Returns (lat, lng) or None."""
    try:
        geolocator = Nominatim(user_agent="a2a")
        loop = asyncio.get_running_loop()
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

    # Step 1–2: Scrape + Extract (or load from cache)
    if args.post_extract:
        # Skip scraping and extraction — load previously extracted listings
        listings = _load_extract_cache()
        if not listings:
            print(f"\nNo extract cache found at {_EXTRACT_CACHE}. Run without --post-extract first.")
            return
        total_scraped = len(listings)
    else:
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

        # Save extract cache so filter/score/output can re-run without AI calls
        _save_extract_cache(listings)

    # Step 3: Filter — tags listings with passed_filter (does NOT drop them)
    if args.all:
        print(f"\n=== Filter skipped (--all) — marking all {len(listings)} listings as passed ===")
        for l in listings:
            l.passed_filter = True
            l.filter_reason = None
    else:
        print(f"\n=== Filtering {len(listings)} listings ===")
        filter_listings(listings, config.requirements)

    # Step 4: Score & rank (all listings — passed are sorted first)
    print(f"\n=== Scoring {len(listings)} listings ===")
    ranked = score_and_rank(listings, config.preferences, config.search, config.requirements)
    passed_count = sum(1 for l in ranked if l.passed_filter)
    top_passed_score = next((l.score for l in ranked if l.passed_filter), None)
    print(f"  Top passed score: {top_passed_score if top_passed_score is not None else 'N/A'}")

    # Step 5: Output
    print(f"\n=== Generating output ===")
    generate_output(
        ranked,
        config.output,
        config.preferences,
        total_scraped=total_scraped,
        sites_count=len(enabled_sites),
    )

    print(f"\n=== Done! {passed_count} passed / {len(ranked)} total listings in report ===")


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
