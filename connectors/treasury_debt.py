#!/usr/bin/env python3
"""National debt — U.S. Treasury 'Debt to the Penny' API.
Pulls the latest total public debt outstanding and the value at inauguration."""
import json, os, datetime, requests

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "national_debt.json")

def latest():
    r = requests.get(API, params={"sort": "-record_date", "page[size]": 1}, timeout=30)
    r.raise_for_status()
    row = r.json()["data"][0]
    return row["record_date"], float(row["tot_pub_debt_out_amt"])

def at_inauguration():
    r = requests.get(API, params={"filter": "record_date:gte:2025-01-17",
                                  "sort": "record_date", "page[size]": 1}, timeout=30)
    r.raise_for_status()
    row = r.json()["data"][0]
    return row["record_date"], float(row["tot_pub_debt_out_amt"])

def main():
    as_of, value = latest()
    base_date, base_value = at_inauguration()
    out = {
        "id": "national_debt", "name": "National debt", "category": "Public Finances",
        "value": value, "unit": "USD", "as_of": as_of, "direction": "up_is_bad",
        "baseline": {"label": f"At inauguration ({base_date})", "value": base_value},
        "source": {"name": "U.S. Treasury — Debt to the Penny",
                   "url": "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/debt-to-the-penny"},
        "cadence": "Daily", "note": "Total public debt outstanding.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"national_debt: {value:,.0f} as of {as_of}")

if __name__ == "__main__":
    main()
