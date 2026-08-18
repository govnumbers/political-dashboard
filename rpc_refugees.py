#!/usr/bin/env python3
"""Interest on the public debt, U.S. Treasury Fiscal Data "Interest Expense on
the Public Debt" dataset. Keyless.

Verified structure (Jul 2026): v2/accounting/od/interest_expense returns ~38
expense-category line items per month with `month_expense_amt` and
`fytd_expense_amt`. THERE IS NO TOTAL ROW, the total is the SUM of
`fytd_expense_amt` across ALL rows for a record_date, including negative
amortization/premium lines (sum everything, filter nothing). Includes interest
on both public issues and intragovernmental (Government Account Series) debt.

Stored series = fiscal-YTD total by month (resets each October)."""
import os
import sys
from collections import defaultdict
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/interest_expense"
HISTORY_START = "2012-10-01"


def sum_fytd(rows):
    """Sum fytd_expense_amt across all line items per record_date.
    Returns [{date: YYYY-MM, value: $B}] ascending. Sums EVERYTHING per date , 
    positive and negative lines alike."""
    totals = defaultdict(float)
    for row in rows:
        try:
            totals[row["record_date"][:7]] += float(row["fytd_expense_amt"])
        except (TypeError, ValueError, KeyError):
            continue
    return [{"date": d, "value": round(totals[d] / 1e9, 1)} for d in sorted(totals)]


def main():
    rows, page = [], 1
    while True:
        r = requests.get(API, params={
            "fields": "record_date,fytd_expense_amt",
            "filter": f"record_date:gte:{HISTORY_START}",
            "sort": "record_date",
            "page[size]": 10000, "page[number]": page,
        }, timeout=60)
        r.raise_for_status()
        batch = r.json()["data"]
        rows += batch
        if len(batch) < 10000:
            break
        page += 1

    series = sum_fytd(rows)
    if not series:
        raise RuntimeError("parsed zero interest-expense points")

    latest = series[-1]
    yoy_key = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"
    prior = next((p["value"] for p in series if p["date"] == yoy_key), None)

    out = {
        "id": "interest_on_debt", "name": "Interest on the public debt (fiscal-YTD)",
        "category": "Public Finances", "value": latest["value"], "unit": "$B",
        "as_of": latest["date"], "direction": "up_is_bad",
        "source": {"name": "U.S. Treasury, Fiscal Data",
                   "url": "https://fiscaldata.treasury.gov/datasets/interest-expense-public-debt/interest-expense-on-the-public-debt"},
        "cadence": "Monthly",
        "note": "Cumulative interest paid on all federal debt this fiscal year (resets each "
                "October). Includes intragovernmental holdings; single months are lumpy.",
    }
    if prior is not None:
        out["comparison"] = {"label": "Same period, prior fiscal year", "value": prior}
    publish(out, series=series)


if __name__ == "__main__":
    main()
