#!/usr/bin/env python3
"""Trade deficit (goods & services) — U.S. Census Bureau International Trade API.
Monthly total balance (FT900). Needs a free CENSUS_API_KEY
(https://api.census.gov/data/key_signup.html).

NOTE: verify the series/params against the current FT900 endpoint on first run —
Census occasionally revises the timeseries path. The value is reported in millions
USD; this connector converts to $B/month to match the dashboard unit."""
import json, os, requests

API = "https://api.census.gov/data/timeseries/intltrade/ft900"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "trade_deficit.json")

def main():
    key = os.environ.get("CENSUS_API_KEY")
    params = {"get": "CTY_CODE,ALL_VAL_MO,BAL_VAL_MO,time", "CTY_CODE": "-",
              "time": "from 2025-01"}
    if key:
        params["key"] = key
    r = requests.get(API, params=params, timeout=30); r.raise_for_status()
    rows = r.json()
    header, data = rows[0], rows[1:]
    bal_i, time_i = header.index("BAL_VAL_MO"), header.index("time")
    data.sort(key=lambda x: x[time_i])
    latest, prior = data[-1], data[-2]
    val = round(abs(float(latest[bal_i])) / 1000, 1)   # millions -> billions
    base = round(abs(float(prior[bal_i])) / 1000, 1)
    out = {
        "id": "trade_deficit", "name": "Trade deficit (goods & services)",
        "category": "Economy", "value": val, "unit": "$B/mo", "as_of": latest[time_i],
        "direction": "up_is_bad",
        "baseline": {"label": f"{prior[time_i]} (prior month)", "value": base},
        "source": {"name": "BEA / U.S. Census Bureau",
                   "url": "https://www.bea.gov/data/intl-trade-investment/international-trade-goods-and-services"},
        "cadence": "Monthly", "note": "Monthly U.S. international trade deficit in goods and services.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"trade_deficit: ${val}B ({out['as_of']})")

if __name__ == "__main__":
    main()
