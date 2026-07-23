# Political Data Platform — Pilot

A curated, source-linked dashboard of the Trump administration's record. Pilot = 3 of 15 planned metrics.

## Structure
```
metrics.json          machine-readable register (the 3 active metrics)
connectors/           one script per source → writes data/*.json
data/                 normalised JSON (committed; this is the "database")
build.py              reads data/*.json → site/index.html (no network needed)
run_all.py            run every connector, then build
site/index.html       the static dashboard
.github/workflows/    daily $0 auto-update (GitHub Actions)
```

## Run locally
```bash
pip install requests
python run_all.py        # pulls live data + rebuilds
open site/index.html
```

## Deploy for $0
1. Push this repo to GitHub.
2. Connect the repo to **Cloudflare Pages**, output directory `site/` (free, unlimited bandwidth).
3. The included Actions workflow refreshes data daily and pushes; Pages redeploys automatically.
4. Optional: a `BLS_API_KEY` repo secret raises the BLS rate limit (not required).

## Adding a metric (the workflow)
1. Add a row to `metrics.json` and to project doc `03 - Metric & Source Register`.
2. Add `connectors/<source>.py` that writes `data/<id>.json` in the same shape as the others.
3. Add a render branch in `build.py`.
That's it — the scheduler and deploy pick it up automatically.
