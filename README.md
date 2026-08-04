# Political Data Platform — Pilot

A curated, source-linked dashboard of the Trump administration's record. v2 register: 23 metrics across 7 categories (Cost of Living, Economy & Jobs, Trade & Tariffs, Public Finances, Immigration, Health & Safety Net, Executive Power & Governance) — all keyless, all with deep stored history. Every card expands into a chart of that history — own-history, term-aligned cross-president, or vs-benchmark — with the influence note, methodology caveats, a table view and the raw series alongside.

## Structure
```
metrics.json          machine-readable register (the active metrics)
connectors/           one script per source → writes data/*.json
  validators.py       per-metric sanity bounds + max-jump (rejects bad reads)
  common.py           shared: merge-don't-overwrite series store, revision
                      detection, validated publish, freshness stamping
  static/             committed historical constants (e.g. ICE annual report
                      totals), per-row sourced — closed years never change
data/                 normalised JSON (committed; this is the "database")
build.py              reads data/*.json → site/index.html + site/d/*.json
                      (pre-computes every chart payload; no network needed)
assets/chart.js       hand-rolled SVG chart renderer, inlined at build time
                      (no libraries, no CDN, no browser storage)
run_all.py            run every connector, then build (loud-fail on any failure)
site/index.html       the static dashboard (~85 KB; history loads per-card)
site/d/<id>.json      per-metric chart payloads, fetched on first expand
.github/workflows/    daily $0 auto-update (GitHub Actions)
```

## Reliability model
- **Deep store, shallow load.** Each connector fetches history and *merges* it into `data/<id>.json` (never overwrites the whole series), so history survives even if a source drops old rows. A changed past value is flagged as a REVISION in the log and the git diff — free change-detection.
- **Sanity validation before publish.** `validators.py` holds plausible bounds + a max period-over-period jump per metric. A value outside them is treated as a bad read: the connector keeps last-good and fails.
- **Loud fail, still up.** `run_all.py` runs every connector, always rebuilds the site with last-good data, then exits non-zero if any connector failed. The workflow commits + redeploys regardless, then ends red so GitHub emails the owner. Green = clean refresh.
- **Honest freshness.** Every card shows its own data date and, via a client-side check, flags "⚠ data may be stale" when a figure is older than its source's normal cadence — so it stays honest even if the pipeline stops and the page freezes. The build timestamp is de-emphasised (it is always fresh, and therefore misleading).
- **Honest charts.** Publication gaps render as line breaks with a note (never interpolated); definition changes are labelled markers on the axis (never smoothed); bars are always zero-based; unpublished periods are labelled empty slots, never zeros. Every chart has a table view and links to the exact data payload it was drawn from.

## Run locally
```bash
pip install requests openpyxl
python run_all.py        # pulls live data + rebuilds
python test_offline.py   # 80 logic/render checks, no network needed
open site/index.html
```

## Deploy for $0
1. Push this repo to GitHub.
2. Connect the repo to **Cloudflare Pages**, output directory `site/` (free, unlimited bandwidth).
3. The included Actions workflow refreshes data daily and pushes; Pages redeploys automatically.
4. Repo secrets (Settings → Secrets and variables → Actions):
   - **None required.** All 23 connectors run keyless (FRED, Treasury Fiscal Data, CDC, CMS, FJC, Federal Register, VoteHub, and the CBP/ICE/VA/CDC-page scrapes).
   - `BLS_API_KEY` — optional; raises the BLS rate limit and widens the CPI/unemployment history window.
5. To get the loud-fail emails, make sure GitHub Actions failure notifications are on for the owner account (Settings → Notifications → Actions).

## Adding a metric (the workflow)
1. Add a row to `metrics.json` and to project doc `03 - Metric & Source Register`.
2. Add plausible bounds + `max_jump` to `connectors/validators.py`.
3. Add `connectors/<source>.py` that builds a `series` of `{date, value}` and calls `common.publish(out, series=...)`.
4. Add it to the `CONNECTORS` list in `run_all.py` and a render branch + `ORDER` entry in `build.py`.
5. Add its chart branch in `build.py`'s `payload()` — template pick (own-history / term-aligned / vs-benchmark), influence note and caveats. The offline tests fail any metric shipped without this furniture, on purpose.
That's it — the scheduler and deploy pick it up automatically.
