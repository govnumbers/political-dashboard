#!/usr/bin/env python3
"""Executive orders signed — Federal Register API (keyless).
Headline = EOs signed by the current president since inauguration, with the
prior president's count over the equivalent window ('same point in the term').
Also stores a cumulative-by-month series so the pace is visible over time."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

API = "https://www.federalregister.gov/api/v1/documents.json"
TERM_START = datetime.date(2025, 1, 20)   # Trump inauguration
PREV_START = datetime.date(2021, 1, 20)   # Biden inauguration (comparison)


def count(president, gte, lte=None):
    conds = {
        "conditions[presidential_document_type]": "executive_order",
        "conditions[president]": president,
        "conditions[signing_date][gte]": gte.isoformat(),
        "per_page": 1,
    }
    if lte:
        conds["conditions[signing_date][lte]"] = lte.isoformat()
    r = requests.get(API, params=conds, timeout=30)
    r.raise_for_status()
    return r.json().get("count", 0)


def signing_dates(president, gte):
    """All EO signing dates for a president since gte (paginated)."""
    dates, page = [], 1
    while True:
        r = requests.get(API, params={
            "conditions[presidential_document_type]": "executive_order",
            "conditions[president]": president,
            "conditions[signing_date][gte]": gte.isoformat(),
            "fields[]": "signing_date",
            "per_page": 1000, "page": page,
        }, timeout=30)
        r.raise_for_status()
        js = r.json()
        results = js.get("results", []) or []
        dates += [d["signing_date"] for d in results if d.get("signing_date")]
        if len(results) < 1000:
            break
        page += 1
    return dates


def main():
    today = datetime.date.today()
    days_in = (today - TERM_START).days
    dates = signing_dates("donald-trump", TERM_START)
    trump = len(dates)
    biden = count("joe-biden", PREV_START, PREV_START + datetime.timedelta(days=days_in))

    # cumulative count by month
    monthly = {}
    for d in dates:
        monthly[d[:7]] = monthly.get(d[:7], 0) + 1
    cum, series = 0, []
    for ym in sorted(monthly):
        cum += monthly[ym]
        series.append({"date": ym, "value": cum})

    out = {
        "id": "executive_orders", "name": "Executive orders signed",
        "category": "Executive Power", "value": trump, "unit": "orders",
        "as_of": today.isoformat(), "since": TERM_START.isoformat(),
        "direction": "neutral",
        "comparison": {"label": "Biden at the same point in his term", "value": biden},
        "source": {"name": "Federal Register",
                   "url": "https://www.federalregister.gov/presidential-documents/executive-orders"},
        "cadence": "As signed",
        "note": "Executive orders signed since inauguration, vs the prior president over the equivalent window.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
