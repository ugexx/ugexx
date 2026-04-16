"""Persist + dedupe the set of listing ids we've already notified on.

State file is ``state/seen.json``: ``{listing_id: first_seen_iso}``. It gets
committed back to the repo at the end of every GitHub Actions run so future
runs can tell "new" from "already notified".
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Listing

STATE_PATH = Path(__file__).resolve().parent.parent / "state" / "seen.json"

# Prune listings older than this to keep seen.json bounded.
RETENTION_DAYS = 60


def _load() -> dict[str, str]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text() or "{}")
    except json.JSONDecodeError:
        # Corrupt state shouldn't break the run; start fresh and let the next
        # commit overwrite.
        return {}


def _save(seen: dict[str, str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")


def filter_new(listings: list[Listing]) -> list[Listing]:
    """Return only listings whose id is not in the seen store."""
    seen = _load()
    return [item for item in listings if item.id not in seen]


def commit(new_listings: list[Listing]) -> None:
    """Mark the given listings as seen and prune stale entries."""
    seen = _load()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RETENTION_DAYS)

    # Prune anything older than cutoff.
    pruned: dict[str, str] = {}
    for lid, iso in seen.items():
        try:
            ts = datetime.fromisoformat(iso)
        except ValueError:
            continue
        if ts >= cutoff:
            pruned[lid] = iso

    # Add the newcomers with the current timestamp.
    stamp = now.isoformat()
    for item in new_listings:
        pruned.setdefault(item.id, stamp)

    _save(pruned)
