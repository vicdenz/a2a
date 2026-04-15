from urllib.parse import parse_qs, urlparse

from src.config import SearchConfig, SiteConfig
from src.scraper.sites import build_search_urls


def _site(builder: str) -> SiteConfig:
    return SiteConfig(
        name="Test",
        enabled=True,
        base_url="https://example.com",
        url_builder=builder,
        strategy="crawlee",
    )


def test_rentals_ca_picks_adjacent_neighbourhoods():
    """UofT anchor should pick all neighbourhoods whose centroids are within 1.5km."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6629,
        anchor_lng=-79.3957,
        max_distance_km=4.0,
        max_monthly_rent=3200,
    )
    urls = build_search_urls(_site("rentals_ca"), search)

    # Extract unique slugs from the URL list
    slugs = []
    for u in urls:
        parts = urlparse(u).path.strip("/").split("/")
        if len(parts) == 2:
            slugs.append(parts[1])
    unique_slugs = list(dict.fromkeys(slugs))

    # Should include the cluster of UofT-adjacent neighbourhoods (multiple, not just one)
    adjacent = {"yorkville", "the-annex", "kensington-chinatown", "bay-street-corridor", "church-yonge-corridor"}
    assert len(unique_slugs) >= 3
    assert set(unique_slugs).issubset(adjacent)

    # Should NOT include clearly-out-of-the-way neighbourhoods (>1.5 km away)
    for far in ("the-beaches", "leslieville", "high-park-north", "yonge-and-eglinton", "roncesvalles"):
        assert far not in unique_slugs

    # First URL has no ?p= (page 1), all use rent_max, no bbox/h3
    parsed = urlparse(urls[0])
    params = parse_qs(parsed.query)
    assert params["rent_max"] == ["3200"]
    assert "bbox" not in params
    assert "h3" not in params
    assert "p" not in params


def test_rentals_ca_interleaves_pages():
    """Pages are interleaved so every neighbourhood is sampled before page 2."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6629,
        anchor_lng=-79.3957,
        max_monthly_rent=3200,
    )
    urls = build_search_urls(_site("rentals_ca"), search)

    # Partition URLs by page: page 1 has no 'p=', page 2 has 'p=2', etc.
    page1 = [u for u in urls if "p=" not in u]
    page2 = [u for u in urls if "p=2" in u]
    assert len(page1) >= 3  # multiple neighbourhoods
    assert len(page2) == len(page1)  # same neighbourhoods repeated

    # All page-1 URLs come before any page-2 URL in the emitted list
    last_page1_idx = max(i for i, u in enumerate(urls) if "p=" not in u)
    first_page2_idx = min(i for i, u in enumerate(urls) if "p=2" in u)
    assert last_page1_idx < first_page2_idx


def test_rentals_ca_distant_anchor_fallback_to_closest():
    """An anchor far from every centroid should still return at least the closest."""
    # Anchor way out in Scarborough — no Toronto neighbourhood within 1.5km
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.7800,
        anchor_lng=-79.2000,
        max_monthly_rent=3000,
    )
    urls = build_search_urls(_site("rentals_ca"), search)
    slugs = {urlparse(u).path.strip("/").split("/")[-1] for u in urls}
    # Exactly one slug — the fallback closest
    assert len(slugs) == 1


def test_rentals_ca_anchor_inside_the_beaches():
    """An anchor at The Beaches centroid should pick the-beaches (within 1.5km)."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6692,
        anchor_lng=-79.2963,
        max_monthly_rent=3000,
    )
    urls = build_search_urls(_site("rentals_ca"), search)
    slugs = {urlparse(u).path.strip("/").split("/")[-1] for u in urls}
    assert "the-beaches" in slugs


def test_rentals_ca_no_slug_without_coords():
    """Without anchor coords, fall back to the city-level URL."""
    search = SearchConfig(city="Toronto", max_monthly_rent=3200)
    urls = build_search_urls(_site("rentals_ca"), search)

    parsed = urlparse(urls[0])
    assert parsed.path.strip("/") == "toronto"
    params = parse_qs(parsed.query)
    assert params["rent_max"] == ["3200"]


def test_rentals_ca_pagination():
    """Rentals.ca page 2+ should include p= param; without anchor, single city URL × 3 pages."""
    search = SearchConfig(city="Toronto")
    urls = build_search_urls(_site("rentals_ca"), search)
    # No anchor coords → single city URL × 3 pages
    assert len(urls) == 3
    assert "p=" not in urls[0]
    assert "p=2" in urls[1]
    assert "p=3" in urls[2]


def test_rentals_ca_only_price_filter():
    """Only rent_max should appear — no furnished/bedroom/bbox/h3 URL filters."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6629,
        anchor_lng=-79.3957,
        max_monthly_rent=3200,
    )
    urls = build_search_urls(_site("rentals_ca"), search)
    parsed = urlparse(urls[0])
    params = parse_qs(parsed.query)
    # Only rent_max allowed as a URL filter
    assert set(params.keys()) == {"rent_max"}


def test_craigslist_radius():
    """Craigslist should include lat/lon/search_distance params."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6611,
        anchor_lng=-79.3957,
        max_distance_km=5.0,
        max_monthly_rent=2500,
    )
    urls = build_search_urls(_site("craigslist"), search)
    parsed = urlparse(urls[0])
    params = parse_qs(parsed.query)
    assert "lat" in params
    assert "lon" in params
    assert "search_distance" in params
    assert "max_price" in params


def test_kijiji_max_price():
    """Kijiji should pass max rent as maxPrice."""
    search = SearchConfig(city="Toronto", max_monthly_rent=3000)
    urls = build_search_urls(_site("kijiji"), search)
    assert "maxPrice=3000" in urls[0]
