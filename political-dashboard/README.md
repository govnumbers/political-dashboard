# Political Data Platform — Pilot

A curated, source-linked dashboard of the Trump administration's record. Pilot = 9 of 15 planned metrics (4 economic, 2 public-finance, 1 executive-power, 2 immigration).

## Structure
```
metrics.json          machine-readable register (the active metrics)
connectors/           one script per source → writes data/*.json
  validators.py       per-metric sanity bounds + max-jump (rejects bad reads)
  common.py           shared: merge-don't-overwrite series store, revision
                      detection, validated publish, freshness stamping
data/                 normalised JSON (committed; this is the "database")
build.py              reads data/*.json → site/index.html (no network needed)
run_all.py            run every connector, then build (loud-fail on any failure)
site/index.html       the static dashboard
.github/workflows/    daily $0 auto-update (GitHub Actions)
```

## Reliability model
- **Deep store, shallow load.** Each connector fetches history and *merges* it into `data/<id>.json` (never overwrites the whole series), so history survives even if a source drops old rows. A changed past value is flagged as a REVISION in the log and the git diff — free change-detection.
- **Sanity validation before publish.** `validators.py` holds plausible bounds + a max period-over-period jump per metric. A value outside them is treated as a bad read: the connector keeps last-good and fails.
- **Loud fail, still up.** `run_all.py` runs every connector, always rebuilds the site with last-good data, then exits non-zero if any connector failed. The workflow commits + redeploys regardless, then ends red so GitHub emails the owner. Green = clean refresh.
- **Honest freshness.** Every card shows its own data date and, via a client-side check, flags "⚠ data may be stale" when a figure is older than its source's normal cadence — so it stays honest even if the pipeline stops and the page freezes. The build timestamp is de-emphasised (it is always fresh, and therefore misleading).

## Run locally
```bash
pip install requests openpyxl
python run_all.py        # pulls live data + rebuilds
open site/index.html
```

## Deploy for $0
1. Push this repo to GitHub.
2. Connect the repo to **Cloudflare Pages**, output directory `site/` (free, unlimited bandwidth).
3. The included Actions workflow refreshes data daily and pushes; Pages redeploys automatically.
4. Repo secrets (Settings → Secrets and variables → Actions):
   - `BLS_API_KEY` — optional; raises the BLS rate limit and widens the history window.
   - `EIA_API_KEY` — **required to make the gas-price metric live** (free: https://www.eia.gov/opendata/register.php). Absent → the connector skips cleanly and keeps last-good.
   - `CENSUS_API_KEY` — **required to make the trade-deficit metric live** (free: https://api.census.gov/data/key_signup.html). Absent → skips cleanly.
5. To get the loud-fail emails, make sure GitHub Actions failure notifications are on for the owner account (Settings → Notifications → Actions).

## Adding a metric (the workflow)
1. Add a row to `metrics.json` and to project doc `03 - Metric & Source Register`.
2. Add plausible bounds + `max_jump` to `connectors/validators.py`.
3. Add `connectors/<source>.py` that builds a `series` of `{date, value}` and calls `common.publish(out, series=...)`.
4. Add it to the `CONNECTORS` list in `run_all.py` and a render branch + `ORDER` entry in `build.py`.
That's it — the scheduler and deploy pick it up automatically.
