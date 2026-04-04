from __future__ import annotations

from urllib.parse import quote, urlencode

from src.config import SearchConfig, SiteConfig


def _kijiji(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://www.kijiji.ca/b-apartments-condos/{city}"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["price"] = f"__{int(search.max_monthly_rent)}"
    if search.min_bedrooms is not None:
        params["bedrooms"] = str(search.min_bedrooms)
    query = urlencode(params) if params else ""
    urls = []
    for page in range(1, 4):
        page_part = f"/page-{page}" if page > 1 else ""
        url = f"{base}{page_part}/k0c37l1700273"
        if query:
            url += f"?{query}"
        urls.append(url)
    return urls


def _craigslist(search: SearchConfig) -> list[str]:
    base = "https://toronto.craigslist.org/search/apa"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["max_price"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["min_price"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["min_bedrooms"] = str(search.min_bedrooms)
    if search.max_bedrooms is not None:
        params["max_bedrooms"] = str(search.max_bedrooms)
    if search.min_sqft is not None:
        params["minSqft"] = str(search.min_sqft)
    urls = []
    for page in range(3):
        p = dict(params)
        if page > 0:
            p["s"] = str(page * 120)
        url = f"{base}?{urlencode(p)}" if p else base
        urls.append(url)
    return urls


def _rentals_ca(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://rentals.ca/{city}"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["rent_max"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["rent_min"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["beds_min"] = str(search.min_bedrooms)
    urls = []
    for page in range(1, 4):
        p = dict(params)
        if page > 1:
            p["p"] = str(page)
        url = f"{base}?{urlencode(p)}" if p else base
        urls.append(url)
    return urls


def _padmapper(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://www.padmapper.com/apartments/{city}-on"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["max-price"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["min-price"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["min-bedrooms"] = str(search.min_bedrooms)
    url = f"{base}?{urlencode(params)}" if params else base
    return [url]


def _apartments_com(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://www.apartments.com/{city}-on"
    params: dict[str, str] = {}
    if search.min_bedrooms is not None:
        params["bb"] = str(search.min_bedrooms)
    urls = []
    for page in range(1, 4):
        page_part = f"/{page}" if page > 1 else ""
        url = f"{base}{page_part}"
        if params:
            url += f"?{urlencode(params)}"
        urls.append(url)
    return urls


def _zillow(search: SearchConfig) -> list[str]:
    city = search.city.lower().replace(" ", "-") if search.city else "toronto"
    base = f"https://www.zillow.com/{city}-on/rentals"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["price_max"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["price_min"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["beds_min"] = str(search.min_bedrooms)
    urls = []
    for page in range(1, 4):
        p = dict(params)
        if page > 1:
            p["currentPage"] = str(page)
        url = f"{base}/?{urlencode(p)}" if p else base
        urls.append(url)
    return urls


def _airbnb(search: SearchConfig) -> list[str]:
    base = "https://www.airbnb.ca/s"
    city = search.city or "Toronto"
    location = quote(f"{city}--ON--Canada")
    params: dict[str, str] = {
        "tab_id": "home_tab",
        "refinement_paths[]": "/homes",
        "monthly_stay": "true",
    }
    if search.max_monthly_rent is not None:
        params["price_max"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["price_min"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["min_bedrooms"] = str(search.min_bedrooms)
    if search.move_in_date:
        params["checkin"] = search.move_in_date
    if search.move_in_date and search.lease_duration_months:
        # Airbnb uses checkout date
        from datetime import datetime, timedelta
        try:
            dt = datetime.strptime(search.move_in_date, "%Y-%m-%d")
            checkout = dt + timedelta(days=search.lease_duration_months * 30)
            params["checkout"] = checkout.strftime("%Y-%m-%d")
        except ValueError:
            pass
    url = f"{base}/{location}/homes?{urlencode(params)}"
    return [url]


def _uoft_housing(search: SearchConfig) -> list[str]:
    base = "https://housing.utoronto.ca/all-listings"
    return [base]


def _facebook_marketplace(search: SearchConfig) -> list[str]:
    city = search.city or "Toronto"
    base = f"https://www.facebook.com/marketplace/{city.lower()}/propertyrentals"
    params: dict[str, str] = {}
    if search.max_monthly_rent is not None:
        params["maxPrice"] = str(int(search.max_monthly_rent))
    if search.min_monthly_rent is not None:
        params["minPrice"] = str(int(search.min_monthly_rent))
    if search.min_bedrooms is not None:
        params["minBedrooms"] = str(search.min_bedrooms)
    url = f"{base}?{urlencode(params)}" if params else base
    return [url]


URL_BUILDERS: dict[str, callable] = {
    "kijiji": _kijiji,
    "craigslist": _craigslist,
    "rentals_ca": _rentals_ca,
    "padmapper": _padmapper,
    "apartments_com": _apartments_com,
    "zillow": _zillow,
    "airbnb": _airbnb,
    "uoft_housing": _uoft_housing,
    "facebook_marketplace": _facebook_marketplace,
}


def build_search_urls(site: SiteConfig, search: SearchConfig) -> list[str]:
    builder = URL_BUILDERS.get(site.url_builder)
    if builder is None:
        raise ValueError(f"Unknown url_builder: {site.url_builder}")
    return builder(search)
