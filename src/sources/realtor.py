"""Realtor.com rentals - best-effort via __NEXT_DATA__ hydration.

Same shape as trulia.py: fetch a city search page, pull the ``__NEXT_DATA__``
JSON, walk to the property list.
"""

from __future__ import annotations

import json
import logging

import httpx
from bs4 import BeautifulSoup

from ..config import CITIES
from ..models import Listing
from .base import DEFAULT_TIMEOUT, parse_number, parse_price, random_headers

log = logging.getLogger(__name__)


def _url_for(city: str) -> str:
    slug = city.replace(" ", "-")
    return f"https://www.realtor.com/apartments/{slug}_CA"


def _walk_properties(blob: dict) -> list[dict]:
    """Realtor.com nests under apolloState with keys like ``Property:M1234567``.

    We look for any dict that has a property-shaped signature (list_price +
    description with beds).
    """
    found: list[dict] = []

    def is_prop(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        desc = d.get("description")
        if isinstance(desc, dict) and ("beds" in desc or "baths" in desc):
            return True
        return False

    def walk(node):
        if isinstance(node, dict):
            if is_prop(node):
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(blob)
    return found


def _fetch_one(client: httpx.Client, city: str) -> list[Listing]:
    url = _url_for(city)
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        log.warning("realtor: HTTP error for %s: %s", city, e)
        return []
    if r.status_code != 200:
        log.warning("realtor: %s -> HTTP %s", city, r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        log.info("realtor: no __NEXT_DATA__ for %s (likely blocked)", city)
        return []

    try:
        blob = json.loads(tag.string)
    except json.JSONDecodeError:
        return []

    props = _walk_properties(blob)
    out: list[Listing] = []
    for p in props:
        native_id = str(p.get("property_id") or p.get("listing_id") or p.get("id") or "")
        if not native_id:
            continue

        href = p.get("href")
        if not href:
            continue
        if href.startswith("/"):
            href = f"https://www.realtor.com{href}"

        list_price = p.get("list_price")
        price = parse_price(list_price if not isinstance(list_price, dict) else list_price.get("min"))

        desc = p.get("description") or {}
        beds = parse_number(desc.get("beds"))
        baths = parse_number(desc.get("baths") or desc.get("baths_consolidated"))
        sqft = parse_number(desc.get("sqft"))

        loc = p.get("location") or {}
        address = loc.get("address") if isinstance(loc, dict) else None
        addr_line = None
        city_name = city
        if isinstance(address, dict):
            addr_line = address.get("line")
            city_name = address.get("city") or city_name

        title = addr_line or "Realtor.com rental"

        out.append(
            Listing(
                id=f"realtor:{native_id}",
                source="realtor",
                title=title,
                price=price,
                beds=beds,
                baths=baths,
                sqft=int(sqft) if sqft else None,
                city=city_name,
                url=href,
                posted_at=None,
                raw_address=addr_line,
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

    log.info("realtor: parsed %d listing(s)", len(deduped))
    return deduped
