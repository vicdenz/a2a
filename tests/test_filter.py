from src.config import RequirementsConfig
from src.extractor.schema import Listing
from src.pipeline.filter import filter_listings


def _make_listing(**kwargs) -> Listing:
    defaults = {"url": "https://example.com/1", "source": "Test"}
    defaults.update(kwargs)
    return Listing(**defaults)


def test_filter_no_requirements():
    reqs = RequirementsConfig()
    listings = [_make_listing(monthly_rent=2000), _make_listing(monthly_rent=3000)]
    result = filter_listings(listings, reqs)
    assert len(result) == 2


def test_filter_max_rent():
    reqs = RequirementsConfig(max_monthly_rent=2000)
    listings = [
        _make_listing(monthly_rent=1800),
        _make_listing(monthly_rent=2500),
        _make_listing(monthly_rent=None),  # Dropped — missing rent
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 1
    assert result[0].monthly_rent == 1800


def test_filter_min_bedrooms():
    reqs = RequirementsConfig(min_bedrooms=2)
    listings = [
        _make_listing(bedrooms=1),
        _make_listing(bedrooms=2),
        _make_listing(bedrooms=None),  # Kept — benefit of the doubt
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 2


def test_filter_furnished():
    reqs = RequirementsConfig(must_be_furnished=True)
    listings = [
        _make_listing(furnished=True),
        _make_listing(furnished=False),
        _make_listing(furnished=None),  # Kept — benefit of the doubt
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 2


def test_filter_distance():
    reqs = RequirementsConfig(max_distance_km=3.0)
    listings = [
        _make_listing(distance_km=1.5),
        _make_listing(distance_km=5.0),
        _make_listing(distance_km=None),  # Dropped — missing distance
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 1
    assert result[0].distance_km == 1.5


def test_filter_short_term():
    reqs = RequirementsConfig(short_term_ok=True)
    listings = [
        _make_listing(short_term_available=True),
        _make_listing(short_term_available=False),  # Dropped
        _make_listing(short_term_available=None),  # Kept
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 2


def test_filter_combined():
    reqs = RequirementsConfig(max_monthly_rent=2000, min_bedrooms=1)
    listings = [
        _make_listing(monthly_rent=1500, bedrooms=2),  # Pass
        _make_listing(monthly_rent=2500, bedrooms=2),  # Fail rent
        _make_listing(monthly_rent=1500, bedrooms=0.5),  # Fail bedrooms
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 1
    assert result[0].monthly_rent == 1500
