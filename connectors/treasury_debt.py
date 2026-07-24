#!/usr/bin/env python3
"""National debt — U.S. Treasury 'Debt to the Penny' API (keyless).
Stores the full daily series since 2017 (deep) so cross-administration
comparison is available later; merges each run so history survives even if the
source ever drops old rows. Headline = latest reading; baseline = inauguration.
"""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, today_iso  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
HISTORY_START = "2017-01-01"   # store deep: Trump I onward
TERM_START = "2025-01-17"      # first reading on/after inauguration


def fetch():
    r = requests.get(API, params={
        "fields": "record_date,tot_pub_debt_out_amt",
        "filter": f"record_date:gte:{HISTORY_START}",
        "sort": "record_date",
        "page[size]": 10000,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["data"]


def main():
    rows = fetch()
    series = [{"date": d["record_date"], "value": round(float(d["tot_pub_debt_out_amt"]), 2)}
              for d in rows]
    latest = series[-1]
    # inauguration baseline = first reading on/after TERM_START
    base = next((p for p in series if p["date"] >= TERM_START), series[0])
    out = {
        "id": "national_debt", "name": "National debt", "category": "Public Finances",
        "value": latest["value"], "unit": "USD", "as_of": latest["date"],
        "direction": "up_is_bad",
        "baseline": {"label": f"At inauguration ({base['date']})", "value": base["value"]},
        "source": {"name": "U.S. Treasury — Debt to the Penny",
                   "url": "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"},
        "cadence": "Daily", "note": "Total public debt outstanding.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
