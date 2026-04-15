from __future__ import annotations

from urllib.parse import quote, urlencode

from geopy.distance import geodesic

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
# Rentals.ca serves geographically-tight listings on neighbourhood-slug URLs
# (e.g. /toronto/yorkville). City-level URLs return broad, non-centered results
# even with bbox/h3 params. To scope results to the anchor, we scrape every
# neighbourhood whose centroid is within _RENTALS_CA_ADJACENCY_KM of the anchor
# (i.e. truly adjacent, not "anywhere in max_distance_km radius"). Falls back
# to the single closest slug if none are within the adjacency threshold.

# Only neighbourhoods whose centroid is within this many km of the anchor are
# scraped. Distances larger than this aren't "adjacent" — they'd include
# far-away neighbourhoods that happen to fall within max_distance_km.
_RENTALS_CA_ADJACENCY_KM = 1.5

_RENTALS_CA_NEIGHBOURHOODS: dict[str, list[tuple[str, float, float]]] = {
    # city: [(slug, lat, lng), ...]
    "toronto": [
        ("trinity-bellwoods", 43.6474, -79.4137),
        ("yonge-and-eglinton", 43.7064, -79.3986),
        ("the-annex", 43.6703, -79.4053),
        ("liberty-village", 43.6391, -79.4200),
        ("yonge-stclair", 43.6872, -79.3940),
        ("high-park-north", 43.6600, -79.4650),
        ("church-yonge-corridor", 43.6613, -79.3805),
        ("midtown-toronto", 43.6970, -79.3957),
        ("bay-street-corridor", 43.6550, -79.3840),
        ("leslieville", 43.6631, -79.3345),
        ("yorkville", 43.6707, -79.3928),
        ("corktown", 43.6553, -79.3651),
        ("south-riverdale", 43.6600, -79.3450),
        ("financial-district", 43.6484, -79.3810),
        ("moss-park", 43.6551, -79.3686),
        ("mount-pleasant-west", 43.7035, -79.3895),
        ("kensington-chinatown", 43.6542, -79.4006),
        ("mount-pleasant-east", 43.7098, -79.3825),
        ("the-beaches", 43.6692, -79.2963),
        ("roncesvalles", 43.6475, -79.4483),
    ],
}


def _rentals_ca(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    # Only use max rent — cast a broad net. Bedroom count, furnished, etc.
    # are checked by the AI + requirements filter downstream.
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["rent_max"] = str(int(search.max_monthly_rent))

    # Pick every neighbourhood whose centroid is within _RENTALS_CA_ADJACENCY_KM
    # of the anchor. Sort by ascending distance so the closest come first.
    slugs: list[str] = []
    neighbourhoods = _RENTALS_CA_NEIGHBOURHOODS.get(city)
    if (
        neighbourhoods
        and search.anchor_lat is not None
        and search.anchor_lng is not None
    ):
        anchor = (search.anchor_lat, search.anchor_lng)
        ranked = sorted(
            ((slug, geodesic(anchor, (lat, lng)).km) for slug, lat, lng in neighbourhoods),
            key=lambda x: x[1],
        )
        slugs = [slug for slug, dist in ranked if dist <= _RENTALS_CA_ADJACENCY_KM]
        # Fallback: if no neighbourhood is within the adjacency threshold,
        # use the single closest so we still return something.
        if not slugs and ranked:
            slugs = [ranked[0][0]]

    if slugs:
        bases = [f"https://rentals.ca/{city}/{slug}" for slug in slugs]
    else:
        bases = [f"https://rentals.ca/{city}"]

    # Interleave: all neighbourhoods page 1, then all page 2, etc. The engine
    # short-circuits once max_listings_per_site is reached, so this ordering
    # guarantees we sample every adjacent neighbourhood before re-paginating.
    urls = []
    for page in range(1, 4):
        for base in bases:
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
