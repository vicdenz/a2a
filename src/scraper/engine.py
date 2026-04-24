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

    # Per-site heuristics for recognizing listing detail URLs
    builder = site.url_builder

    # Rentals.ca: use listing-card permalink class instead of generic href matching.
    # Building-name URLs (/toronto/immix, /toronto/akoya) are indistinguishable from
    # category pages (/toronto/furnished, /toronto/pet-friendly) by URL pattern alone,
    # but listing cards reliably use the `listing-card__permalink-button` class.
    if builder == "rentals_ca":
        card_pattern = re.compile(
            r'listing-card__permalink-button[^>]*href=["\']([^"\'#]+)',
            re.IGNORECASE,
        )
        for href in card_pattern.findall(html):
            full_url = href if href.startswith("http") else base + href
            urls.add(full_url)
        return list(urls)

    # Generic href extraction for all other sites
    href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
    all_hrefs = href_pattern.findall(html)

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
        elif builder == "airbnb" and "/rooms/" in href:
            clean = re.sub(r"\?.*", "", full_url)
            urls.add(clean)

    # Debug: if no URLs found, log sample hrefs to help diagnose pattern issues
    if not urls and all_hrefs:
        sample = [h for h in all_hrefs if h.startswith("/") or site.base_url in h][:10]
        if sample:
            print(f"    No listing URLs matched. Sample hrefs from {site.name}:")
            for h in sample:
                print(f"      {h[:120]}")
        else:
            print(f"    {len(all_hrefs)} hrefs found but none match site domain. Page may be JS-rendered.")

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

            # Build search URL groups. Each group is one logical bucket (e.g. a
            # rentals.ca neighbourhood); sites without buckets return one group.
            url_groups = build_search_urls(site, config.search, config.requirements)
            total_pages = sum(len(g) for g in url_groups)
            total_quota = config.scraping.max_listings_per_site
            per_group_quota = max(1, total_quota // max(1, len(url_groups)))
            if len(url_groups) > 1:
                print(f"  Search pages: {total_pages} across {len(url_groups)} groups (quota: {per_group_quota}/group)")
            else:
                print(f"  Search pages: {total_pages}")

            # Collect listing URLs from each group, capped per-group so every
            # bucket contributes its fair share before the global cap kicks in.
            listing_urls: list[str] = []
            for group in url_groups:
                if len(listing_urls) >= total_quota:
                    break
                group_urls: list[str] = []
                for search_url in group:
                    if len(group_urls) >= per_group_quota:
                        break

                    for attempt in range(1, config.scraping.max_retries + 1):
                        try:
                            print(f"  Fetching search page: {search_url[:80]}...")
                            html = await strategy.fetch(search_url, site, config.scraping)
                            page_urls = await _extract_listing_urls(html, site)
                            group_urls.extend(page_urls)
                            print(f"  Found {len(page_urls)} listing links")
                            break
                        except Exception as e:
                            print(f"  Attempt {attempt} failed: {e}")
                            if attempt == config.scraping.max_retries:
                                print(f"  Giving up on search page after {attempt} attempts")

                    await asyncio.sleep(config.scraping.request_delay_ms / 1000)

                listing_urls.extend(group_urls[:per_group_quota])

            # Deduplicate and apply the overall cap
            listing_urls = list(dict.fromkeys(listing_urls))[:total_quota]
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
