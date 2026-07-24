#!/usr/bin/env python3
"""Trade deficit (goods & services) — U.S. Census Bureau International Trade API
(FT900). Monthly total balance. Needs a free CENSUS_API_KEY
(https://api.census.gov/data/key_signup.html).

Stores a deep monthly series (since 2017); merges each run. Value converted from
millions USD to $B/month and shown as a positive deficit magnitude.

Census works KEYLESS at low volume (1 call/run), so this runs with or without
CENSUS_API_KEY — the key only raises rate limits. (Contrast with gas/EIA, which
requires a key.) NOTE: on the first live run, verify the FT900 fields/params
below against the current endpoint — Census occasionally revises the timeseries
path; a bad read is caught by the validators."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.census.gov/data/timeseries/intltrade/ft900"
BASE_KEY = "2025-01"  # inauguration month


def main():
    key = os.environ.get("CENSUS_API_KEY")
    params = {"get": "BAL_VAL_MO,time", "CTY_CODE": "-", "time": "from 2017-01"}
    if key:
        params["key"] = key  # optional: raises rate limits
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()
    header, data = rows[0], rows[1:]
    bal_i, time_i = header.index("BAL_VAL_MO"), header.index("time")

    series = []
    for row in data:
        try:
            series.append({"date": row[time_i], "value": round(abs(float(row[bal_i])) / 1000, 1)})
        except (TypeError, ValueError):
            continue
    series.sort(key=lambda p: p["date"])

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == BASE_KEY), None)
    baseline = ({"label": "At inauguration (Jan 2025)", "value": base}
                if base is not None else
                {"label": f"{series[-2]['date']} (prior month)", "value": series[-2]["value"]})
    out = {
        "id": "trade_deficit", "name": "Trade deficit (goods & services)",
        "category": "Economy", "value": latest["value"], "unit": "$B/mo", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": baseline,
        "source": {"name": "BEA / U.S. Census Bureau",
                   "url": "https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services"},
        "cadence": "Monthly", "note": "Monthly U.S. international trade deficit in goods and services.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
