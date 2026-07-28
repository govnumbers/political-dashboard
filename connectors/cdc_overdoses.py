#!/usr/bin/env python3
"""Drug overdose deaths (trailing 12 months, provisional) — CDC NCHS Vital
Statistics Rapid Release via the data.cdc.gov open API (keyless JSON).

Verified structure (Jul 2026): dataset xkb8-kh2a, rows filtered to state=US and
indicator="Number of Drug Overdose Deaths". Fields: year ("2026"), month (full
name, "February"), period ("12 month-ending"), data_value (reported, incomplete
for recent months), predicted_value (CDC's completeness-adjusted estimate).

USE predicted_value — reported counts for recent months are systematically low
because investigations are pending (CDC's own guidance). ~5-month publication
lag, hence the stale_days override."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

API = "https://data.cdc.gov/resource/xkb8-kh2a.json"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}
BASELINE_MONTH = "2025-01"


def rows_to_series(rows):
    """Rows -> [{date: YYYY-MM (12-month window END), value: deaths}], ascending.
    predicted_value preferred; data_value fallback."""
    out = []
    for row in rows:
        m = MONTHS.get(str(row.get("month", "")).strip())
        try:
            y = int(row["year"])
        except (TypeError, ValueError, KeyError):
            continue
        if not m:
            continue
        raw = row.get("predicted_value") or row.get("data_value")
        try:
            v = int(round(float(raw)))
        except (TypeError, ValueError):
            continue
        out.append({"date": f"{y}-{m:02d}", "value": v})
    out.sort(key=lambda p: p["date"])
    return out


def main():
    r = requests.get(API, params={
        "state": "US",
        "indicator": "Number of Drug Overdose Deaths",
        "$limit": 5000,
    }, headers=UA, timeout=60)
    r.raise_for_status()
    series = rows_to_series(r.json())
    if not series:
        raise RuntimeError("parsed zero overdose points from CDC VSRR")

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == BASELINE_MONTH), None)

    out = {
        "id": "overdose_deaths", "name": "Drug overdose deaths (trailing 12 months)",
        "category": "Health & Safety Net", "value": latest["value"], "unit": "deaths/12mo",
        "as_of": latest["date"], "direction": "up_is_bad",
        "source": {"name": "CDC — NCHS provisional overdose counts",
                   "url": "https://www.cdc.gov/nchs/nvss/vsrr/drug-overdose-data.htm"},
        "cadence": "Monthly", "stale_days": 240,
        "note": "Provisional CDC estimate (completeness-adjusted) of overdose deaths in the 12 "
                "months ending this month; reported ~5 months behind and revised.",
    }
    if base is not None:
        out["baseline"] = {"label": "12 months ending Jan 2025 (inauguration)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
