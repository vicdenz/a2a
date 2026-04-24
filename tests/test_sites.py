from urllib.parse import parse_qs, urlparse

import pytest

from src.config import RequirementsConfig, SearchConfig, SiteConfig
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
    groups = build_search_urls(_site("rentals_ca"), search)

    # One group per neighbourhood
    slugs = []
    for group in groups:
        parts = urlparse(group[0]).path.strip("/").split("/")
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

    # First URL of first group has no ?p= (page 1), uses rent_max, no bbox/h3
    parsed = urlparse(groups[0][0])
    params = parse_qs(parsed.query)
    assert params["rent_max"] == ["3200"]
    assert "bbox" not in params
    assert "h3" not in params
    assert "p" not in params


def test_rentals_ca_user_provided_neighbourhoods_override():
    """Explicit slugs in requirements take precedence over auto-pick."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6629,  # UofT — would auto-pick yorkville etc.
        anchor_lng=-79.3957,
        max_monthly_rent=3200,
    )
    reqs = RequirementsConfig(
        rentals_ca_neighbourhoods=["the-beaches", "leslieville", "roncesvalles"]
    )
    groups = build_search_urls(_site("rentals_ca"), search, reqs)

    # Order should match the user's list — one group per slug
    assert len(groups) == 3
    slugs = [urlparse(g[0]).path.strip("/").split("/")[-1] for g in groups]
    assert slugs == ["the-beaches", "leslieville", "roncesvalles"]


def test_rentals_ca_pagination_per_group():
    """Each neighbourhood group has its own 3-page sequence."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6629,
        anchor_lng=-79.3957,
        max_monthly_rent=3200,
    )
    groups = build_search_urls(_site("rentals_ca"), search)

    for group in groups:
        assert len(group) == 3
        assert "p=" not in group[0]
        assert "p=2" in group[1]
        assert "p=3" in group[2]


def test_rentals_ca_distant_anchor_fallback_to_closest():
    """An anchor far from every centroid should still return at least the closest."""
    # Anchor way out in Scarborough — no Toronto neighbourhood within 1.5km
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.7800,
        anchor_lng=-79.2000,
        max_monthly_rent=3000,
    )
    groups = build_search_urls(_site("rentals_ca"), search)
    slugs = {urlparse(g[0]).path.strip("/").split("/")[-1] for g in groups}
    # Exactly one group — the fallback closest
    assert len(groups) == 1
    assert len(slugs) == 1


def test_rentals_ca_anchor_inside_the_beaches():
    """An anchor at The Beaches centroid should pick the-beaches (within 1.5km)."""
    search = SearchConfig(
        city="Toronto",
        anchor_lat=43.6692,
        anchor_lng=-79.2963,
        max_monthly_rent=3000,
    )
    groups = build_search_urls(_site("rentals_ca"), search)
    slugs = {urlparse(g[0]).path.strip("/").split("/")[-1] for g in groups}
    assert "the-beaches" in slugs


def test_rentals_ca_no_slug_without_coords():
    """Without anchor coords, fall back to a single city-level group."""
    search = SearchConfig(city="Toronto", max_monthly_rent=3200)
    groups = build_search_urls(_site("rentals_ca"), search)

    assert len(groups) == 1
    parsed = urlparse(groups[0][0])
    assert parsed.path.strip("/") == "toronto"
    params = parse_qs(parsed.query)
    assert params["rent_max"] == ["3200"]


def test_rentals_ca_pagination():
    """Without anchor coords, single city group × 3 pages."""
    search = SearchConfig(city="Toronto")
    groups = build_search_urls(_site("rentals_ca"), search)
    assert len(groups) == 1
    urls = groups[0]
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
    groups = build_search_urls(_site("rentals_ca"), search)
    parsed = urlparse(groups[0][0])
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
    groups = build_search_urls(_site("craigslist"), search)
    assert len(groups) == 1
    parsed = urlparse(groups[0][0])
    params = parse_qs(parsed.query)
    assert "lat" in params
    assert "lon" in params
    assert "search_distance" in params
    assert "max_price" in params


def test_craigslist_unsupported_city():
    """Craigslist should raise ValueError for unsupported cities."""
    with pytest.raises(ValueError, match="Unsupported Craigslist city"):
        build_search_urls(_site("craigslist"), SearchConfig(city="Saskatoon"))


def test_kijiji_unsupported_city():
    """Kijiji should raise ValueError for unsupported cities."""
    with pytest.raises(ValueError, match="Unsupported Kijiji city"):
        build_search_urls(_site("kijiji"), SearchConfig(city="Saskatoon"))


def test_kijiji_max_price():
    """Kijiji should pass max rent as maxPrice."""
    search = SearchConfig(city="Toronto", max_monthly_rent=3000)
    groups = build_search_urls(_site("kijiji"), search)
    assert len(groups) == 1
    assert "maxPrice=3000" in groups[0][0]
