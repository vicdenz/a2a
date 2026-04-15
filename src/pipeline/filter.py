from __future__ import annotations

from src.config import RequirementsConfig
from src.extractor.schema import Listing


def filter_listings(listings: list[Listing], requirements: RequirementsConfig) -> list[Listing]:
    """Tag listings with passed_filter / filter_reason. Returns ALL listings unchanged in count."""
    drop_counts: dict[str, int] = {}
    passed_count = 0

    for listing in listings:
        drop_reason: str | None = None

        # allowed_neighborhoods — if set, drop listings whose neighborhood
        # is known but doesn't match any of the allowed values (case-insensitive).
        # Listings with unknown neighborhood are kept (benefit of the doubt).
        if requirements.allowed_neighborhoods:
            allowed = [n.lower() for n in requirements.allowed_neighborhoods]
            if listing.neighborhood is not None:
                listing_hood = listing.neighborhood.lower()
                if not any(a in listing_hood or listing_hood in a for a in allowed):
                    drop_reason = "allowed_neighborhoods"

        # max_monthly_rent — drop if missing or exceeds
        if drop_reason is None and requirements.max_monthly_rent is not None:
            if listing.monthly_rent is None:
                drop_reason = "max_monthly_rent (rent unknown)"
            elif listing.monthly_rent > requirements.max_monthly_rent:
                drop_reason = f"max_monthly_rent (${listing.monthly_rent:.0f} > ${requirements.max_monthly_rent})"

        # min_bedrooms — keep if missing (benefit of the doubt)
        if drop_reason is None and requirements.min_bedrooms is not None:
            if listing.bedrooms is not None and listing.bedrooms < requirements.min_bedrooms:
                drop_reason = f"min_bedrooms ({listing.bedrooms} < {requirements.min_bedrooms})"

        # max_distance_km — drop if missing or exceeds
        if drop_reason is None and requirements.max_distance_km is not None:
            if listing.distance_km is None:
                drop_reason = "max_distance_km (distance unknown — geocoding failed or address not extracted)"
            elif listing.distance_km > requirements.max_distance_km:
                drop_reason = f"max_distance_km ({listing.distance_km:.1f}km > {requirements.max_distance_km}km)"

        # must_be_furnished — keep if missing (benefit of the doubt)
        if drop_reason is None and requirements.must_be_furnished is not None:
            if listing.furnished is not None and listing.furnished != requirements.must_be_furnished:
                drop_reason = f"must_be_furnished (extracted: {listing.furnished})"

        # must_allow_pets — keep if missing
        if drop_reason is None and requirements.must_allow_pets is not None:
            if listing.pets_allowed is not None and listing.pets_allowed != requirements.must_allow_pets:
                drop_reason = f"must_allow_pets (extracted: {listing.pets_allowed})"

        # must_have_laundry — check both in-unit and shared
        if drop_reason is None and requirements.must_have_laundry is not None and requirements.must_have_laundry:
            has_laundry = (listing.laundry_in_unit is True) or (listing.laundry_shared is True)
            if listing.laundry_in_unit is not None or listing.laundry_shared is not None:
                if not has_laundry:
                    drop_reason = "must_have_laundry (explicitly no laundry)"

        # must_have_parking — keep if missing
        if drop_reason is None and requirements.must_have_parking is not None:
            if listing.parking_included is not None and listing.parking_included != requirements.must_have_parking:
                drop_reason = f"must_have_parking (extracted: {listing.parking_included})"

        # short_term_ok — keep if missing
        if drop_reason is None and requirements.short_term_ok:
            if listing.short_term_available is not None and listing.short_term_available is False:
                drop_reason = "short_term_ok (explicitly not short-term)"

        if drop_reason is None:
            listing.passed_filter = True
            listing.filter_reason = None
            passed_count += 1
        else:
            listing.passed_filter = False
            listing.filter_reason = drop_reason
            label = listing.address or listing.url[:60]
            print(f"  FILTERED [{listing.source}] {label[:60]} — {drop_reason}")
            drop_counts[drop_reason.split(" (")[0]] = drop_counts.get(drop_reason.split(" (")[0], 0) + 1

    # Log filter summary
    print(f"  Filtered: {passed_count} passed, {len(listings) - passed_count} failed (kept for HTML toggle)")
    for rule, count in sorted(drop_counts.items()):
        print(f"    {rule}: {count} failed")

    # Show distance breakdown for passed listings
    if passed_count and requirements.max_distance_km is not None:
        passed = [l for l in listings if l.passed_filter]
        with_dist = [(l.distance_km, l.neighborhood or l.address or l.url[:50]) for l in passed if l.distance_km is not None]
        no_dist = [l for l in passed if l.distance_km is None]
        if with_dist:
            with_dist.sort()
            print(f"  Distance range of passed listings: {with_dist[0][0]:.1f}–{with_dist[-1][0]:.1f} km")
        if no_dist:
            print(f"  Warning: {len(no_dist)} passed listing(s) have no distance (geocoding failed)")

    return listings
