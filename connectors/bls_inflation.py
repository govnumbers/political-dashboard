#!/usr/bin/env python3
"""Inflation (CPI-U, year over year) — Bureau of Labor Statistics API.
Series CUUR0000SA0 = CPI-U, all items, US city average, not seasonally adjusted
(the NSA index is the one used for headline year-over-year inflation).
Optionally set BLS_API_KEY env var for higher rate limits."""
import json, os, datetime, requests

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES = "CUUR0000SA0"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "inflation.json")

def main():
    this_year = datetime.date.today().year
    payload = {"seriesid": [SERIES], "startyear": str(this_year - 1), "endyear": str(this_year)}
    key = os.environ.get("BLS_API_KEY")
    if key:
        payload["registrationkey"] = key
    r = requests.post(API, json=payload, timeout=30)
    r.raise_for_status()
    rows = r.json()["Results"]["series"][0]["data"]  # newest first
    # build {(year, month): value}
    idx = {(int(d["year"]), int(d["period"][1:])): float(d["value"])
           for d in rows if d["period"].startswith("M")}
    latest = max(idx)                      # (year, month)
    year_ago = (latest[0] - 1, latest[1])
    yoy = round((idx[latest] - idx[year_ago]) / idx[year_ago] * 100, 1)
    as_of = f"{latest[0]}-{latest[1]:02d}"
    out = {
        "id": "inflation", "name": "Inflation (CPI-U, year over year)",
        "category": "Economy", "value": yoy, "unit": "%", "as_of": as_of,
        "direction": "up_is_bad",
        "target": {"label": "Federal Reserve target", "value": 2.0},
        "source": {"name": "Bureau of Labor Statistics", "url": "https://www.bls.gov/cpi/"},
        "cadence": "Monthly",
        "note": "Consumer Price Index for All Urban Consumers, all items, change over the prior 12 months.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"inflation: {yoy}% (YoY, {as_of})")

if __name__ == "__main__":
    main()
