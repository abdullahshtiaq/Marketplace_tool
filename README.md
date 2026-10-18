# flipwatch

Watches **Kijiji** and **Facebook Marketplace** for new card listings (trading cards, graphics cards,
anything else you put on the watchlist). When a new listing is priced low enough to flip for a profit,
it sends an alert to your phone right away.

```
FLIP [kijiji] $40 - Old Pokémon card binder - childhood collection
Watch: Pokemon bulk / collections
Location: Toronto
Signals: binder, childhood, moving, must go
https://www.kijiji.ca/v-hobbies-craft/...
```

## How it works

1. Every few minutes it runs each search in your watchlist on each site, sorted newest first.
2. The first scan of a search only records what's already listed, so after that you hear about **new** listings only.
3. Each new listing is checked like this:
   - **Exclude words** (`wtb`, `proxy`, `fake`, `for parts`, …) and a check that the query words actually appear in the listing, since both sites pad results with loosely related listings.
   - **Placeholder prices** (`$1`, `$0`) and "please contact" listings are skipped.
   - **Flip math:** `profit = market_value × (1 − selling_fee_pct) − fixed_costs − price`. You get an alert when profit ≥ `min_profit` and ROI ≥ `min_roi`.
   - Watches without a `market_value` alert on anything under `max_price` (good for "cheap bulk lots").
4. **Price drops** on a listing it has already seen are checked again and alerted as `PRICE DROP`.
5. **Signal words** (`binder`, `collection`, `moving`, `must go`, `sealed`, `psa`, …) are shown in the alert. They often mean the seller wants a quick sale.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # only needed for Facebook

cp config.example.yaml config.yaml   # then edit your area, watchlist and values
```

### Phone notifications (ntfy, free, no account)

1. Install the **ntfy** app (iOS/Android) and subscribe to a topic name nobody will guess, e.g. `flips-8f3k2q`.
2. `export NTFY_TOPIC=flips-8f3k2q` (or put it directly in `config.yaml`).
3. `python -m flipwatch test-notify`

Discord webhooks and Telegram bots are supported too (see `notify:` in the config).

### Facebook login (one time)

Marketplace search only works when you're logged in, so flipwatch uses its own saved browser profile:

```bash
python -m flipwatch fb-login     # a browser opens; log in, then press Enter in the terminal
```

The session is saved in `.fb-profile/`. If Facebook logs you out later, the log shows
`not logged in to Facebook`. Run `fb-login` again to fix it.

## Running

```bash
python -m flipwatch run                    # watch forever
python -m flipwatch run --once -v          # one scan, logs why each listing was skipped
python -m flipwatch run --source kijiji    # only one site
```

Run it on a machine that stays on at home, like a desktop, a Raspberry Pi or an old laptop (`tmux`, `systemd`
or Task Scheduler). A residential IP matters: both sites often block cloud/datacenter IPs, and Facebook
challenges logins from new locations.

## Tuning the watchlist

```yaml
watches:
  - name: Charizard
    queries: ["charizard"]
    market_value: 120         # what it actually sells for (eBay *sold* listings)
    min_profit: 40            # optional per-watch overrides of the deals: defaults
    exclude: [plush, figure, sticker]
  - name: Pokemon bulk
    queries: ["pokemon cards", "pokemon binder"]
    max_price: 60
    require_any: [lot, binder, collection, bulk]
```

| Option | Meaning |
| --- | --- |
| `queries` | Search terms, run on each site in `sources` (default both) |
| `market_value` | Realistic resale value; turns on the profit/ROI check |
| `max_price` / `min_price` | Hard price limits |
| `min_profit`, `min_roi` | Per-watch overrides of the `deals:` defaults |
| `require_all`, `require_any`, `exclude` | Word filters on title and description |
| `match_query_terms` | Require every query word in the listing (default `true`) |
| `allow_no_price` | Alert on "please contact" listings too |

Keep `market_value` up to date. It's the number that decides what counts as a flip.

For Kijiji, take `location_slug` and `location_id` from a search URL for your area:
`kijiji.ca/b-<location_slug>/<query>/k0l<location_id>`. For Facebook, `location` is the
`facebook.com/marketplace/<location>/` part of the URL.

## Notes

- Keep `poll_interval_seconds` at 120 or more. Polling harder gets you rate-limited or blocked, and on Facebook it puts your account at risk. Automated access is against Facebook's terms, so consider a secondary account.
- Both sites change their page markup from time to time. The parsers live in `flipwatch/sources/` and have fixture tests in `tests/`. If searches start returning 0 listings, those are the files to update.

## Development

```bash
pip install pytest
python -m pytest
```
