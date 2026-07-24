#!/usr/bin/env python3
"""Unemployment rate (U-3) — Bureau of Labor Statistics API.
Series LNS14000000 = civilian unemployment rate, seasonally adjusted.
Stores a deep monthly series; merges each run. Baseline = inauguration month."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES = "LNS14000000"
BASE_KEY = "2025-01"  # inauguration month


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

    series = [{"date": f"{int(d['year'])}-{int(d['period'][1:]):02d}", "value": float(d["value"])}
              for d in rows if d["period"].startswith("M")]
    series.sort(key=lambda p: p["date"])

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == BASE_KEY), None)
    out = {
        "id": "unemployment", "name": "Unemployment rate", "category": "Economy",
        "value": latest["value"], "unit": "%", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": {"label": "At inauguration (Jan 2025)", "value": base},
        "source": {"name": "Bureau of Labor Statistics",
                   "url": "https://www.bls.gov/news.release/empsit.nr0.htm"},
        "cadence": "Monthly", "note": "Unemployment rate (U-3), seasonally adjusted.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
