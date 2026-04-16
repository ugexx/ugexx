"""Filter listings down to the user's criteria (beds, baths, price, city)."""

from __future__ import annotations

from .config import CITIES, MAX_BEDS, MAX_PRICE, MIN_BATHS, MIN_BEDS
from .models import Listing


def _city_matches(city: str | None, address: str | None) -> bool:
    """True if either the city or raw address string contains one of our
    target cities (case-insensitive substring match).

    If both are unknown we conservatively return True - rather than drop a
    listing just because the source didn't expose a structured city we let it
    through; the dedup + Slack digest make it cheap to eyeball false positives.
    """
    haystack_parts = [p for p in (city, address) if p]
    if not haystack_parts:
        return True
    haystack = " ".join(haystack_parts).lower()
    return any(c.lower() in haystack for c in CITIES)


def keep(listing: Listing) -> bool:
    """Return True if the listing passes all user-configured filters."""
    if listing.price is None or listing.price > MAX_PRICE:
        return False
    if listing.beds is not None and not (MIN_BEDS <= listing.beds <= MAX_BEDS):
        return False
    if listing.baths is not None and listing.baths < MIN_BATHS:
        return False
    if not _city_matches(listing.city, listing.raw_address):
        return False
    return True
