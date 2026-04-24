from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime

from google import genai
from google.genai import types
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

from src.config import AppConfig
from src.extractor.schema import EXTRACTION_FIELDS, Listing

# Suppress noisy gRPC fork warnings from Playwright + genai coexistence
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "0")

_geolocator = Nominatim(user_agent="a2a")

# Free-tier Gemini rate limits (RPM = requests per minute).
# gemini-2.0-flash-lite free tier: 15 RPM, 1500 RPD, 1M TPM.
# We use 12 RPM to leave a comfortable margin.
_rpm_limit = 12
# Minimum seconds between any two consecutive requests (60 / rpm).
# This prevents burst-firing all allowed requests at the start of a window.
_min_gap_s = 60.0 / _rpm_limit  # 5.0s
_request_times: list[float] = []
_last_request_time: float = 0.0
_rate_lock = asyncio.Lock()

# Only 1 concurrent API call — combined with _min_gap_s this guarantees
# we never exceed _rpm_limit requests per minute.
_semaphore = asyncio.Semaphore(1)

# Max retries for 429 / transient errors
_MAX_RETRIES = 3

# Nominatim rate limit: 1 req/sec
_geocode_lock = asyncio.Lock()
_last_geocode_time: float = 0


async def _wait_for_rate_limit() -> None:
    """Enforce both a per-minute cap and a minimum gap between requests."""
    global _last_request_time
    async with _rate_lock:
        now = time.time()

        # 1. Minimum inter-request gap (prevents bursting)
        gap_wait = _min_gap_s - (now - _last_request_time)
        if gap_wait > 0:
            await asyncio.sleep(gap_wait)
            now = time.time()

        # 2. Rolling-window RPM cap
        while _request_times and now - _request_times[0] >= 60:
            _request_times.pop(0)
        if len(_request_times) >= _rpm_limit:
            wait = 60 - (now - _request_times[0]) + 1.0
            if wait > 0:
                print(f"    Rate limit: waiting {wait:.1f}s (window full)...")
                await asyncio.sleep(wait)
                now = time.time()

        _last_request_time = now
        _request_times.append(now)


def _clean_html(html: str) -> str:
    """
    Strip non-content elements to minimize token count while preserving
    all data the extraction prompt needs.
    """
    # Remove entire layout/chrome blocks with their contents
    for tag in ("nav", "header", "footer", "aside", "svg", "canvas", "iframe", "noscript"):
        html = re.sub(rf"<{tag}[\s>][\s\S]*?</{tag}>", "", html, flags=re.IGNORECASE)

    # Remove script and style blocks
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)

    # Simplify img tags: keep only src attribute
    def _keep_img_src(m: re.Match) -> str:
        src = re.search(r'src=["\']([^"\']+)["\']', m.group(0), re.IGNORECASE)
        return f'<img src="{src.group(1)}">' if src else ""

    html = re.sub(r"<img[^>]*>", _keep_img_src, html, flags=re.IGNORECASE)

    # Strip all attributes from every other tag
    html = re.sub(r"<([a-zA-Z][a-zA-Z0-9]*)\s[^>]*?>", r"<\1>", html)

    # Remove tags that are now empty
    html = re.sub(r"<[a-zA-Z][a-zA-Z0-9]*>\s*</[a-zA-Z][a-zA-Z0-9]*>", "", html)

    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)

    # Truncate — 30k chars (~7.5k tokens) per listing. With batch size 3 the total
    # prompt is ~90k chars, well within the model's context but enough to capture
    # amenity sections that appear deeper in the page (furnished, laundry, etc.).
    if len(html) > 30000:
        html = html[:30000]

    return html.strip()


def _content_fingerprint(html: str) -> str:
    """
    Generate a content-based fingerprint from raw HTML for cross-site duplicate
    detection before any AI call is made.
    """
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())

    numbers = sorted(set(re.findall(r"\b\d+\b", text)))
    words = sorted(set(w for w in text.split() if len(w) >= 4))

    key = "|".join(numbers[:20]) + "||" + " ".join(words[:80])
    return hashlib.md5(key.encode()).hexdigest()


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


# ── Batched extraction ────────────────────────────────────────────────────────
# Bundle multiple listings into one API call to reduce request count.
# Free tier: 15 RPM but ~1M TPM — we're request-limited, not token-limited.
# Keep at 3 (not 5) to avoid "lost in the middle" where the model misses fields
# for listings buried deep in a large concatenated prompt.
_BATCH_SIZE = 3


