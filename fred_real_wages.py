#!/usr/bin/env python3
"""Foreign aid, USAspending (keyless), a CONSTRUCTED metric with the
definition printed on the card. v3 register #33 (War & Defense tab).

DEFINITION (fixed at v3 lock): federal obligations under budget function 150
,  "International Affairs", the OMB category that has defined the foreign-
affairs budget for decades (development and humanitarian aid, security
assistance, State operations, multilateral contributions). Broader than
"aid to poor countries", narrower than nothing: it is THE long-standing
official definition, which is why it's the one we compute. The card states
this; foreignassistance.gov (partial reporting since the USAID merger , 
doc 04 watch list) is the labelled cross-check.

SOURCE MECHANICS: USAspending's Spending Explorer API, POST /api/v2/spending/
with {"type": "budget_function", "filters": {"fy": YYYY, "quarter": Q}} , 
returns obligations by budget function, fiscal-year-to-date through that
quarter. Keyless, verified current to FY2026 Q3 (research, Aug 2026). We
build: closed fiscal years at Q4 (one point per FY, a stable annual history)
plus the current FY at its newest available quarter (the live headline),
with the prior year's same-quarter figure as the comparison."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

API = "https://api.usaspending.gov/api/v2/spending/"
FUNCTION_NAME = "international affairs"
FIRST_FY = 2017          # API-supported history floor for this endpoint era
FY_END_MONTH = {1: "12", 2: "03", 3: "06", 4: "09"}  # quarter -> calendar month it ends


def fy_of(d):
    return d.year + 1 if d.month >= 10 else d.year


def fetch_function_amount(fy, quarter):
    """Obligations ($) for budget function 150, FYTD through `quarter` of `fy`,
    or None if that period isn't published yet."""
    r = requests.post(API, json={"type": "budget_function",
                                 "filters": {"fy": str(fy), "quarter": str(quarter)}},
                      headers=dict(UA, **{"Content-Type": "application/json"}), timeout=60)
    if r.status_code >= 500:
        r.raise_for_status()
    js = r.json()
    for row in js.get("results", []) or []:
        if FUNCTION_NAME in str(row.get("name", "")).lower():
            try:
                return float(row["amount"])
            except (TypeError, ValueError, KeyError):
                return None
    return None


def quarter_date(fy, quarter):
    """FY+quarter -> the calendar YYYY-MM that quarter ends (FY starts in Oct)."""
    month = FY_END_MONTH[quarter]
    year = fy - 1 if quarter == 1 else fy
    return f"{year}-{month}"


def main():
    today = datetime.date.today()
    current_fy = fy_of(today)

    series, latest_q, prior_same_q = [], None, None
    # closed fiscal years: one Q4 point each (annual history)
    for fy in range(FIRST_FY, current_fy):
        amt = fetch_function_amount(fy, 4)
        if amt is not None:
            series.append({"date": quarter_date(fy, 4), "value": round(amt / 1e9, 1)})

    # current FY: newest published quarter, walking back
    for q in (4, 3, 2, 1):
        amt = fetch_function_amount(current_fy, q)
        if amt is not None:
            series.append({"date": quarter_date(current_fy, q), "value": round(amt / 1e9, 1)})
            latest_q = q
            prior = fetch_function_amount(current_fy - 1, q)
            if prior is not None:
                prior_same_q = round(prior / 1e9, 1)
            break
    if not series:
        raise RuntimeError("USAspending returned no international-affairs amounts")
    series.sort(key=lambda p: p["date"])
    latest = series[-1]

    out = {
        "id": "foreign_aid", "name": "Foreign aid & international affairs (obligations)",
        "category": "War & Defense", "value": latest["value"], "unit": "$B",
        "as_of": latest["date"], "direction": "neutral",
        "source": {"name": "USAspending (budget function 150)",
                   "url": "https://www.usaspending.gov/explorer/budget_function"},
        "cadence": "Quarterly", "stale_days": 160,
        "note": "Federal obligations under budget function 150, International Affairs, "
                "the official category covering development and humanitarian aid, security "
                "assistance, State operations and multilateral contributions. Obligations "
                "are commitments, not cash delivered; the USAID→State transition muddies "
                "2025 reporting (cross-checked against foreignassistance.gov).",
    }
    if latest_q and prior_same_q is not None:
        out["comparison"] = {"label": f"Same point FY{current_fy - 1}", "value": prior_same_q}
        out["fytd_quarter"] = latest_q
    publish(out, series=series)


if __name__ == "__main__":
    main()
