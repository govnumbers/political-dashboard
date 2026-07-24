#!/usr/bin/env python3
"""Inflation (CPI-U, year over year) — Bureau of Labor Statistics API.
Series CUUR0000SA0 = CPI-U, all items, US city average, not seasonally adjusted
(the NSA index used for headline year-over-year inflation).
Stores a deep monthly YoY series; merges each run. Optional BLS_API_KEY widens
the window and raises rate limits."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES = "CUUR0000SA0"


def main():
    this_year = datetime.date.today().year
    key = os.environ.get("BLS_API_KEY")
    start = 2016 if key else this_year - 9   # keyless: <=10-yr span
    payload = {"seriesid": [SERIES], "startyear": str(start), "endyear": str(this_year)}
    if key:
        payload["registrationkey"] = key
    r = requests.post(API, json=payload, timeout=30)
    r.raise_for_status()
    rows = r.json()["Results"]["series"][0]["data"]
    idx = {(int(d["year"]), int(d["period"][1:])): float(d["value"])
           for d in rows if d["period"].startswith("M")}

    # YoY % for every month whose year-ago index is present
    series = []
    for (y, m) in sorted(idx):
        ya = idx.get((y - 1, m))
        if ya:
            series.append({"date": f"{y}-{m:02d}", "value": round((idx[(y, m)] - ya) / ya * 100, 1)})

    latest = series[-1]
    out = {
        "id": "inflation", "name": "Inflation (CPI-U, year over year)",
        "category": "Economy", "value": latest["value"], "unit": "%", "as_of": latest["date"],
        "direction": "up_is_bad",
        "target": {"label": "Federal Reserve target", "value": 2.0},
        "source": {"name": "Bureau of Labor Statistics", "url": "https://www.bls.gov/cpi/"},
        "cadence": "Monthly",
        "note": "Consumer Price Index for All Urban Consumers, all items, change over the prior 12 months.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
