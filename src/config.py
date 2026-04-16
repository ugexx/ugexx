"""Search preferences for the Ventura County rental bot."""

# Ventura County cities to cover. Matched case-insensitive against the listing's
# city / address field. Keep variants for Westlake Village since Zillow/Redfin
# sometimes return just "Westlake".
CITIES: list[str] = [
    # Coastal
    "Ventura",
    "Oxnard",
    "Camarillo",
    # Conejo Valley
    "Thousand Oaks",
    "Newbury Park",
    "Westlake Village",
    "Westlake",
    # East end
    "Simi Valley",
    "Moorpark",
]

# Core filters - adjust here and re-run; no code changes required elsewhere.
MIN_BEDS: float = 2
MAX_BEDS: float = 3
MIN_BATHS: float = 1.5
MAX_PRICE: int = 2800

# Used by sources that support a posted-since parameter. Cron runs every ~12h;
# 36h of overlap guards against delayed listings and dedup handles the rest.
LOOKBACK_HOURS: int = 36

# Per-source kill switches. Flip to False to quickly disable a flaky scraper
# without editing main.py.
ENABLED_SOURCES: dict[str, bool] = {
    "craigslist": True,
    "redfin": True,
    "trulia": True,
    "realtor": True,
    "zillow": True,
    "apartments_com": True,
}

# If True, send a heartbeat Slack message even when no new listings matched.
# Useful while verifying the cron is firing; silence later if it gets noisy.
SEND_EMPTY_DIGEST: bool = True
