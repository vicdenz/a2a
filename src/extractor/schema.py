from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Listing(BaseModel):
    # Identity
    url: str
    source: str
    listing_id: str | None = None

    # Location
    address: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None

    # Unit details
    title: str | None = None
    description: str | None = None
    bedrooms: float | None = None
    bathrooms: float | None = None
    unit_type: str | None = None
    sqft: int | None = None
    floor: int | None = None

    # Pricing
    monthly_rent: float | None = None
    currency: str | None = None
    utilities_included: bool | None = None
    utilities_detail: str | None = None

    # Availability
    available_date: str | None = None
    lease_term: str | None = None
    short_term_available: bool | None = None

    # Amenities
    furnished: bool | None = None
    pets_allowed: bool | None = None
    parking_included: bool | None = None
    parking_detail: str | None = None
    laundry_in_unit: bool | None = None
    laundry_shared: bool | None = None
    outdoor_space: bool | None = None
    gym: bool | None = None
    dishwasher: bool | None = None
    ac: bool | None = None

    # Media
    images: list[str] = Field(default_factory=list)

    # Scoring (populated by pipeline)
    score: float | None = None
    score_breakdown: dict | None = None

    # Filtering (populated by pipeline)
    passed_filter: bool | None = None
    filter_reason: str | None = None

    # Meta
    scraped_at: datetime = Field(default_factory=datetime.now)
    raw_html_hash: str | None = None


# JSON schema string for the extraction prompt — excludes pipeline-only fields
EXTRACTION_FIELDS: dict = {
    "listing_id": "string or null",
    "address": "string or null",
    "neighborhood": "string or null",
    "city": "string or null",
    "title": "string or null",
    "description": "string or null — first 500 chars of listing description",
    "bedrooms": "number or null — 0.5 for bachelor/studio",
    "bathrooms": "number or null",
    "unit_type": "string or null — apartment | condo | basement | house | room | studio",
    "sqft": "integer or null",
    "floor": "integer or null",
    "monthly_rent": "number or null — no currency symbols",
    "currency": "string or null — CAD or USD",
    "utilities_included": "boolean or null",
    "utilities_detail": "string or null",
    "available_date": "string or null — ISO date or natural language",
    "lease_term": "string or null",
    "short_term_available": "boolean or null",
    "furnished": "boolean or null",
    "pets_allowed": "boolean or null",
    "parking_included": "boolean or null",
    "parking_detail": "string or null",
    "laundry_in_unit": "boolean or null",
    "laundry_shared": "boolean or null",
    "outdoor_space": "boolean or null",
    "gym": "boolean or null",
    "dishwasher": "boolean or null",
    "ac": "boolean or null",
    "images": "list of image URL strings",
}
