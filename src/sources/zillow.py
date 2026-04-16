"""Zillow - best-effort only. Expected to frequently return nothing.

Zillow actively fights GitHub Actions IP ranges with Perimeter X / captcha
challenges. We attempt a single call per city via the map-search JSON endpoint
and skip on any non-200 or non-JSON response. If this becomes permanently
blocked we can flip ``ENABLED_SOURCES["zillow"] = False`` in config.py.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlencode

import httpx

from ..config import CITIES, MAX_BEDS, MAX_PRICE, MIN_BEDS
from ..models import Listing
from .base import DEFAULT_TIMEOUT, parse_number, parse_price, random_headers

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.zillow.com/async-create-search-page-state"


def _payload_for(city: str) -> dict:
    # Zillow expects a searchQueryState object. "price.max" is rental price
    # when isForRent is true. We leave map bounds unset and let Zillow geocode
    # the city via regionSelection.
    return {
        "searchQueryState": {
            "pagination": {},
            "usersSearchTerm": f"{city}, CA",
            "filterState": {
                "isForSaleByAgent": {"value": False},
                "isForSaleByOwner": {"value": False},
                "isNewConstruction": {"value": False},
                "isForSaleForeclosure": {"value": False},
                "isComingSoon": {"value": False},
                "isAuction": {"value": False},
                "isPreMarketForeclosure": {"value": False},
                "isPreMarketPreForeclosure": {"value": False},
                "isMakeMeMove": {"value": False},
                "isForRent": {"value": True},
                "price": {"min": 0, "max": MAX_PRICE},
                "monthlyPayment": {"min": 0, "max": MAX_PRICE},
                "beds": {"min": int(MIN_BEDS), "max": int(MAX_BEDS)},
            },
            "isListVisible": True,
        },
        "wants": {"cat1": ["listResults"]},
        "requestId": 1,
    }


def _fetch_one(client: httpx.Client, city: str) -> list[Listing]:
    # Zillow accepts search as either POST JSON or GET with encoded query.
    qs_state = json.dumps(_payload_for(city)["searchQueryState"], separators=(",", ":"))
    params = {
        "searchQueryState": qs_state,
        "wants": json.dumps({"cat1": ["listResults"]}, separators=(",", ":")),
        "requestId": "1",
    }
    url = f"{SEARCH_URL}?{urlencode(params)}"
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        log.warning("zillow: HTTP error for %s: %s", city, e)
        return []
    if r.status_code != 200:
        log.info("zillow: %s -> HTTP %s (likely blocked)", city, r.status_code)
        return []

    try:
        data = r.json()
    except (json.JSONDecodeError, ValueError):
        log.info("zillow: non-JSON response for %s (likely captcha)", city)
        return []

    results = (
        (data.get("cat1") or {}).get("searchResults", {}).get("listResults") or []
    )
    out: list[Listing] = []
    for h in results:
        zpid = h.get("zpid") or h.get("id")
        if not zpid:
            continue
        href = h.get("detailUrl") or ""
        if href.startswith("/"):
            href = f"https://www.zillow.com{href}"

        price = parse_price(h.get("price") or h.get("unformattedPrice"))
        beds = parse_number(h.get("beds"))
        baths = parse_number(h.get("baths"))
        sqft = parse_number(h.get("area"))
        addr = h.get("address") or h.get("statusText")

        out.append(
            Listing(
                id=f"zillow:{zpid}",
                source="zillow",
                title=addr or "Zillow rental",
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
        headers=random_headers({"Accept": "application/json, text/plain, */*"}),
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

    log.info("zillow: parsed %d listing(s)", len(deduped))
    return deduped
