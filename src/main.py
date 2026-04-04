from __future__ import annotations

import asyncio

from src.config import load_config
from src.extractor.claude import extract_all
from src.output.generator import generate_output
from src.pipeline.filter import filter_listings
from src.pipeline.scorer import score_and_rank
from src.scraper.engine import scrape_all


async def main() -> None:
    print("=== Apartment Finder ===\n")

    # Step 0: Load config
    print("Loading configuration...")
    config = load_config()
    enabled_sites = [s for s in config.websites if s.enabled]
    print(f"  {len(enabled_sites)} sites enabled")
    print(f"  City: {config.search.city or '(not set)'}")
    print(f"  Max rent: {config.search.max_monthly_rent or '(not set)'}")

    # Step 1: Scrape
    raw_pages = await scrape_all(config)
    total_scraped = len(raw_pages)

    if not raw_pages:
        print("\nNo listings scraped. Check your config and network connection.")
        return

    # Step 2: Extract
    listings = await extract_all(raw_pages, config)

    if not listings:
        print("\nNo listings could be extracted. Check Claude API key and model.")
        return

    # Step 3: Filter
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
    asyncio.run(main())
