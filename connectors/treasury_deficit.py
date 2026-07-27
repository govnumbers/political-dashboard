#!/usr/bin/env python3
"""Federal budget deficit (fiscal-year-to-date) — U.S. Treasury Monthly Treasury
Statement (MTS), Table 1. Keyless (same Fiscal Data API family as Debt to the Penny).

Verified structure (mts_table_1): each row is a period, identified by
`classification_desc` (month names, plus a "Year-to-Date" row and "FY YYYY"
rows). The net deficit/surplus for that period is in `current_month_dfct_sur_amt`
(reported in whole dollars; positive = deficit, i.e. outlays > receipts). We take
the "Year-to-Date" row at each record_date to get the running fiscal-YTD deficit,
convert to $B, and compare to the same fiscal position a year earlier.

The series resets each October (new fiscal year), which is expected and handled
by the validator's wider max-jump for this metric."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_1"
HISTORY_START = "2017-01-01"


def main():
    r = requests.get(API, params={
        "fields": "record_date,line_code_nbr,classification_desc,current_month_dfct_sur_amt",
        "filter": f"record_date:gte:{HISTORY_START}",
        "sort": "record_date",
        "page[size]": 10000,
    }, timeout=60)
    r.raise_for_status()
    data = r.json()["data"]

    # mts_table_1 has multiple "Year-to-Date" rows per date. Verified via the
    # receipts/outlays behind each: line 280 = the CURRENT fiscal-year-to-date
    # total (Oct→current month); line 140 = the PRIOR full fiscal year (shown for
    # comparison). record_fiscal_year tags both with the report year, so it can't
    # distinguish them — the line code can. Select line 280.
    ytd = [row for row in data
           if row.get("classification_desc", "").strip().lower() == "year-to-date"
           and str(row.get("line_code_nbr", "")).strip() == "280"]
    if not ytd:
        raise RuntimeError("no line-280 'Year-to-Date' rows in mts_table_1")

    series = []
    for row in ytd:
        try:
            val = float(row["current_month_dfct_sur_amt"]) / 1e9  # whole dollars -> $B
        except (TypeError, ValueError, KeyError):
            continue
        series.append({"date": row["record_date"][:7], "value": round(val, 1)})
    series.sort(key=lambda p: p["date"])
    if not series:
        raise RuntimeError("parsed zero year-to-date deficit points from mts_table_1")

    latest = series[-1]
    # same fiscal position one year earlier (both are Oct-through-<month> cumulatives)
    yoy_key = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"
    prior = next((p["value"] for p in series if p["date"] == yoy_key), None)

    out = {
        "id": "budget_deficit", "name": "Federal budget deficit (fiscal-YTD)",
        "category": "Public Finances", "value": latest["value"], "unit": "$B", "as_of": latest["date"],
        "direction": "up_is_bad",
        "source": {"name": "U.S. Treasury — Monthly Treasury Statement",
                   "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/summary-of-receipts-outlays-and-the-deficit-surplus-of-the-u-s-government"},
        "cadence": "Monthly",
        "note": "Cumulative federal budget deficit so far this fiscal year (resets each October).",
    }
    if prior is not None:
        out["comparison"] = {"label": "Same period, prior fiscal year", "value": prior}
    publish(out, series=series)


if __name__ == "__main__":
    main()
