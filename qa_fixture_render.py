#!/usr/bin/env python3
"""Defense outlays, U.S. Treasury Monthly Treasury Statement, Table 5
(outlays by agency). Keyless, same Fiscal Data API family as debt/deficit/
tariffs. v3 register #32 (War & Defense tab, locked 12 Aug 2026).

Verified structure (research, Aug 2026): the department aggregate line is
classification_desc = "Total--Department of Defense--Military Programs"
(June 2026: $78.78B gross / $78.33B net for the month), with gross/net
outlay fields for the month and fiscal-YTD plus the prior year's FYTD , 
the same built-in comparator as the tariffs table. History to ~2015.

RENAME GUARD: the department is being rebranded Defense -> War (defense.gov
already redirects to war.gov). The MTS label still said "Defense" at build
time; if the exact-match filter returns nothing, we re-fetch recent records
unfiltered and locate the aggregate line by regex on either name, so a quiet
relabel degrades to a slightly bigger fetch instead of a dead metric.

Stored series = fiscal-YTD NET outlays by month (resets each October, like
the deficit series; validator max_jump absorbs the reset)."""
import os
import re
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/mts_table_5"
HISTORY_START = "2014-10-01"
EXACT = "Total--Department of Defense--Military Programs"
RENAME = re.compile(r"total--department of (defense|war)--military programs", re.I)
FIELDS = ("record_date,classification_desc,"
          "current_month_gross_outly_amt,current_month_net_outly_amt,"
          "current_fytd_gross_outly_amt,current_fytd_net_outly_amt,"
          "prior_fytd_net_outly_amt")


def _fetch(params):
    r = requests.get(API, params=params, timeout=60)
    r.raise_for_status()
    return r.json()["data"]


def fetch_defense_rows():
    rows = _fetch({
        "fields": FIELDS,
        "filter": f"classification_desc:eq:{EXACT},record_date:gte:{HISTORY_START}",
        "sort": "record_date", "page[size]": 10000,
    })
    if rows:
        return rows
    # rename guard: pull everything and match either department name
    print("  ! defense_outlays: exact label returned no rows, scanning for a renamed line")
    allrows = _fetch({
        "fields": FIELDS,
        "filter": f"record_date:gte:{HISTORY_START}",
        "sort": "record_date", "page[size]": 10000,
    })
    rows = [r_ for r_ in allrows if RENAME.match(str(r_.get("classification_desc", "")).strip())]
    if not rows:
        raise RuntimeError("MTS table 5: no Department of Defense/War aggregate line found")
    return rows


def _b(row, key):
    """Whole dollars -> $B (1 decimal), or None."""
    try:
        return round(float(row[key]) / 1e9, 1)
    except (TypeError, ValueError, KeyError):
        return None


def main():
    rows = fetch_defense_rows()
    series = []
    for row in rows:
        v = _b(row, "current_fytd_net_outly_amt")
        if v is not None:
            series.append({"date": row["record_date"][:7], "value": v})
    if not series:
        raise RuntimeError("defense_outlays: parsed zero FYTD points")

    latest_row = rows[-1]
    latest = series[-1]
    prior = _b(latest_row, "prior_fytd_net_outly_amt")
    month_gross = _b(latest_row, "current_month_gross_outly_amt")
    month_net = _b(latest_row, "current_month_net_outly_amt")

    out = {
        "id": "defense_outlays", "name": "Defense outlays (fiscal-YTD)",
        "category": "War & Defense", "value": latest["value"], "unit": "$B",
        "as_of": latest["date"], "direction": "neutral",
        "source": {"name": "U.S. Treasury Monthly Treasury Statement",
                   "url": "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"},
        "cadence": "Monthly",
        "note": "Net outlays of the Department of Defense, Military Programs, fiscal-year-to-date "
                "(military pay, operations, procurement, R&D; excludes VA and civil programs). "
                "Congress appropriates; outlays lag decisions.",
    }
    if prior is not None:
        out["comparison"] = {"label": "Same point last fiscal year", "value": prior}
    if month_net is not None:
        out["latest_month"] = {"gross": month_gross, "net": month_net}
    publish(out, series=series)


if __name__ == "__main__":
    main()
