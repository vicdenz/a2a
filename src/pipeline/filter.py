from __future__ import annotations

from src.config import RequirementsConfig
from src.extractor.schema import Listing


def filter_listings(listings: list[Listing], requirements: RequirementsConfig) -> list[Listing]:
    """Apply hard requirement filters. Listings failing ANY enabled filter are dropped."""
    passed: list[Listing] = []
    drop_counts: dict[str, int] = {}

    for listing in listings:
        dropped = False

        # allowed_neighborhoods — if set, drop listings whose neighborhood
        # is known but doesn't match any of the allowed values (case-insensitive).
        # Listings with unknown neighborhood are kept (benefit of the doubt).
        if requirements.allowed_neighborhoods:
            allowed = [n.lower() for n in requirements.allowed_neighborhoods]
            if listing.neighborhood is not None:
                listing_hood = listing.neighborhood.lower()
                if not any(a in listing_hood or listing_hood in a for a in allowed):
                    drop_counts["allowed_neighborhoods"] = drop_counts.get("allowed_neighborhoods", 0) + 1
                    dropped = True

        # max_monthly_rent — drop if missing or exceeds
        if not dropped and requirements.max_monthly_rent is not None:
            if listing.monthly_rent is None or listing.monthly_rent > requirements.max_monthly_rent:
                drop_counts["max_monthly_rent"] = drop_counts.get("max_monthly_rent", 0) + 1
                dropped = True

        # min_bedrooms — keep if missing (benefit of the doubt)
        if not dropped and requirements.min_bedrooms is not None:
            if listing.bedrooms is not None and listing.bedrooms < requirements.min_bedrooms:
                drop_counts["min_bedrooms"] = drop_counts.get("min_bedrooms", 0) + 1
                dropped = True

        # max_distance_km — drop if missing or exceeds
        if not dropped and requirements.max_distance_km is not None:
            if listing.distance_km is None or listing.distance_km > requirements.max_distance_km:
                drop_counts["max_distance_km"] = drop_counts.get("max_distance_km", 0) + 1
                dropped = True

        # must_be_furnished — keep if missing (benefit of the doubt)
        if not dropped and requirements.must_be_furnished is not None:
            if listing.furnished is not None and listing.furnished != requirements.must_be_furnished:
                drop_counts["must_be_furnished"] = drop_counts.get("must_be_furnished", 0) + 1
                dropped = True

        # must_allow_pets — keep if missing
        if not dropped and requirements.must_allow_pets is not None:
            if listing.pets_allowed is not None and listing.pets_allowed != requirements.must_allow_pets:
                drop_counts["must_allow_pets"] = drop_counts.get("must_allow_pets", 0) + 1
                dropped = True

        # must_have_laundry — check both in-unit and shared
        if not dropped and requirements.must_have_laundry is not None and requirements.must_have_laundry:
            has_laundry = (listing.laundry_in_unit is True) or (listing.laundry_shared is True)
            if listing.laundry_in_unit is not None or listing.laundry_shared is not None:
                if not has_laundry:
                    drop_counts["must_have_laundry"] = drop_counts.get("must_have_laundry", 0) + 1
                    dropped = True

        # must_have_parking — keep if missing
        if not dropped and requirements.must_have_parking is not None:
            if listing.parking_included is not None and listing.parking_included != requirements.must_have_parking:
                drop_counts["must_have_parking"] = drop_counts.get("must_have_parking", 0) + 1
                dropped = True

        # short_term_ok — keep if missing
        if not dropped and requirements.short_term_ok:
            if listing.short_term_available is not None and listing.short_term_available is False:
                drop_counts["short_term_ok"] = drop_counts.get("short_term_ok", 0) + 1
                dropped = True

        if not dropped:
            passed.append(listing)

    # Log filter results
    total_dropped = len(listings) - len(passed)
    print(f"  Filtered: {len(passed)} passed, {total_dropped} dropped")
    for rule, count in sorted(drop_counts.items()):
        print(f"    {rule}: {count} dropped")

    # Show distance breakdown for passed listings
    if passed and requirements.max_distance_km is not None:
        with_dist = [(l.distance_km, l.neighborhood or l.address or l.url[:50]) for l in passed if l.distance_km is not None]
        no_dist = [l for l in passed if l.distance_km is None]
        if with_dist:
            with_dist.sort()
            print(f"  Distance range of passed listings: {with_dist[0][0]:.1f}–{with_dist[-1][0]:.1f} km")
        if no_dist:
            print(f"  Warning: {len(no_dist)} passed listing(s) have no distance (geocoding failed)")

    return passed
