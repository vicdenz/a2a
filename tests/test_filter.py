from src.config import RequirementsConfig
from src.extractor.schema import Listing
from src.pipeline.filter import filter_listings


def _make_listing(**kwargs) -> Listing:
    defaults = {"url": "https://example.com/1", "source": "Test"}
    defaults.update(kwargs)
    return Listing(**defaults)


def _passed(result: list[Listing]) -> list[Listing]:
    return [l for l in result if l.passed_filter]


def test_filter_no_requirements():
    reqs = RequirementsConfig()
    listings = [_make_listing(monthly_rent=2000), _make_listing(monthly_rent=3000)]
    result = filter_listings(listings, reqs)
    # Always returns all listings now
    assert len(result) == 2
    # Both pass with no requirements
    assert all(l.passed_filter for l in result)


def test_filter_max_rent():
    reqs = RequirementsConfig(max_monthly_rent=2000)
    listings = [
        _make_listing(monthly_rent=1800),
        _make_listing(monthly_rent=2500),
        _make_listing(monthly_rent=None),  # Tagged as failed — missing rent
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    passed = _passed(result)
    assert len(passed) == 1
    assert passed[0].monthly_rent == 1800
    # Failed listings should carry a reason
    failed = [l for l in result if not l.passed_filter]
    assert all(l.filter_reason for l in failed)


def test_filter_min_bedrooms():
    reqs = RequirementsConfig(min_bedrooms=2)
    listings = [
        _make_listing(bedrooms=1),
        _make_listing(bedrooms=2),
        _make_listing(bedrooms=None),  # Pass — benefit of the doubt
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    assert len(_passed(result)) == 2


def test_filter_furnished():
    reqs = RequirementsConfig(must_be_furnished=True)
    listings = [
        _make_listing(furnished=True),
        _make_listing(furnished=False),
        _make_listing(furnished=None),  # Pass — benefit of the doubt
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    assert len(_passed(result)) == 2


def test_filter_distance():
    reqs = RequirementsConfig(max_distance_km=3.0)
    listings = [
        _make_listing(distance_km=1.5),
        _make_listing(distance_km=5.0),
        _make_listing(distance_km=None),  # Failed — missing distance
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    passed = _passed(result)
    assert len(passed) == 1
    assert passed[0].distance_km == 1.5


def test_filter_short_term():
    reqs = RequirementsConfig(require_short_term=True)
    listings = [
        _make_listing(short_term_available=True),
        _make_listing(short_term_available=False),  # Failed
        _make_listing(short_term_available=None),  # Pass
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    assert len(_passed(result)) == 2


def test_filter_combined():
    reqs = RequirementsConfig(max_monthly_rent=2000, min_bedrooms=1)
    listings = [
        _make_listing(monthly_rent=1500, bedrooms=2),  # Pass
        _make_listing(monthly_rent=2500, bedrooms=2),  # Fail rent
        _make_listing(monthly_rent=1500, bedrooms=0.5),  # Fail bedrooms
    ]
    result = filter_listings(listings, reqs)
    assert len(result) == 3
    passed = _passed(result)
    assert len(passed) == 1
    assert passed[0].monthly_rent == 1500
