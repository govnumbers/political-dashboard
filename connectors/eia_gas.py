#!/usr/bin/env python3
"""Gas price (US regular retail) — via FRED series GASREGW (keyless).

GASREGW is the EIA's weekly U.S. regular all-formulations retail gasoline price,
redistributed by the St. Louis Fed's FRED. FRED's CSV endpoint needs no API key,
so this metric self-updates with nothing to sign up for or manage. (Underlying
data is still EIA; FRED is just the keyless delivery.)"""
import os
import sys
import csv
import io
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = "GASREGW"
TERM_START = "2025-01-13"   # first weekly obs on/after inauguration week
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def fred_series(series_id):
    r = requests.get(API, params={"id": series_id}, headers=UA, timeout=45)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))
    out = []
    for row in rows[1:]:                      # row[0]=date, row[1]=value; '.' = missing
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            out.append((row[0], float(row[1])))
        except ValueError:
            continue
    return out


def main():
    raw = fred_series(SERIES)
    if not raw:
        raise RuntimeError("FRED returned no GASREGW observations")
    series = [{"date": d, "value": round(v, 3)} for d, v in raw]   # weekly, YYYY-MM-DD
    series.sort(key=lambda p: p["date"])

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] >= TERM_START), series[0]["value"])
    out = {
        "id": "gas_price", "name": "Gas price (regular)", "category": "Economy",
        "value": latest["value"], "unit": "$/gal", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": {"label": "At inauguration (Jan 2025)", "value": base},
        "source": {"name": "U.S. Energy Information Administration (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/GASREGW"},
        "cadence": "Weekly", "note": "US average regular gasoline, per gallon.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
