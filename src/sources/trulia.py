"""Trulia rentals - best-effort via the __NEXT_DATA__ hydration payload.

Trulia is a Zillow-owned property and is behind similar bot protection. We
fetch the search page for each city, look for the ``<script id="__NEXT_DATA__">``
JSON blob, and walk to the property list. If Trulia returns an interstitial
(e.g. Perimeter X challenge) we log and skip gracefully.
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
    slug = city.replace(" ", "_")
    return f"https://www.trulia.com/for_rent/{slug},CA/"


def _extract_props(blob: dict) -> list[dict]:
    """Trulia nests the list under a deep path that shifts across deployments.

    Rather than hardcode the path, walk the structure looking for any list of
    objects that have both "price" and "bedrooms" (or similar). Good enough for
    a scraper we expect to break periodically.
    """
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            keys = set(node.keys())
            if {"id", "url"}.issubset(keys) and any(k in keys for k in ("price", "bedrooms", "beds")):
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
        log.warning("trulia: HTTP error for %s: %s", city, e)
        return []
    if r.status_code != 200:
        log.warning("trulia: %s -> HTTP %s", city, r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        log.info("trulia: no __NEXT_DATA__ for %s (likely blocked)", city)
        return []

    try:
        blob = json.loads(tag.string)
    except json.JSONDecodeError:
        return []

    props = _extract_props(blob)
    out: list[Listing] = []
    for p in props:
        native_id = str(p.get("id") or p.get("legacyId") or "")
        if not native_id:
            continue
        href = p.get("url") or ""
        if href.startswith("/"):
            href = f"https://www.trulia.com{href}"

        price_raw = p.get("price")
        if isinstance(price_raw, dict):
            price_raw = price_raw.get("price") or price_raw.get("formattedPrice")
        price = parse_price(price_raw)

        beds = parse_number(p.get("bedrooms") or p.get("beds"))
        baths = parse_number(p.get("bathrooms") or p.get("baths"))
        sqft_raw = p.get("floorSpace") or p.get("sqft") or p.get("area")
        if isinstance(sqft_raw, dict):
            sqft_raw = sqft_raw.get("formattedDimension") or sqft_raw.get("max")
        sqft = parse_number(sqft_raw)

        loc = p.get("location") or {}
        addr = None
        city_name = city
        if isinstance(loc, dict):
            addr = loc.get("partialLocation") or loc.get("address")
            city_name = loc.get("city") or city_name

        title = addr or p.get("title") or "Trulia rental"

        out.append(
            Listing(
                id=f"trulia:{native_id}",
                source="trulia",
                title=title,
                price=price,
                beds=beds,
                baths=baths,
                sqft=int(sqft) if sqft else None,
                city=city_name,
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

    log.info("trulia: parsed %d listing(s)", len(deduped))
    return deduped
