"""Apartments.com - best-effort. Parses the listing cards off the search HTML.

Apartments.com has mild anti-bot protection that sometimes serves a blank
placeholder HTML when they detect a datacenter IP. We fall back to empty on
that case rather than adding headless browsers.
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup

from ..config import CITIES, MAX_BEDS, MAX_PRICE, MIN_BEDS
from ..models import Listing
from .base import DEFAULT_TIMEOUT, parse_number, parse_price, random_headers

log = logging.getLogger(__name__)


def _url_for(city: str) -> str:
    slug = city.lower().replace(" ", "-")
    # Apartments.com path format: /<city>-ca/min-<beds>-bedrooms-under-<price>/
    # Using the Min-Bedrooms override handles 2+ cleanly.
    return (
        f"https://www.apartments.com/{slug}-ca/"
        f"min-{int(MIN_BEDS)}-bedrooms-under-{int(MAX_PRICE)}/"
    )


def _fetch_one(client: httpx.Client, city: str) -> list[Listing]:
    url = _url_for(city)
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        log.warning("apartments_com: HTTP error for %s: %s", city, e)
        return []
    if r.status_code != 200:
        log.info("apartments_com: %s -> HTTP %s", city, r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select("article.placard, li.mortar-wrapper")
    if not cards:
        log.info("apartments_com: no cards for %s (likely blocked)", city)
        return []

    out: list[Listing] = []
    for card in cards:
        native_id = card.get("data-listingid") or card.get("data-listing-id") or card.get("id")
        link_tag = card.select_one("a.property-link, a.js-placardTitle, a[href]")
        href = link_tag.get("href") if link_tag else None
        if not href:
            continue
        if not native_id:
            native_id = href.rstrip("/").rsplit("/", 1)[-1]

        title_tag = card.select_one(".property-title, .property-name, .js-placardTitle")
        title = title_tag.get_text(strip=True) if title_tag else "Apartments.com listing"

        price_tag = card.select_one(".property-pricing, .price-range, .propertyRent")
        price = parse_price(price_tag.get_text(" ", strip=True)) if price_tag else None
        # Price may come through as a range "2,500 - 3,000"; parse_price returns
        # the first match which is the min - good enough for our cap check.

        beds_tag = card.select_one(".property-beds, .bed-range")
        baths_tag = card.select_one(".property-baths, .bath-range")
        sqft_tag = card.select_one(".property-sqft, .sqft-range")
        beds = parse_number(beds_tag.get_text(" ", strip=True)) if beds_tag else None
        baths = parse_number(baths_tag.get_text(" ", strip=True)) if baths_tag else None
        sqft = parse_number(sqft_tag.get_text(" ", strip=True)) if sqft_tag else None

        # Cap beds check since the URL only enforces min.
        if beds is not None and beds > MAX_BEDS:
            continue

        addr_tag = card.select_one(".property-address, .property-location")
        addr = addr_tag.get_text(" ", strip=True) if addr_tag else None

        out.append(
            Listing(
                id=f"apartments:{native_id}",
                source="apartments.com",
                title=title,
                price=price,
                beds=beds,
                baths=baths,
                sqft=int(sqft) if sqft else None,
                city=city,
                url=href,
                posted_at=None,
                raw_address=addr,
            )
        )
    return out


def fetch() -> list[Listing]:
    all_listings: list[Listing] = []
    with httpx.Client(
        headers=random_headers(),
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        for city in CITIES:
            all_listings.extend(_fetch_one(client, city))

    seen_ids: set[str] = set()
    deduped: list[Listing] = []
    for item in all_listings:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        deduped.append(item)

    log.info("apartments_com: parsed %d listing(s)", len(deduped))
    return deduped
