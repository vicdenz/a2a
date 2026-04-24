from src.config import PreferenceConfig, SearchConfig
from src.extractor.schema import Listing
from src.pipeline.scorer import score_and_rank


def _make_listing(**kwargs) -> Listing:
    defaults = {"url": "https://example.com/1", "source": "Test"}
    defaults.update(kwargs)
    return Listing(**defaults)


def _pref(name, weight, ptype, field=None, enabled=True) -> PreferenceConfig:
    return PreferenceConfig(
        name=name, enabled=enabled, weight=weight,
        description="", type=ptype, field=field,
    )


def test_scorer_boolean_field():
    prefs = [_pref("Furnished", 6, "boolean_field", field="furnished")]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(furnished=True),
        _make_listing(furnished=False),
        _make_listing(furnished=None),
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 6.0
    assert result[1].score == 0.0
    assert result[2].score == 0.0


def test_scorer_price_asc():
    prefs = [_pref("Lower rent", 8, "price_asc")]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(monthly_rent=1000),
        _make_listing(monthly_rent=2000),
        _make_listing(monthly_rent=1500),
    ]
    result = score_and_rank(listings, prefs, search)
    # Cheapest should have highest score
    assert result[0].monthly_rent == 1000
    assert result[0].score == 8.0
    assert result[-1].monthly_rent == 2000
    assert result[-1].score == 0.0


def test_scorer_distance():
    prefs = [_pref("Close", 10, "distance")]
    search = SearchConfig(city="Toronto", max_distance_km=5.0)
    listings = [
        _make_listing(distance_km=0.3),   # Very close
        _make_listing(distance_km=2.5),   # Mid
        _make_listing(distance_km=5.0),   # At max
        _make_listing(distance_km=None),  # Unknown
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].distance_km == 0.3
    assert result[0].score == 10.0  # Within 0.5 km = full points
    assert result[-1].score == 0.0


def test_scorer_disabled_preference():
    prefs = [
        _pref("Furnished", 6, "boolean_field", field="furnished", enabled=False),
    ]
    search = SearchConfig(city="Toronto")
    listings = [_make_listing(furnished=True)]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 0.0


def test_scorer_multiple_preferences():
    prefs = [
        _pref("Lower rent", 8, "price_asc"),
        _pref("Furnished", 6, "boolean_field", field="furnished"),
    ]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(monthly_rent=1000, furnished=True),   # 8 + 6 = 14
        _make_listing(monthly_rent=2000, furnished=True),   # 0 + 6 = 6
        _make_listing(monthly_rent=1000, furnished=False),  # 8 + 0 = 8
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 14.0
    assert result[1].score == 8.0
    assert result[2].score == 6.0


def test_scorer_null_price_last():
    prefs = [_pref("Lower rent", 8, "price_asc")]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(monthly_rent=None),
        _make_listing(monthly_rent=1500),
    ]
    result = score_and_rank(listings, prefs, search)
    # Null-price listing should be last
    assert result[-1].monthly_rent is None


def test_scorer_distance_at_boundary():
    """Distance exactly at 0.5km gets full points, exactly at max gets 0."""
    prefs = [_pref("Close", 10, "distance")]
    search = SearchConfig(city="Toronto", max_distance_km=5.0)
    listings = [
        _make_listing(distance_km=0.5),
        _make_listing(distance_km=5.0),
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 10.0
    assert result[1].score == 0.0


def test_scorer_distance_beyond_max():
    """Distance beyond max_distance_km should score 0."""
    prefs = [_pref("Close", 10, "distance")]
    search = SearchConfig(city="Toronto", max_distance_km=5.0)
    listings = [_make_listing(distance_km=8.0)]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 0.0


def test_scorer_price_asc_all_same():
    """When all listings have the same price, all get full points."""
    prefs = [_pref("Lower rent", 8, "price_asc")]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(monthly_rent=1500),
        _make_listing(monthly_rent=1500),
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].score == 8.0
    assert result[1].score == 8.0


def test_scorer_passed_filter_sorted_first():
    """Passed-filter listings should appear before filtered-out ones regardless of score."""
    prefs = [_pref("Lower rent", 8, "price_asc")]
    search = SearchConfig(city="Toronto")
    listings = [
        _make_listing(monthly_rent=1000, passed_filter=False),
        _make_listing(monthly_rent=2000, passed_filter=True),
    ]
    result = score_and_rank(listings, prefs, search)
    assert result[0].passed_filter is True
    assert result[1].passed_filter is False


def test_scorer_requirements_max_distance_fallback():
    """Scorer should use requirements.max_distance_km when search.max_distance_km is None."""
    from src.config import RequirementsConfig
    prefs = [_pref("Close", 10, "distance")]
    search = SearchConfig(city="Toronto")
    reqs = RequirementsConfig(max_distance_km=3.0)
    listings = [
        _make_listing(distance_km=0.3),
        _make_listing(distance_km=3.0),
    ]
    result = score_and_rank(listings, prefs, search, reqs)
    assert result[0].score == 10.0
    assert result[1].score == 0.0