def _build_batch_prompt(items: list[tuple[str, str, str]]) -> str:
    """Build a prompt that extracts multiple listings in one API call.

    items: list of (site_name, listing_url, cleaned_html) tuples.
    """
    schema_str = json.dumps(EXTRACTION_FIELDS, indent=2)

    listings_block = ""
    for i, (site_name, url, html) in enumerate(items, 1):
        listings_block += f"\n--- LISTING {i} ---\nSite: {site_name}\nURL: {url}\n\nHTML:\n{html}\n"

    return f"""You are extracting structured rental listing data from raw HTML.
You are given {len(items)} listings. Extract each one separately.

Instructions:
- Extract every field you can find in each listing's HTML.
- Use null for any field you cannot find or are not confident about.
- For boolean fields, only return true/false if explicitly stated. Use null if ambiguous.
- Monthly rent must be a number (no currency symbols). If a price range is given, use the lower bound.
- Currency should be "CAD" unless clearly USD.
- Do not infer or guess values. Only extract what is explicitly present.

Schema (each listing must match this):
{schema_str}

{listings_block}

Return a JSON array of {len(items)} objects, one per listing, in the same order.
No explanation, no markdown fences. Just the JSON array."""


async def _call_gemini(
    client: genai.Client,
    model_name: str,
    prompt: str,
    config: AppConfig,
    label: str = "",
) -> str | None:
    """Make a single Gemini API call with rate limiting and retry."""
    for attempt in range(1, _MAX_RETRIES + 1):
        async with _semaphore:
            await _wait_for_rate_limit()
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=config.ai.temperature,
                        max_output_tokens=config.ai.max_tokens,
                        response_mime_type="application/json",
                    ),
                )
                return response.text.strip()
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower():
                    retry_match = re.search(r"retry in ([\d.]+)s", err_str, re.IGNORECASE)
                    wait = float(retry_match.group(1)) + 1 if retry_match else 30
                    if attempt < _MAX_RETRIES:
                        print(f"  Rate limited{' on ' + label if label else ''}, waiting {wait:.0f}s (attempt {attempt}/{_MAX_RETRIES})...")
                        await asyncio.sleep(wait)
                        continue
                print(f"  Gemini API error{' for ' + label if label else ''}: {e}")
                return None
    return None


def _parse_json_response(text: str) -> list | dict | None:
    """Parse JSON from Gemini response, stripping markdown fences if present."""
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}")
        return None


async def _extract_batch(
    client: genai.Client,
    model_name: str,
    items: list[tuple[str, str, str]],
    config: AppConfig,
) -> list[Listing]:
    """Extract multiple listings from a single batched API call."""
    # Prepare cleaned HTML and hashes
    cleaned_items: list[tuple[str, str, str, str]] = []  # (site, url, cleaned_html, hash)
    for site_name, url, html in items:
        cleaned = _clean_html(html)
        html_hash = hashlib.md5(cleaned.encode()).hexdigest()
        cleaned_items.append((site_name, url, cleaned, html_hash))

    prompt = _build_batch_prompt([(s, u, c) for s, u, c, _ in cleaned_items])
    urls_label = ", ".join(u[:40] for _, u, _, _ in cleaned_items[:2]) + ("..." if len(cleaned_items) > 2 else "")

    text = await _call_gemini(client, model_name, prompt, config, label=f"batch({len(items)})")
    if text is None:
        return []

    data = _parse_json_response(text)
    if data is None:
        # Fallback: try extracting individually
        print(f"  Batch parse failed, falling back to individual extraction...")
        results = []
        for site_name, url, cleaned, html_hash in cleaned_items:
            single_prompt = _build_extraction_prompt(site_name, url, cleaned)
            single_text = await _call_gemini(client, model_name, single_prompt, config, label=url[:60])
            if single_text is None:
                continue
            single_data = _parse_json_response(single_text)
            if isinstance(single_data, dict):
                try:
                    results.append(Listing(url=url, source=site_name, scraped_at=datetime.now(), raw_html_hash=html_hash, **single_data))
                except Exception as e:
                    print(f"  Validation error for {url[:60]}: {e}")
        return results

    # Handle response: should be a JSON array
    if isinstance(data, dict):
        # Model returned a single object instead of array — wrap it
        data = [data]

    if not isinstance(data, list):
        print(f"  Unexpected response type: {type(data)}")
        return []

    listings = []
    for i, item_data in enumerate(data):
        if i >= len(cleaned_items):
            break
        site_name, url, _, html_hash = cleaned_items[i]
        if not isinstance(item_data, dict):
            print(f"  Skipping non-dict item {i} for {url[:60]}")
            continue
        try:
            listing = Listing(
                url=url,
                source=site_name,
                scraped_at=datetime.now(),
                raw_html_hash=html_hash,
                **item_data,
            )
            listings.append(listing)
        except Exception as e:
            print(f"  Validation error for {url[:60]}: {e}")

    return listings


