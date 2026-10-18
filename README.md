# flipwatch

Watches **Kijiji** and **Facebook Marketplace** for new car listings. When a car is priced low enough
to flip for a profit, it sends an alert to your phone right away.

```
FLIP [kijiji] $4,500 - 2014 Honda Civic LX - as is
Watch: Honda Civic
2014 | 182,000 km
Est. profit $2,815 (56% ROI)
Resale est. $7,815 (90% of $8,683 median ask, 9 2013-2015 comps)
Location: Calgary
Signals: as is, moving, must go
https://www.kijiji.ca/v-cars-trucks/...
```

## How it works

1. Every few minutes it runs each search in your watchlist on each site, sorted newest first
   (Kijiji searches the Cars & Trucks category).
2. The first scan of a search only records what's already listed, so after that you hear about **new** listings only.
3. Year and mileage come from the site's own data when it provides them, and otherwise from the title and description
   ("2014 Civic, 182K km", "95k miles" is converted to km).
4. Each new listing is checked like this:
   - **Filters:** your year range and max km. Exclude words skip non-sales, write-offs and dealer ads
     (`wtb`, `lease takeover`, `for parts`, `salvage`, `financing available`, `omvic`, `+ hst`, …). The query
     words must also appear in the listing, since both sites pad results with loosely related listings.
   - **Placeholder prices** (`$1`, `$123`) and "please contact" listings are skipped.
   - **Flip math:**
     `cost = price × (1 + purchase_tax_pct) + fixed_costs` and `profit = resale value − cost`.
     You get an alert when profit ≥ `min_profit` and ROI (profit ÷ cost) ≥ `min_roi`.
5. **Price drops** on a listing it has already seen are checked again and alerted as `PRICE DROP`.
6. **Signal words** (`as is`, `needs safety`, `must go`, `moving`, `check engine`, `one owner`, …) are shown in
   the alert. They often mean a motivated seller or a cheap fix.

### Valuing cars

Each watch uses one of these. The example config uses `auto` for every model, which is the easiest way to start:

| Option | When to use it |
| --- | --- |
| `market_value_by_year: {2013: 7500, 2014: 8500}` | You know the model. Take values from Canadian Black Book, AutoTrader or sold comps |
| `market_value: 9000` | A narrow year range where one number is close enough |
| `market_value: auto` | Let flipwatch learn: resale = `auto_resale_pct` × the **median asking price** of comparable listings it has seen in the last 30 days, within ±1 model year. It needs `auto_min_comps` comparable listings first, so the first scans build up data before it alerts |
| none, just `max_price` | "Anything under $3k matching these words", e.g. mechanic specials |

`auto` compares against asking prices, not sold prices. Keep `auto_resale_pct` below 1 and use it to
find leads, not as an appraisal.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # only needed for Facebook

cp config.example.yaml config.yaml   # then edit your area, watchlist, values and costs
```

The example config is set up for **Calgary**: Kijiji Calgary, Facebook Marketplace within 60 km, and no purchase tax,
because Alberta charges none on private used-car sales. It watches the Civic, Accord, CR-V, Corolla, Camry and RAV4,
cheap Hondas and Toyotas of any model, and every new car listing under $6k with motivated-seller wording.
Set `fixed_costs` in `deals:` to what a flip really costs you (registration, detailing, small repairs).

Queries left empty (`""`) scan every new listing in the Cars & Trucks category (Kijiji) or Vehicles (Facebook).

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

## Watch options

```yaml
watches:
  - name: Honda Civic 2012-2016   # once you know your own numbers
    queries: ["honda civic"]
    min_year: 2012
    max_year: 2016
    max_km: 220000
    market_value_by_year: {2012: 6500, 2013: 7500, 2014: 8500, 2015: 10000, 2016: 12500}
    exclude: [type r, si, hybrid]
```

| Option | Meaning |
| --- | --- |
| `queries` | Search terms, run on each site in `sources` (default both) |
| `market_value`, `market_value_by_year` | How to value the car (see above) |
| `min_year`, `max_year`, `max_km` | Vehicle limits. Listings with an unknown year or km still pass |
| `max_price` / `min_price` | Hard price limits |
| `min_profit`, `min_roi` | Per-watch overrides of the `deals:` defaults |
| `require_all`, `require_any`, `exclude` | Word filters on title and description |
| `match_query_terms` | Require every query word in the listing (default `true`) |
| `allow_no_price` | Alert on "please contact" listings too |

For Kijiji, take `location_slug` and `location_id` from a cars search URL for your area:
`kijiji.ca/b-cars-trucks/<location_slug>/<query>/k0c174l<location_id>`. For Facebook, `location` is the
`facebook.com/marketplace/<location>/` part of the URL.

## Notes

- Before you buy, run a lien check (Alberta Personal Property Registry, at a registry agent) and a history report
  (e.g. CARFAX Canada). In Alberta, buying and reselling cars for profit as a business requires an AMVIC licence.
  Unlicensed flipping ("curbsiding") is illegal, so check AMVIC's rules before you scale up.
- Keep `poll_interval_seconds` at 120 or more. Polling harder gets you rate-limited or blocked, and on Facebook it
  puts your account at risk. Automated access is against Facebook's terms, so consider a secondary account.
- Both sites change their page markup from time to time. The parsers live in `flipwatch/sources/` and have
  fixture tests in `tests/`. If searches start returning 0 listings, those are the files to update.

## Development

```bash
pip install pytest
python -m pytest
```
