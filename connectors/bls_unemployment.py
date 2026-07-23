#!/usr/bin/env python3
"""Unemployment rate (U-3) — Bureau of Labor Statistics API.
Series LNS14000000 = civilian unemployment rate, seasonally adjusted."""
import json, os, datetime, requests

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
SERIES = "LNS14000000"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "unemployment.json")
BASE_YEAR, BASE_MONTH = 2025, 1  # inauguration month

def main():
    yr = datetime.date.today().year
    payload = {"seriesid": [SERIES], "startyear": "2025", "endyear": str(yr)}
    if os.environ.get("BLS_API_KEY"):
        payload["registrationkey"] = os.environ["BLS_API_KEY"]
    r = requests.post(API, json=payload, timeout=30); r.raise_for_status()
    rows = r.json()["Results"]["series"][0]["data"]
    idx = {(int(d["year"]), int(d["period"][1:])): float(d["value"])
           for d in rows if d["period"].startswith("M")}
    latest = max(idx)
    base = idx.get((BASE_YEAR, BASE_MONTH))
    out = {
        "id": "unemployment", "name": "Unemployment rate", "category": "Economy",
        "value": idx[latest], "unit": "%", "as_of": f"{latest[0]}-{latest[1]:02d}",
        "direction": "up_is_bad",
        "baseline": {"label": "At inauguration (Jan 2025)", "value": base},
        "source": {"name": "Bureau of Labor Statistics",
                   "url": "https://www.bls.gov/news.release/empsit.nr0.htm"},
        "cadence": "Monthly", "note": "Unemployment rate (U-3), seasonally adjusted.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"unemployment: {idx[latest]}% ({out['as_of']})")

if __name__ == "__main__":
    main()
