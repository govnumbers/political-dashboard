#!/usr/bin/env python3
"""Gas price (US regular retail) — EIA Open Data API v2.
Needs a free EIA_API_KEY (https://www.eia.gov/opendata/register.php).
Series: weekly US regular all-formulations retail price, $/gal.

If the key is not set the connector SKIPS cleanly (keeps last-good, exits 0) so
the board stays green until you opt in — it goes live the moment EIA_API_KEY is
added as a repo secret."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
SERIES = "EMM_EPMR_PTE_NUS_DPG"
TERM_START = "2025-01-13"   # first weekly obs on/after inauguration week


def main():
    key = os.environ.get("EIA_API_KEY")
    if not key:
        print("  – gas_price: EIA_API_KEY not set; skipping (keeping last-good). "
              "Add the secret to make this metric live.")
        return
    params = {
        "api_key": key, "frequency": "weekly", "data[0]": "value",
        "facets[series][]": SERIES,
        "sort[0][column]": "period", "sort[0][direction]": "desc",
        "length": 700,   # ~13 years weekly (store deep)
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()["response"]["data"]  # newest first

    series = [{"date": x["period"], "value": round(float(x["value"]), 3)}
              for x in rows if x.get("value") is not None]
    series.sort(key=lambda p: p["date"])

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] >= TERM_START), series[0]["value"])
    out = {
        "id": "gas_price", "name": "Gas price (regular)", "category": "Economy",
        "value": latest["value"], "unit": "$/gal", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": {"label": "At inauguration (Jan 2025)", "value": base},
        "source": {"name": "U.S. Energy Information Administration",
                   "url": "https://www.eia.gov/petroleum/gasdiesel/"},
        "cadence": "Weekly", "note": "US average regular gasoline, per gallon.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
