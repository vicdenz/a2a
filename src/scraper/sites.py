from __future__ import annotations

from urllib.parse import quote, urlencode

from src.config import SearchConfig, SiteConfig


# ── Kijiji ────────────────────────────────────────────────────────────────────
# URL format: /b-apartments-condos/{city-slug}/page-{N}/c37l{location_code}
# Filters: maxPrice/minPrice as query params, bedrooms via path attribute codes.
# Toronto slug is "city-of-toronto", location code 1700273.

_KIJIJI_CITY_SLUGS: dict[str, tuple[str, str]] = {
    # city name -> (url slug, location code)
    "toronto": ("city-of-toronto", "1700273"),
    "ottawa": ("ottawa", "1700185"),
    "vancouver": ("vancouver", "1700287"),
    "montreal": ("ville-de-montreal", "1700281"),
    "calgary": ("calgary", "1700199"),
    "edmonton": ("edmonton", "1700203"),
}


def _kijiji(search: SearchConfig) -> list[str]:
    city_key = (search.city or "Toronto").lower()
    slug, loc_code = _KIJIJI_CITY_SLUGS.get(city_key, ("city-of-toronto", "1700273"))

    # Build the category+attribute suffix
    suffix = f"c37l{loc_code}"

    # Only use max_monthly_rent in URL (broad net). Min rent and bedrooms are
    # checked later by the AI extraction + requirements filter, so we don't
    # exclude "1+den" units or good deals at the URL level.
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["maxPrice"] = str(int(search.max_monthly_rent))

    urls = []
    for page in range(1, 4):
        page_part = f"/page-{page}" if page > 1 else ""
        url = f"https://www.kijiji.ca/b-apartments-condos/{slug}{page_part}/{suffix}"
        if params:
            url += f"?{urlencode(params)}"
        urls.append(url)
    return urls


# ── Craigslist ────────────────────────────────────────────────────────────────

def _craigslist(search: SearchConfig) -> list[str]:
    base = "https://toronto.craigslist.org/search/apa"
    # Only use max price and location in URL — cast a broad net.
    # Bedroom count and min price are checked by the AI + requirements filter,
    # so we don't exclude "1+den" or cheap-but-great listings at the URL level.
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["max_price"] = str(int(search.max_monthly_rent))
    # Radius search: Craigslist supports lat/lon + search_distance (in miles)
    if search.anchor_lat is not None and search.anchor_lng is not None:
        params["lat"] = f"{search.anchor_lat:.6f}"
        params["lon"] = f"{search.anchor_lng:.6f}"
        if search.max_distance_km is not None:
            miles = search.max_distance_km / 1.60934
            params["search_distance"] = f"{miles:.1f}"
    urls = []
    for page in range(3):
        p = dict(params)
        if page > 0:
            p["s"] = str(page * 120)
        url = f"{base}?{urlencode(p)}" if p else base
        urls.append(url)
    return urls


# ── Rentals.ca ────────────────────────────────────────────────────────────────

def _rentals_ca(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://rentals.ca/{city}"
    # Only use max rent in URL — cast a broad net.
    # Min rent and bedroom count are checked by the AI + requirements filter,
    # so we don't exclude "1+den" units or budget finds at the URL level.
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["rent_max"] = str(int(search.max_monthly_rent))
    urls = []
    for page in range(1, 4):
        p = dict(params)
        if page > 1:
            p["p"] = str(page)
        url = f"{base}?{urlencode(p)}" if p else base
        urls.append(url)
    return urls


# ── Airbnb ────────────────────────────────────────────────────────────────────
# Pagination via items_offset query param (increments of 20).

def _airbnb(search: SearchConfig) -> list[str]:
    base = "https://www.airbnb.ca/s"
    city = search.city or "Toronto"
    location = quote(f"{city}--ON--Canada")
    # Only use max price, dates, and monthly_stay in URL — cast a broad net.
    # Min price and bedroom count are checked by the AI + requirements filter.
    params: dict[str, str] = {
        "tab_id": "home_tab",
        "refinement_paths[]": "/homes",
        "monthly_stay": "true",
    }
    if search.max_monthly_rent is not None:
        params["price_max"] = str(int(search.max_monthly_rent))
    if search.move_in_date:
        params["checkin"] = search.move_in_date
    if search.move_in_date and search.lease_duration_months:
        from datetime import datetime, timedelta
        try:
            dt = datetime.strptime(search.move_in_date, "%Y-%m-%d")
            checkout = dt + timedelta(days=search.lease_duration_months * 30)
            params["checkout"] = checkout.strftime("%Y-%m-%d")
        except ValueError:
            pass

    urls = []
    for page in range(3):
        p = dict(params)
        if page > 0:
            p["items_offset"] = str(page * 20)
        url = f"{base}/{location}/homes?{urlencode(p)}"
        urls.append(url)
    return urls


# ── Facebook Marketplace ─────────────────────────────────────────────────────

def _facebook_marketplace(search: SearchConfig) -> list[str]:
    city = search.city or "Toronto"
    base = f"https://www.facebook.com/marketplace/{city.lower()}/propertyrentals"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["maxPrice"] = str(int(search.max_monthly_rent))
    url = f"{base}?{urlencode(params)}" if params else base
    return [url]


# ── Registry ─────────────────────────────────────────────────────────────────

URL_BUILDERS: dict[str, callable] = {
    "kijiji": _kijiji,
    "craigslist": _craigslist,
    "rentals_ca": _rentals_ca,

    "airbnb": _airbnb,
    "facebook_marketplace": _facebook_marketplace,
}


def build_search_urls(site: SiteConfig, search: SearchConfig) -> list[str]:
    builder = URL_BUILDERS.get(site.url_builder)
    if builder is None:
        raise ValueError(f"Unknown url_builder: {site.url_builder}")
    return builder(search)
