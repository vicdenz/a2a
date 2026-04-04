from datetime import datetime

from src.extractor.schema import Listing


def test_listing_minimal():
    listing = Listing(url="https://example.com/1", source="TestSite")
    assert listing.url == "https://example.com/1"
    assert listing.source == "TestSite"
    assert listing.monthly_rent is None
    assert listing.images == []
    assert listing.score is None


def test_listing_full():
    listing = Listing(
        url="https://example.com/2",
        source="Kijiji",
        listing_id="abc123",
        address="123 Main St",
        neighborhood="Annex",
        city="Toronto",
        latitude=43.66,
        longitude=-79.39,
        distance_km=1.5,
        title="Cozy 1BR",
        description="Nice apartment",
        bedrooms=1,
        bathrooms=1,
        unit_type="apartment",
        sqft=500,
        monthly_rent=1800,
        currency="CAD",
        utilities_included=True,
        furnished=True,
        pets_allowed=False,
        parking_included=False,
        laundry_in_unit=True,
        laundry_shared=False,
        outdoor_space=False,
        gym=False,
        dishwasher=True,
        ac=True,
        images=["https://img.com/1.jpg"],
    )
    assert listing.bedrooms == 1
    assert listing.monthly_rent == 1800
    assert listing.furnished is True
    assert len(listing.images) == 1


def test_listing_serialization():
    listing = Listing(url="https://example.com/3", source="Test")
    data = listing.model_dump()
    assert data["url"] == "https://example.com/3"
    assert "score" in data
