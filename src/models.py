"""Shared data model for listings coming out of any source."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class Listing:
    """A rental listing, normalized across all sources.

    `id` is the dedup key and should be stable across refetches. Format is
    ``"<source>:<native-id>"`` (e.g. ``"craigslist:7693245890"``).
    """

    id: str
    source: str
    title: str
    price: int | None
    beds: float | None
    baths: float | None
    sqft: int | None
    city: str | None
    url: str
    posted_at: datetime | None = None
    raw_address: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.posted_at is not None:
            d["posted_at"] = self.posted_at.isoformat()
        return d
