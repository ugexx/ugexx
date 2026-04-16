"""Orchestrator: fetch all enabled sources, filter, dedupe, notify."""

from __future__ import annotations

import logging
import sys

from . import dedupe, filter as filter_mod, slack
from .config import ENABLED_SOURCES
from .models import Listing
from .sources import apartments_com, craigslist, realtor, redfin, trulia, zillow

log = logging.getLogger("rental-search")

# Ordered so the most reliable sources run first - if something flakes later in
# the pipeline the earlier ones still produce value.
SOURCES = [
    ("craigslist", craigslist.fetch),
    ("redfin", redfin.fetch),
    ("trulia", trulia.fetch),
    ("realtor", realtor.fetch),
    ("zillow", zillow.fetch),
    ("apartments_com", apartments_com.fetch),
]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def run() -> int:
    _configure_logging()

    all_listings: list[Listing] = []
    attempted: list[str] = []
    skipped: list[str] = []

    for name, fetch in SOURCES:
        if not ENABLED_SOURCES.get(name, True):
            log.info("%s: disabled in config, skipping", name)
            skipped.append(name)
            continue
        attempted.append(name)
        try:
            got = fetch()
            log.info("%s: returned %d listings", name, len(got))
            all_listings.extend(got)
        except Exception as e:  # noqa: BLE001 - fail-soft per source
            log.warning("%s: fetch failed: %s", name, e)
            skipped.append(name)

    log.info("aggregated %d raw listings across sources", len(all_listings))

    kept = [item for item in all_listings if filter_mod.keep(item)]
    log.info("%d listings passed filters", len(kept))

    new = dedupe.filter_new(kept)
    log.info("%d listings are new (not in seen.json)", len(new))

    slack.send_digest(new, sources_attempted=attempted, sources_skipped=skipped)

    dedupe.commit(new)
    log.info("done; seen.json updated")
    return 0


if __name__ == "__main__":
    sys.exit(run())
