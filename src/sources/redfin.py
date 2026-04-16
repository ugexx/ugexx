"""Redfin rentals via their public-facing ``rentals/api/search`` endpoint.

Redfin exposes a JSON search endpoint that powers their own rentals site. We
query one city at a time (simpler than coaxing the multi-region search to work
against a single request). Each response is a flat list of listings with
normalized beds/baths/price fields, so mapping to our `Listing` is easy.
"""

from __future__ import annotations

import json
import logging

import httpx

from ..config import CITIES, MAX_PRICE, MIN_BEDS
from ..models import Listing
from .base import DEFAULT_TIMEOUT, parse_number, parse_price, random_headers

log = logging.getLogger(__name__)

# Redfin's rentals search endpoint. Returns JSON.
SEARCH_URL = "https://www.redfin.com/stingray/api/v1/search/rentals"


def _query_for(city: str) -> dict:
    # "al=1" means "for rent" search; market-agnostic params keep this
    # portable across CA cities.
    return {
        "al": 1,
        "market": "socal",
        "min_beds": int(MIN_BEDS),
        "max_price": int(MAX_PRICE),
        "num_homes": 50,
        "ord": "days-on-redfin-asc",
        "page_number": 1,
        "region_id": "",
        "region_type": 6,
        "sf": "1,2,3,5,6,7",
        "status": 9,
        "uipt": "1,2,3,4,5,6,7,8",
        "v": 8,
        "location": f"{city}, CA",
    }


def _fetch_one(client: httpx.Client, city: str) -> list[Listing]:
    try:
        r = client.get(SEARCH_URL, params=_query_for(city))
    except httpx.HTTPError as e:
        log.warning("redfin: HTTP error for %s: %s", city, e)
        return []

    if r.status_code != 200:
        log.warning("redfin: %s -> HTTP %s", city, r.status_code)
        return []

    # Redfin sometimes prefixes JSON with anti-hijacking "{}&&" garbage.
    text = r.text
    if text.startswith("{}&&"):
        text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("redfin: non-JSON response for %s", city)
        return []

    homes = (data.get("payload") or {}).get("homes") or []
    out: list[Listing] = []
    for h in homes:
        price = parse_price(
            (h.get("price") or {}).get("value")
            or (h.get("rentPriceRange") or {}).get("min", {}).get("value")
        )
        beds = parse_number(h.get("beds"))
        baths = parse_number(h.get("baths"))
        sqft = parse_number((h.get("sqFt") or {}).get("value"))
        addr = h.get("streetLine", {}).get("value") if isinstance(h.get("streetLine"), dict) else None
        city_name = h.get("city")
        link_path = h.get("url")
        url = f"https://www.redfin.com{link_path}" if link_path else ""
        native_id = h.get("mlsId", {}).get("value") if isinstance(h.get("mlsId"), dict) else h.get("propertyId")
        if not native_id:
            native_id = url.rstrip("/").rsplit("/", 1)[-1]
        title = f"{addr}, {city_name}" if addr and city_name else (addr or city_name or "Redfin rental")

        out.append(
            Listing(
                id=f"redfin:{native_id}",
                source="redfin",
                title=title,
                price=price,
                beds=beds,
                baths=baths,
                sqft=int(sqft) if sqft else None,
                city=city_name,
                url=url,
                posted_at=None,
                raw_address=addr,
            )
        )
    return out


def fetch() -> list[Listing]:
    all_listings: list[Listing] = []
    with httpx.Client(
        headers=random_headers({"Accept": "application/json, text/plain, */*"}),
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
    ) as client:
        for city in CITIES:
            all_listings.extend(_fetch_one(client, city))

    # dedupe within source - the same property might show for neighboring city queries
    seen_ids: set[str] = set()
    deduped: list[Listing] = []
    for item in all_listings:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        deduped.append(item)

    log.info("redfin: parsed %d listing(s) across %d cities", len(deduped), len(CITIES))
    return deduped
