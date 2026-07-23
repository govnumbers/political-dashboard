#!/usr/bin/env python3
"""Executive orders signed — Federal Register API.
Counts EOs signed by the current president since inauguration, plus the
prior president's count over the equivalent window (an 'at the same point
in the term' comparison). Runs anywhere with open network (e.g. GitHub Actions)."""
import json, os, datetime, requests

API = "https://www.federalregister.gov/api/v1/documents.json"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "executive_orders.json")

TERM_START = datetime.date(2025, 1, 20)          # Trump inauguration
PREV_START = datetime.date(2021, 1, 20)           # Biden inauguration (comparison)

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

def main():
    today = datetime.date.today()
    days_in = (today - TERM_START).days
    trump = count("donald-trump", TERM_START)
    biden = count("joe-biden", PREV_START, PREV_START + datetime.timedelta(days=days_in))
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
    json.dump(out, open(OUT, "w"), indent=2)
    print(f"executive_orders: {trump} (Biden comp {biden})")

if __name__ == "__main__":
    main()
