#!/usr/bin/env python3
"""Gas price (US regular retail) — EIA Open Data API v2.
Needs a free EIA_API_KEY (https://www.eia.gov/opendata/register.php).
Series: weekly US regular all-formulations retail price, $/gal."""
import json, os, datetime, requests

API = "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
SERIES = "EMM_EPMR_PTE_NUS_DPG"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "gas_price.json")

def main():
    key = os.environ["EIA_API_KEY"]  # required
    params = {
        "api_key": key, "frequency": "weekly", "data[0]": "value",
        "facets[series][]": SERIES,
        "sort[0][column]": "period", "sort[0][direction]": "desc",
        "length": 120,
    }
    r = requests.get(API, params=params, timeout=30); r.raise_for_status()
    rows = r.json()["response"]["data"]  # newest first
    latest = rows[0]
    # baseline: first observation on/after inauguration week
    base = min((x for x in rows if x["period"] >= "2025-01-13"), key=lambda x: x["period"])
    out = {
        "id": "gas_price", "name": "Gas price (regular)", "category": "Economy",
        "value": round(float(latest["value"]), 3), "unit": "$/gal", "as_of": latest["period"],
        "direction": "up_is_bad",
        "baseline": {"label": "At inauguration (Jan 2025)", "value": round(float(base["value"]), 3)},
        "source": {"name": "U.S. Energy Information Administration",
                   "url": "https://www.eia.gov/petroleum/gasdiesel/"},
        "cadence": "Weekly", "note": "US average regular gasoline, per gallon.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"gas_price: ${out['value']} ({out['as_of']})")

if __name__ == "__main__":
    main()
