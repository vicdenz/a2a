from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime

import anthropic
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from src.config import AppConfig
from src.extractor.schema import EXTRACTION_FIELDS, Listing

# Rate limit: 5 concurrent Claude API calls
_semaphore = asyncio.Semaphore(5)

# Nominatim rate limit: 1 req/sec
_geocode_lock = asyncio.Lock()
_last_geocode_time: float = 0


def _clean_html(html: str) -> str:
    """Strip scripts, styles, and comments to reduce token count."""
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    # Truncate to ~80k characters
    if len(html) > 80000:
        html = html[:80000]
    return html


def _build_extraction_prompt(site_name: str, listing_url: str, html: str) -> str:
    schema_str = json.dumps(EXTRACTION_FIELDS, indent=2)
    return f"""You are extracting structured rental listing data from raw HTML.

Site: {site_name}
URL: {listing_url}

Instructions:
- Extract every field you can find in the HTML.
- Return a single JSON object matching the schema exactly.
- Use null for any field you cannot find or are not confident about.
- For boolean fields, only return true/false if explicitly stated. Use null if ambiguous.
- Monthly rent must be a number (no currency symbols). If a price range is given, use the lower bound.
- Currency should be "CAD" unless clearly USD.
- Do not infer or guess values. Only extract what is explicitly present.

Schema:
{schema_str}

HTML:
{html}

Return only the JSON object. No explanation, no markdown fences."""


async def _extract_one(
    client: anthropic.AsyncAnthropic,
    site_name: str,
    listing_url: str,
    html: str,
    config: AppConfig,
) -> Listing | None:
    """Extract a single listing from HTML using Claude."""
    cleaned = _clean_html(html)
    html_hash = hashlib.md5(cleaned.encode()).hexdigest()
    prompt = _build_extraction_prompt(site_name, listing_url, cleaned)

    async with _semaphore:
        try:
            response = await client.messages.create(
                model=config.ai.model,
                max_tokens=config.ai.max_tokens,
                temperature=config.ai.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"  Claude API error for {listing_url[:60]}: {e}")
            return None

    # Parse response
    text = response.content[0].text.strip()
    # Remove markdown fences if present despite instructions
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {listing_url[:60]}: {e}")
        return None

    try:
        listing = Listing(
            url=listing_url,
            source=site_name,
            scraped_at=datetime.now(),
            raw_html_hash=html_hash,
            **data,
        )
        return listing
    except Exception as e:
        print(f"  Listing validation error for {listing_url[:60]}: {e}")
        return None


async def _geocode_listing(listing: Listing, anchor_address: str) -> None:
    """Geocode a listing's address and compute distance to anchor."""
    global _last_geocode_time

    if not listing.address or not listing.city:
        return

    geolocator = Nominatim(user_agent="apartment-finder")
    query = f"{listing.address}, {listing.city}"

    async with _geocode_lock:
        # Enforce 1 req/sec
        elapsed = time.time() - _last_geocode_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _last_geocode_time = time.time()

        try:
            loop = asyncio.get_event_loop()
            location = await loop.run_in_executor(None, geolocator.geocode, query)
        except Exception:
            return

    if location is None:
        return

    listing.latitude = location.latitude
    listing.longitude = location.longitude

    # Calculate distance to anchor
    if anchor_address:
        async with _geocode_lock:
            elapsed = time.time() - _last_geocode_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _last_geocode_time = time.time()

            try:
                loop = asyncio.get_event_loop()
                anchor_loc = await loop.run_in_executor(None, geolocator.geocode, anchor_address)
            except Exception:
                return

        if anchor_loc:
            listing.distance_km = round(
                geodesic(
                    (listing.latitude, listing.longitude),
                    (anchor_loc.latitude, anchor_loc.longitude),
                ).km,
                2,
            )


async def extract_all(
    raw_pages: list[tuple[str, str, str]],
    config: AppConfig,
) -> list[Listing]:
    """Extract structured listings from raw HTML pages using Claude API."""
    if not raw_pages:
        print("No pages to extract.")
        return []

    print(f"\n=== Extracting data from {len(raw_pages)} listing pages ===")
    client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)

    tasks = [
        _extract_one(client, site_name, url, html, config)
        for site_name, url, html in raw_pages
    ]

    listings: list[Listing] = []
    results = await asyncio.gather(*tasks)
    for r in results:
        if r is not None:
            listings.append(r)

    print(f"  Extracted {len(listings)} listings successfully")

    # Geocode all listings
    if config.search.anchor_address:
        print(f"  Geocoding {len(listings)} listings (1/sec rate limit)...")
        for listing in listings:
            await _geocode_listing(listing, config.search.anchor_address)

    # Deduplicate by raw_html_hash
    seen_hashes: set[str] = set()
    deduped: list[Listing] = []
    for listing in listings:
        if listing.raw_html_hash and listing.raw_html_hash in seen_hashes:
            continue
        if listing.raw_html_hash:
            seen_hashes.add(listing.raw_html_hash)
        deduped.append(listing)

    print(f"  After deduplication: {len(deduped)} listings")
    return deduped
