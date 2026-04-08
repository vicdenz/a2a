from __future__ import annotations

import asyncio
import re

from src.config import AppConfig, SiteConfig
from src.scraper.sites import build_search_urls
from src.scraper.strategies import STRATEGIES, ScraperStrategy


async def _extract_listing_urls(html: str, site: SiteConfig) -> list[str]:
    """Extract individual listing URLs from a search results page HTML."""
    urls: set[str] = set()
    base = site.base_url.rstrip("/")

    # Generic href extraction — grab links that look like individual listing pages
    href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
    all_hrefs = href_pattern.findall(html)

    # Per-site heuristics for recognizing listing detail URLs
    builder = site.url_builder

    for href in all_hrefs:
        full_url = href if href.startswith("http") else base + href

        if builder == "kijiji" and "/v-" in href:
            urls.add(full_url)
        elif builder == "craigslist" and re.search(r"/apa/d/", href):
            urls.add(full_url)
        elif builder == "craigslist" and re.search(r"/apa/\d{8,}", href):
            urls.add(full_url)
        elif builder == "craigslist" and re.search(r"craigslist\.org/\w+/\w+/\d{8,}", href):
            urls.add(full_url)
        elif builder == "rentals_ca" and re.search(r"/[a-z\-]+/[a-z0-9\-]+-id\d+", href):
            # Explicit listing ID format: /toronto/building-name-id123456
            urls.add(full_url)
        elif builder == "rentals_ca" and re.search(r"/[a-z\-]+/\d+[a-z\-]", href):
            # Address format: /toronto/55-oakmount-rd, /toronto/1101-bay
            # Must start with a digit (street number).
            # Exclude category pages (/toronto/2-bedrooms) and non-listing paths.
            if not re.search(r"/\d+-bed(room)?s?\b", href):
                if not re.search(r"/\d+-bath(room)?s?\b", href):
                    if not re.search(r"/(manage|static|api|auth)\b", href):
                        if not re.search(r"\.(js|css|png|jpg|svg|ico)$", href):
                            urls.add(full_url)
        elif builder == "airbnb" and "/rooms/" in href:
            clean = re.sub(r"\?.*", "", full_url)
            urls.add(clean)
        elif builder == "facebook_marketplace" and "/marketplace/item/" in href:
            urls.add(full_url)

    # Debug: if no URLs found, log sample hrefs to help diagnose pattern issues
    if not urls and all_hrefs:
        sample = [h for h in all_hrefs if h.startswith("/") or site.base_url in h][:10]
        if sample:
            print(f"    DEBUG: No listing URLs matched. Sample hrefs from {site.name}:")
            for h in sample:
                print(f"      {h[:120]}")
        else:
            print(f"    DEBUG: {len(all_hrefs)} hrefs found but none match site domain. Page may be JS-rendered.")

    return list(urls)


async def scrape_all(config: AppConfig) -> list[tuple[str, str, str]]:
    """
    Scrape all enabled websites and return (site_name, listing_url, html) tuples.
    """
    results: list[tuple[str, str, str]] = []
    enabled_sites = [s for s in config.websites if s.enabled]

    if not enabled_sites:
        print("No websites enabled in config.")
        return results

    # Create one strategy instance per strategy type
    strategy_instances: dict[str, ScraperStrategy] = {}

    try:
        for site in enabled_sites:
            print(f"\n--- Scraping: {site.name} ---")

            # Get or create strategy
            if site.strategy not in strategy_instances:
                strategy_cls = STRATEGIES.get(site.strategy)
                if strategy_cls is None:
                    print(f"  Unknown strategy '{site.strategy}', skipping {site.name}")
                    continue
                strategy_instances[site.strategy] = strategy_cls()
            strategy = strategy_instances[site.strategy]

            # Build search URLs
            search_urls = build_search_urls(site, config.search)
            print(f"  Search pages: {len(search_urls)}")

            # Standard flow: collect listing URLs from search pages, then fetch each
            listing_urls: list[str] = []
            for search_url in search_urls:
                if len(listing_urls) >= config.scraping.max_listings_per_site:
                    break

                for attempt in range(1, config.scraping.max_retries + 1):
                    try:
                        print(f"  Fetching search page: {search_url[:80]}...")
                        html = await strategy.fetch(search_url, site, config.scraping)
                        page_urls = await _extract_listing_urls(html, site)
                        listing_urls.extend(page_urls)
                        print(f"  Found {len(page_urls)} listing links")
                        break
                    except Exception as e:
                        print(f"  Attempt {attempt} failed: {e}")
                        if attempt == config.scraping.max_retries:
                            print(f"  Giving up on search page after {attempt} attempts")

                await asyncio.sleep(config.scraping.request_delay_ms / 1000)

            # Deduplicate and cap
            listing_urls = list(dict.fromkeys(listing_urls))[:config.scraping.max_listings_per_site]
            print(f"  Total unique listings to fetch: {len(listing_urls)}")

            # Fetch each listing page
            for i, listing_url in enumerate(listing_urls, 1):
                for attempt in range(1, config.scraping.max_retries + 1):
                    try:
                        print(f"  [{i}/{len(listing_urls)}] {listing_url[:80]}...")
                        html = await strategy.fetch(listing_url, site, config.scraping)
                        results.append((site.name, listing_url, html))
                        break
                    except Exception as e:
                        print(f"  Attempt {attempt} failed: {e}")
                        if attempt == config.scraping.max_retries:
                            print(f"  Skipping listing after {attempt} attempts")

                await asyncio.sleep(config.scraping.request_delay_ms / 1000)

        print(f"\n=== Scraping complete: {len(results)} listing pages collected ===")

    finally:
        # Clean up all strategy instances
        for strat in strategy_instances.values():
            try:
                await strat.close()
            except Exception:
                pass

    return results
