"""Shared helpers for source scrapers (HTTP client, header rotation, parsing)."""

from __future__ import annotations

import random
import re

import httpx

# A short list of real-looking desktop user-agents. Rotated per-request for
# sources that may rate-limit. Nothing fancy - GitHub Actions IPs will still be
# rate-limited by aggressive anti-bot services like Zillow/Apartments.com no
# matter what UA we send.
USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.3 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
]

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def random_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if extra:
        headers.update(extra)
    return headers


def make_client(extra_headers: dict[str, str] | None = None) -> httpx.Client:
    """Return an httpx.Client with sensible defaults + rotated headers."""
    return httpx.Client(
        headers=random_headers(extra_headers),
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        http2=False,
    )


_PRICE_RE = re.compile(r"\$?\s*([\d,]+)")


def parse_price(value) -> int | None:
    """Best-effort parse of a price into an int of dollars."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value)
    m = _PRICE_RE.search(s)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_number(value) -> float | None:
    """Best-effort parse of a count/measure (beds, baths, sqft) into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"(\d+(?:\.\d+)?)", str(value))
    return float(m.group(1)) if m else None
