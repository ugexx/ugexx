# Ventura County Rental Search

Twice a day, GitHub Actions fetches fresh rental listings from Craigslist,
Redfin, Trulia, Realtor.com, Zillow, and Apartments.com; filters them down to
your saved criteria; skips anything you've already been notified about; and
posts a Slack digest.

Inspired by a Reddit post about using Claude to land a London flat in 5 days.
Adapted for Ventura County and Slack delivery.

## What it searches

- **Cities**: Ventura, Oxnard, Camarillo, Thousand Oaks, Newbury Park, Westlake
  Village, Simi Valley, Moorpark
- **Filter**: 2-3 bedrooms, ≥ 1.5 baths, ≤ $2,800/mo
- **Schedule**: 8am and 6pm Pacific, daily

All of these are controlled by `src/config.py`. Edit, push, done.

## Reality check

$2,800 for a 2-3bd in Ventura County is aggressive. Expect **0-3 hits per run
on a typical week**. Craigslist and Redfin do the heavy lifting. Zillow and
Apartments.com actively block GitHub Actions datacenter IPs - they'll
frequently return nothing, which is logged and accepted. Flip them off in
`ENABLED_SOURCES` if the noise bothers you.

## One-time setup

### 1. Create a Slack app for the bot

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Name it something like "Rental Bot" and pick your workspace
3. Under **OAuth & Permissions**, add the `chat:write` bot scope
4. Click **Install to Workspace** and approve
5. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
6. Invite the bot into the channel where you want digests:
   `/invite @Rental Bot` in that channel

### 2. Grab the channel ID

Right-click the channel in Slack → **View channel details** → scroll to the
bottom. Or open the channel in the web app: the URL ends in the channel ID
(`C0ABCDEF123`). For a DM to yourself, it starts with `D...` and you can find
it in the profile pane.

### 3. Add the secrets to GitHub

Repo → **Settings** → **Secrets and variables** → **Actions** → **New
repository secret**:

- `SLACK_BOT_TOKEN` - the `xoxb-...` token
- `SLACK_CHANNEL_ID` - e.g. `C0ABCDEF123`

### 4. Trigger a dry run

Actions tab → **Rental Search** → **Run workflow**. First run should post a
digest (or "No new rentals" message) within ~1 minute.

## Changing your criteria

Everything lives in [`src/config.py`](src/config.py):

- `CITIES` - add/remove cities (matched case-insensitive against each listing)
- `MIN_BEDS` / `MAX_BEDS` / `MIN_BATHS` / `MAX_PRICE` - the core filter
- `ENABLED_SOURCES` - kill switches per source
- `SEND_EMPTY_DIGEST` - set `False` once you're tired of the heartbeat messages

Commit, push, and the next scheduled run picks it up.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export SLACK_BOT_TOKEN=xoxb-...
export SLACK_CHANNEL_ID=C0ABCDEF123
python -m src.main
```

Or per-source spot check:

```bash
python -c "from src.sources import craigslist; import json; \
  print(json.dumps([l.to_dict() for l in craigslist.fetch()[:3]], default=str, indent=2))"
```

## How dedup works

After each run the script appends every newly-notified listing id to
`state/seen.json` and the workflow commits that file back to the repo. The
next run reads it back and filters those ids out, so you won't see the same
listing twice. Entries older than 60 days are pruned automatically.

If you ever want to "reset" and be notified about everything again, just
`echo '{}' > state/seen.json && git commit -m 'reset seen'`.

## Repo layout

```
src/
  main.py               # orchestrator
  config.py             # cities, filters, source toggles
  models.py             # Listing dataclass
  filter.py             # price / beds / baths / city match
  dedupe.py             # seen.json read/write + pruning
  slack.py              # Block Kit digest delivery
  sources/
    craigslist.py       # RSS - most reliable
    redfin.py           # stingray/api/v1/search/rentals JSON
    trulia.py           # __NEXT_DATA__ hydration
    realtor.py          # __NEXT_DATA__ hydration
    zillow.py           # async-create-search-page-state (best-effort)
    apartments_com.py   # HTML card scrape (best-effort)
state/seen.json
.github/workflows/rental-search.yml
```

## Troubleshooting

- **No Slack message arrived** - check the Actions run log. Most likely the
  bot isn't a member of the channel (`/invite @Rental Bot`) or the secrets
  aren't set.
- **Same run fires two Slack messages** - the workflow's `concurrency:` block
  should prevent this; if it does happen, there's a queued retry in Actions.
- **A source returns 0 every time** - that site's bot protection won the
  arms race. Disable it in `ENABLED_SOURCES` and live with the rest.
- **Want to add Facebook Marketplace** - requires auth + is extremely fragile.
  Not planned for v1.
