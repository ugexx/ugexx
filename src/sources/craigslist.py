"""Craigslist Ventura County - RSS-based fetch. The most reliable source.

Craigslist exposes a per-search RSS feed that embeds the key facts we need.
Beds/baths aren't in the feed title, so we parse them out of the description
where available.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urlencode

import feedparser

from ..config import LOOKBACK_HOURS, MAX_BEDS, MAX_PRICE, MIN_BATHS, MIN_BEDS
from ..models import Listing
from .base import parse_number, parse_price, random_headers

log = logging.getLogger(__name__)

BASE = "https://ventura.craigslist.org/search/apa"

_BEDS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*BR", re.IGNORECASE)
_BATHS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*Ba", re.IGNORECASE)
_SQFT_RE = re.compile(r"(\d[\d,]*)\s*ft\u00b2|(\d[\d,]*)\s*ft2|(\d[\d,]*)\s*sqft", re.IGNORECASE)


def _build_url() -> str:
    params = {
        "format": "rss",
        "min_bedrooms": int(MIN_BEDS),
        "max_bedrooms": int(MAX_BEDS),
        "max_price": int(MAX_PRICE),
        "min_bathrooms": MIN_BATHS,
        "postedToday": 0,  # we use LOOKBACK_HOURS instead
        "postal": 93001,  # Ventura zip - anchors the "nearby" ordering
        "search_distance": 30,
    }
    return f"{BASE}?{urlencode(params)}"


def _extract_price(title: str, summary: str) -> int | None:
    # Craigslist titles look like "$2,450 / 2br - ...". Try title first.
    for s in (title, summary):
        p = parse_price(s)
        if p:
            return p
    return None


def _extract_sqft(text: str) -> int | None:
    m = _SQFT_RE.search(text)
    if not m:
        return None
    for g in m.groups():
        if g:
            try:
                return int(g.replace(",", ""))
            except ValueError:
                return None
    return None


def _extract_city(summary: str) -> str | None:
    # Craigslist surfaces a parenthesized neighborhood in the title we don't
    # have here; the summary sometimes contains an address. Leave None and
    # rely on the coarse filter falling back to the raw summary.
    return None


def fetch() -> list[Listing]:
    url = _build_url()
    log.info("craigslist: fetching %s", url)

    # feedparser does its own HTTP; pass a realistic UA via request_headers.
    feed = feedparser.parse(url, request_headers=random_headers())
    if feed.bozo:
        log.warning("craigslist: feed parse error: %s", feed.bozo_exception)

    cutoff_ts = datetime.now().timestamp() - LOOKBACK_HOURS * 3600
    listings: list[Listing] = []

    for entry in feed.entries:
        title = entry.get("title", "") or ""
        summary = entry.get("summary", "") or entry.get("description", "") or ""
        link = entry.get("link") or ""

        # Posted time. Craigslist RSS uses dc:date; feedparser maps to updated_parsed.
        posted_at = None
        ts_struct = entry.get("updated_parsed") or entry.get("published_parsed")
        if ts_struct:
            try:
                posted_at = datetime(*ts_struct[:6])
                if posted_at.timestamp() < cutoff_ts:
                    continue
            except (TypeError, ValueError):
                posted_at = None

        # Derive a stable id from the URL path.
        native_id = link.rstrip("/").rsplit("/", 1)[-1].split(".")[0] or link
        lid = f"craigslist:{native_id}"

        beds_m = _BEDS_RE.search(title + " " + summary)
        baths_m = _BATHS_RE.search(title + " " + summary)
        beds = parse_number(beds_m.group(1)) if beds_m else None
        baths = parse_number(baths_m.group(1)) if baths_m else None
        sqft = _extract_sqft(title + " " + summary)
        price = _extract_price(title, summary)

        listings.append(
            Listing(
                id=lid,
                source="craigslist",
                title=title,
                price=price,
                beds=beds,
                baths=baths,
                sqft=sqft,
                city=_extract_city(summary),
                url=link,
                posted_at=posted_at,
                raw_address=summary[:200] if summary else None,
            )
        )

    log.info("craigslist: parsed %d listing(s)", len(listings))
    return listings
