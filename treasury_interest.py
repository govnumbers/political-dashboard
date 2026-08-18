#!/usr/bin/env python3
"""Tariff revenue (customs duties), U.S. Treasury Monthly Treasury Statement,
Table 4 (receipts by classification). Keyless, same Fiscal Data API family as
the debt and deficit connectors.

Verified structure (Jul 2026): filter classification_desc = "Customs Duties"
(line_code_nbr 405). Each monthly record carries gross receipts, refunds, and
net, both for the month and fiscal-year-to-date, PLUS the prior year's FYTD , 
a built-in comparator.

DISPLAY RULE (locked in project doc 02): gross AND net are always shown
together. June 2026 had ~$49B of refunds in a single month (International Emergency Economic Powers Act litigation),
making net negative while gross ran at record highs, either figure alone
misleads, in opposite directions.

Stored series = fiscal-YTD GROSS by month (resets each October, like the
budget-deficit series; the validator's wide max_jump absorbs the reset)."""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_4"
HISTORY_START = "2014-10-01"
FIELDS = ("record_date,line_code_nbr,classification_desc,"
          "current_month_gross_rcpt_amt,current_month_net_rcpt_amt,"
          "current_fytd_gross_rcpt_amt,current_fytd_net_rcpt_amt,"
          "prior_fytd_gross_rcpt_amt,prior_fytd_net_rcpt_amt")


def fetch_customs_rows():
    r = requests.get(API, params={
        "fields": FIELDS,
        "filter": f"classification_desc:eq:Customs Duties,record_date:gte:{HISTORY_START}",
        "sort": "record_date",
        "page[size]": 10000,
    }, timeout=60)
    r.raise_for_status()
    rows = r.json()["data"]
    # one row per record_date; if a date ever carries several, prefer line 405
    by_date = {}
    for row in rows:
        d = row["record_date"]
        if d not in by_date or str(row.get("line_code_nbr", "")).strip() == "405":
            by_date[d] = row
    return [by_date[d] for d in sorted(by_date)]


def _b(row, key):
    """Field in whole dollars -> $B (rounded 0.1), or None."""
    try:
        return round(float(row[key]) / 1e9, 1)
    except (TypeError, ValueError, KeyError):
        return None


def main():
    rows = fetch_customs_rows()
    if not rows:
        raise RuntimeError("no Customs Duties rows in mts_table_4")

    series, series_net = [], []
    for row in rows:
        v = _b(row, "current_fytd_gross_rcpt_amt")
        if v is not None:
            series.append({"date": row["record_date"][:7], "value": v})
        nv = _b(row, "current_fytd_net_rcpt_amt")
        if nv is not None:
            series_net.append({"date": row["record_date"][:7], "value": nv})
    if not series:
        raise RuntimeError("parsed zero customs-duties FYTD points")

    latest_row = rows[-1]
    net_fytd = _b(latest_row, "current_fytd_net_rcpt_amt")
    prior_gross = _b(latest_row, "prior_fytd_gross_rcpt_amt")
    month_gross = _b(latest_row, "current_month_gross_rcpt_amt")
    month_net = _b(latest_row, "current_month_net_rcpt_amt")

    note = "Customs duties collected this fiscal year (resets each October). Gross collections"
    if net_fytd is not None:
        note += f"; net of refunds ${net_fytd:,.0f}B"
    note += ". Courts ordered large tariff refunds in 2026, so both are shown, either alone misleads."

    out = {
        "id": "tariff_revenue", "name": "Tariff revenue (customs duties, fiscal-YTD)",
        "category": "Trade & Tariffs", "value": series[-1]["value"], "unit": "$B",
        "as_of": series[-1]["date"], "direction": "neutral",
        "net_fytd": net_fytd, "month_gross": month_gross, "month_net": month_net,
        "source": {"name": "U.S. Treasury, Monthly Treasury Statement",
                   "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/receipts-of-the-u-s-government"},
        "cadence": "Monthly", "note": note,
    }
    if prior_gross is not None:
        out["comparison"] = {"label": "Same period last fiscal year (gross)", "value": prior_gross}
    # Net-of-refunds FYTD line for the expanded chart (phase 7): same rows, the
    # net field, full history refetched every run, so plain overwrite is safe
    # and self-healing. Display rule (doc 02): gross and net always together.
    if series_net:
        out["series_net"] = series_net
    publish(out, series=series)


if __name__ == "__main__":
    main()
