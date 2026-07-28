#!/usr/bin/env python3
"""Trade deficit (goods & services) — via FRED series BOPGSTB (keyless).

BOPGSTB is the U.S. Census/BEA monthly Trade Balance in Goods and Services
(balance-of-payments basis, seasonally adjusted, millions USD), redistributed by
FRED. FRED's CSV endpoint needs no API key, so this self-updates with nothing to
manage. The balance is negative (a deficit); we show it as a positive $B
magnitude to match the card. (Underlying data is Census/BEA; FRED is delivery.)"""
import os
import sys
import csv
import io
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = "BOPGSTB"
BASE_KEY = "2025-01"   # inauguration month
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def main():
    r = requests.get(API, params={"id": SERIES}, headers=UA, timeout=45)
    r.raise_for_status()
    rows = list(csv.reader(io.StringIO(r.text)))

    series = []
    for row in rows[1:]:                       # row[0]=YYYY-MM-01, row[1]=millions (negative)
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            series.append({"date": row[0][:7], "value": round(abs(float(row[1])) / 1000, 1)})
        except ValueError:
            continue
    series.sort(key=lambda p: p["date"])
    if not series:
        raise RuntimeError("FRED returned no BOPGSTB observations")

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == BASE_KEY), None)
    baseline = ({"label": "At inauguration (Jan 2025)", "value": base}
                if base is not None else
                {"label": f"{series[-2]['date']} (prior month)", "value": series[-2]["value"]})
    out = {
        "id": "trade_deficit", "name": "Trade deficit (goods & services)",
        "category": "Trade & Tariffs", "value": latest["value"], "unit": "$B/mo", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": baseline,
        "source": {"name": "U.S. Census Bureau / BEA (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/BOPGSTB"},
        "cadence": "Monthly", "note": "Monthly U.S. international trade deficit in goods and services.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
