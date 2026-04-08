from __future__ import annotations

from src.config import PreferenceConfig, RequirementsConfig, SearchConfig
from src.extractor.schema import Listing


def score_and_rank(
    listings: list[Listing],
    preferences: list[PreferenceConfig],
    search: SearchConfig,
) -> list[Listing]:
    """Score listings by weighted preferences and sort descending."""
    if not listings:
        return listings

    enabled = [p for p in preferences if p.enabled]
    if not enabled:
        # No preferences — return as-is with score 0
        for listing in listings:
            listing.score = 0.0
            listing.score_breakdown = {}
        return listings

    # Precompute min/max for price and distance across all listings
    rents = [l.monthly_rent for l in listings if l.monthly_rent is not None]
    min_rent = min(rents) if rents else 0
    max_rent = max(rents) if rents else 1

    distances = [l.distance_km for l in listings if l.distance_km is not None]
    max_distance = search.max_distance_km or (max(distances) if distances else 10)

    for listing in listings:
        breakdown: dict[str, float] = {}
        total = 0.0

        for pref in enabled:
            points = 0.0

            if pref.type == "distance":
                if listing.distance_km is not None:
                    if listing.distance_km <= 0.5:
                        points = pref.weight
                    elif listing.distance_km >= max_distance:
                        points = 0.0
                    else:
                        # Linear interpolation: closer = more points
                        ratio = 1.0 - (listing.distance_km - 0.5) / (max_distance - 0.5)
                        points = pref.weight * max(0.0, ratio)

            elif pref.type == "price_asc":
                if listing.monthly_rent is not None and max_rent > min_rent:
                    ratio = 1.0 - (listing.monthly_rent - min_rent) / (max_rent - min_rent)
                    points = pref.weight * ratio
                elif listing.monthly_rent is not None:
                    points = pref.weight  # All same price — full points

            elif pref.type == "boolean_field":
                if pref.field:
                    val = getattr(listing, pref.field, None)
                    if val is True:
                        points = pref.weight

            elif pref.type == "neighborhood_match":
                # Full points if listing's neighborhood matches any preferred value.
                # Case-insensitive substring match (e.g. "Yorkville" matches "Bloor-Yorkville").
                # No points if neighborhood unknown — benefit of the doubt already handled by
                # the distance scorer which rewards proximity to the anchor.
                if pref.values and listing.neighborhood is not None:
                    hood = listing.neighborhood.lower()
                    if any(v.lower() in hood or hood in v.lower() for v in pref.values):
                        points = pref.weight

            breakdown[pref.name] = round(points, 2)
            total += points

        listing.score = round(total, 2)
        listing.score_breakdown = breakdown

    # Sort: by score descending, then null-price listings last
    listings.sort(
        key=lambda l: (
            l.monthly_rent is not None,  # False (null price) sorts before True
            l.score or 0,
        ),
        reverse=True,
    )

    return listings
