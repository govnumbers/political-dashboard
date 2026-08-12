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
from common import publish, load_existing  # noqa: E402

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


def signing_dates(president, gte, lte=None):
    """All EO signing dates for a president since gte (paginated); lte bounds a
    closed term for the one-time cross-president backfill."""
    dates, page = [], 1
    while True:
        params = {
            "conditions[presidential_document_type]": "executive_order",
            "conditions[president]": president,
            "conditions[signing_date][gte]": gte.isoformat(),
            "fields[]": "signing_date",
            "per_page": 1000, "page": page,
        }
        if lte:
            params["conditions[signing_date][lte]"] = lte.isoformat()
        r = requests.get(API, params=params, timeout=30)
        r.raise_for_status()
        js = r.json()
        results = js.get("results", []) or []
        dates += [d["signing_date"] for d in results if d.get("signing_date")]
        if len(results) < 1000:
            break
        page += 1
    return dates


def month_curve(dates, start, months=48):
    """Signing dates -> dense cumulative-by-month curve for a term's first
    `months` months: [{"month": m, "value": cum}] with empty months carrying
    the running count (the meaning of a cumulative counter, not interpolation)."""
    per = {}
    for ds in dates:
        d = datetime.date.fromisoformat(ds)
        mi = (d.year - start.year) * 12 + (d.month - start.month)
        if 0 <= mi <= months:
            per[mi] = per.get(mi, 0) + 1
    if not per:
        return []
    out, cum = [], 0
    for m in range(0, max(per) + 1):
        cum += per.get(m, 0)
        out.append({"month": m, "value": cum})
    return out


# Closed prior terms for the term-aligned chart. Fetched ONCE (the data can
# never change — the terms are over), then carried forward from the stored
# file on every later run. A fetch failure only skips the enhancement — the
# live metric still publishes.
PREV_TERMS = {"biden": (datetime.date(2021, 1, 20), datetime.date(2025, 1, 19)),
              "obama": (datetime.date(2009, 1, 20), datetime.date(2013, 1, 19)),
              # v3 lock: Trump-'17 curve powers the four-bar collapsed strip
              "trump1": (datetime.date(2017, 1, 20), datetime.date(2021, 1, 19))}
PREV_SLUG = {"biden": "joe-biden", "obama": "barack-obama", "trump1": "donald-trump"}


def prev_term_curves(existing):
    have = (existing or {}).get("prev_terms") or {}
    if all(k in have and have[k] for k in PREV_TERMS):
        return have
    curves = dict(have)
    for pid, (start, end) in PREV_TERMS.items():
        if curves.get(pid):
            continue
        try:
            curve = month_curve(signing_dates(PREV_SLUG[pid], start, lte=end), start)
            if curve:
                curves[pid] = curve
                print(f"  ✓ executive_orders: backfilled {pid} curve ({curve[-1]['value']} EOs over {len(curve)} months)")
        except Exception as e:                                    # noqa: BLE001
            print(f"  ! executive_orders: {pid} backfill failed this run ({e}) — will retry next run")
    return curves


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
        "category": "Executive Power & Governance", "value": trump, "unit": "orders",
        "as_of": today.isoformat(), "since": TERM_START.isoformat(),
        "direction": "neutral",
        "comparison": {"label": "Biden at the same point in his term", "value": biden},
        "source": {"name": "Federal Register",
                   "url": "https://www.federalregister.gov/presidential-documents/executive-orders"},
        "cadence": "As signed",
        "note": "Executive orders signed since inauguration, vs the prior president over the equivalent window.",
    }
    prev = prev_term_curves(load_existing("executive_orders"))
    if prev:
        out["prev_terms"] = prev

    # v3 lock: all-time per-president totals (NARA disposition ranges; pre-FDR
    # UCSB, labelled — citations + the Obama-count flag live in the static
    # file). Enhancement-only: never blocks the live metric.
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "static", "eo_alltime.json")) as f:
            st = _json.load(f)
        out["all_time"] = {"nara_modern": st["nara_modern"],
                           "ucsb_pre_fdr": st["ucsb_pre_fdr"],
                           "flags": st["_flags"]}
    except Exception as e:  # noqa: BLE001
        print(f"  ! executive_orders: all-time totals skipped this run ({e})")

    publish(out, series=series)


if __name__ == "__main__":
    main()