async def _geocode_listing(
    listing: Listing,
    anchor_coords: tuple[float, float] | None,
) -> None:
    """Geocode a listing's address and compute distance to the pre-geocoded anchor."""
    global _last_geocode_time

    if not listing.address or not listing.city:
        return

    query = f"{listing.address}, {listing.city}"

    async with _geocode_lock:
        elapsed = time.time() - _last_geocode_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _last_geocode_time = time.time()

        try:
            loop = asyncio.get_running_loop()
            location = await loop.run_in_executor(None, _geolocator.geocode, query)
        except Exception:
            return

    if location is None:
        return

    listing.latitude = location.latitude
    listing.longitude = location.longitude

    # Compute distance using pre-geocoded anchor coords (no extra Nominatim call)
    if anchor_coords:
        listing.distance_km = round(
            geodesic(
                (listing.latitude, listing.longitude),
                anchor_coords,
            ).km,
            2,
        )


async def extract_all(
    raw_pages: list[tuple[str, str, str]],
    config: AppConfig,
) -> list[Listing]:
    """Extract structured listings from raw HTML pages using Gemini API."""
    if not raw_pages:
        print("No pages to extract.")
        return []

    print(f"\n=== Extracting data from {len(raw_pages)} listing pages ===")

    # Cross-site duplicate detection
    seen_fingerprints: set[str] = set()
    unique_pages: list[tuple[str, str, str]] = []
    for site_name, url, html in raw_pages:
        fp = _content_fingerprint(html)
        if fp in seen_fingerprints:
            print(f"  Skipping cross-site duplicate: {url[:60]}")
            continue
        seen_fingerprints.add(fp)
        unique_pages.append((site_name, url, html))

    skipped = len(raw_pages) - len(unique_pages)
    if skipped:
        print(f"  Skipped {skipped} cross-site duplicate(s) — {len(unique_pages)} unique listings to extract")
    raw_pages = unique_pages

    client = genai.Client(api_key=config.gemini_api_key)
    model_name = config.ai.model

    # Batch listings into groups to reduce API request count
    # Free tier: 10 RPM but ~1M TPM — batching trades tokens for fewer requests
    batches = [
        raw_pages[i : i + _BATCH_SIZE]
        for i in range(0, len(raw_pages), _BATCH_SIZE)
    ]
    total_requests = len(batches)
    est_minutes = total_requests * _min_gap_s / 60
    print(f"  {len(raw_pages)} listings in {total_requests} batches of ≤{_BATCH_SIZE} (~{est_minutes:.1f} min)")

    listings: list[Listing] = []
    for batch_idx, batch in enumerate(batches, 1):
        print(f"  Batch {batch_idx}/{total_requests} ({len(batch)} listings)...")
        batch_results = await _extract_batch(client, model_name, batch, config)
        listings.extend(batch_results)
        print(f"    → {len(batch_results)}/{len(batch)} extracted (total: {len(listings)})")

    print(f"  Extracted {len(listings)} listings successfully")

    # Geocode all listings using pre-computed anchor coords (avoids re-geocoding
    # the anchor once per listing, which was doubling the Nominatim call count).
    anchor_coords: tuple[float, float] | None = None
    if config.search.anchor_lat is not None and config.search.anchor_lng is not None:
        anchor_coords = (config.search.anchor_lat, config.search.anchor_lng)

    if anchor_coords or config.search.anchor_address:
        print(f"  Geocoding {len(listings)} listings (1 req/sec)...")
        for listing in listings:
            await _geocode_listing(listing, anchor_coords)

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
