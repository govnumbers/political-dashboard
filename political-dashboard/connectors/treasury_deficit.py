#!/usr/bin/env python3
"""Federal budget deficit (fiscal-year-to-date) — U.S. Treasury Monthly Treasury
Statement (MTS), Table 1 'Summary of Receipts, Outlays, and the Deficit/Surplus'.
Keyless (same Fiscal Data API family as Debt to the Penny).

The MTS deficit is naturally a fiscal-YTD figure that resets each October, and
the table conveniently carries the same period a year earlier as a built-in
comparison. Amounts are reported in millions; we convert to $B.

Robustness: this connector could not be live-tested from the build sandbox
(government APIs are egress-blocked there), so it DETECTS the relevant fields
and the deficit row dynamically rather than hard-coding exact field strings. If
Treasury's schema differs, the read fails cleanly and the validators/loud-fail
keep last-good — no bad number reaches the site."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_1"
HISTORY_START = "2017-01-01"


def _find_key(row, *must_contain):
    for k in row:
        kl = k.lower()
        if all(t in kl for t in must_contain):
            return k
    return None


def main():
    r = requests.get(API, params={
        "filter": f"record_date:gte:{HISTORY_START}",
        "sort": "record_date",
        "page[size]": 10000,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]
    if not data:
        raise RuntimeError("MTS returned no rows")

    # deficit/surplus summary rows only
    deficit_rows = [row for row in data
                    if "deficit" in row.get("classification_desc", "").lower()]
    if not deficit_rows:
        raise RuntimeError("could not locate a Deficit/Surplus row in mts_table_1 "
                           f"(classifications seen: {sorted({d.get('classification_desc','') for d in data})[:8]})")

    sample = deficit_rows[-1]
    fytd_key = _find_key(sample, "current", "fytd", "amt") or _find_key(sample, "fytd", "amt")
    prior_key = _find_key(sample, "prior", "fytd", "amt")
    if not fytd_key:
        raise RuntimeError(f"no fiscal-YTD amount field found; keys were {list(sample)}")

    series = []
    for row in deficit_rows:
        try:
            val = abs(float(row[fytd_key])) / 1000.0  # millions -> $B, deficit magnitude
        except (TypeError, ValueError, KeyError):
            continue
        series.append({"date": row["record_date"][:7], "value": round(val, 1)})
    series.sort(key=lambda p: p["date"])
    if not series:
        raise RuntimeError("parsed zero deficit points from mts_table_1")

    latest = series[-1]
    comparison = None
    if prior_key:
        try:
            comparison = {"label": "Same period, prior fiscal year",
                          "value": round(abs(float(sample[prior_key])) / 1000.0, 1)}
        except (TypeError, ValueError):
            comparison = None

    out = {
        "id": "budget_deficit", "name": "Federal budget deficit (fiscal-YTD)",
        "category": "Public Finances", "value": latest["value"], "unit": "$B", "as_of": latest["date"],
        "direction": "up_is_bad",
        "source": {"name": "U.S. Treasury — Monthly Treasury Statement",
                   "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/summary-of-receipts-outlays-and-the-deficit-surplus-of-the-u-s-government"},
        "cadence": "Monthly",
        "note": "Cumulative federal budget deficit so far this fiscal year (resets each October).",
    }
    if comparison:
        out["comparison"] = comparison
    publish(out, series=series)


if __name__ == "__main__":
    main()
