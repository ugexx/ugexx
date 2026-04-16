"""Format and deliver the digest to Slack via chat.postMessage."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from .config import SEND_EMPTY_DIGEST
from .models import Listing

log = logging.getLogger(__name__)


def _fmt_price(p: int | None) -> str:
    return f"${p:,}/mo" if p is not None else "price unknown"


def _fmt_beds_baths(beds: float | None, baths: float | None) -> str:
    b = f"{beds:g}bd" if beds is not None else "?bd"
    ba = f"{baths:g}ba" if baths is not None else "?ba"
    return f"{b} / {ba}"


def _fmt_sqft(sqft: int | None) -> str:
    return f"{sqft:,} sqft" if sqft else ""


def _listing_block(item: Listing) -> dict:
    details = [
        _fmt_price(item.price),
        _fmt_beds_baths(item.beds, item.baths),
    ]
    sqft = _fmt_sqft(item.sqft)
    if sqft:
        details.append(sqft)
    location = item.city or item.raw_address or ""
    if location:
        details.append(location)

    line1 = f"*<{item.url}|{item.title or 'Listing'}>*"
    line2 = "  •  ".join(details)
    line3 = f"_source: {item.source}_"

    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{line1}\n{line2}\n{line3}",
        },
    }


def _header_text(count: int) -> str:
    now = datetime.now().astimezone()
    slot = "morning" if now.hour < 12 else "evening"
    date = now.strftime("%b %-d")
    if count == 0:
        return f"No new Ventura County rentals — {date} {slot}"
    plural = "s" if count != 1 else ""
    return f"{count} new Ventura County rental{plural} — {date} {slot}"


def _build_blocks(
    listings: list[Listing],
    sources_attempted: list[str],
    sources_skipped: list[str],
) -> list[dict]:
    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": _header_text(len(listings))},
        },
    ]

    if listings:
        for item in listings:
            blocks.append({"type": "divider"})
            blocks.append(_listing_block(item))

    footer_bits = []
    if sources_attempted:
        footer_bits.append(f"searched: {', '.join(sources_attempted)}")
    if sources_skipped:
        footer_bits.append(f"skipped: {', '.join(sources_skipped)}")
    if footer_bits:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "  •  ".join(footer_bits)}],
            }
        )

    return blocks


def send_digest(
    listings: list[Listing],
    sources_attempted: list[str],
    sources_skipped: list[str],
) -> None:
    """Post a digest of new listings to the configured Slack channel.

    Requires env vars SLACK_BOT_TOKEN and SLACK_CHANNEL_ID.
    """
    if not listings and not SEND_EMPTY_DIGEST:
        log.info("no new listings and SEND_EMPTY_DIGEST=False; skipping Slack send")
        return

    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_CHANNEL_ID")
    if not token or not channel:
        log.error("SLACK_BOT_TOKEN and SLACK_CHANNEL_ID must both be set; skipping send")
        return

    client = WebClient(token=token)
    blocks = _build_blocks(listings, sources_attempted, sources_skipped)
    fallback = _header_text(len(listings))

    try:
        client.chat_postMessage(channel=channel, text=fallback, blocks=blocks)
        log.info("posted digest with %d listing(s) to %s", len(listings), channel)
    except SlackApiError as e:
        log.error("slack post failed: %s", e.response.get("error"))
