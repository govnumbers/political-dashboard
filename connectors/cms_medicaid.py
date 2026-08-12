#!/usr/bin/env python3
"""Medicaid & CHIP enrollment — CMS via the data.medicaid.gov open API
(keyless JSON, DKAN datastore).

Verified structure (Jul 2026): dataset 6165f45b-ca93-5bb5-9d06-db29c692a360
("State Medicaid and CHIP Applications, Eligibility Determinations, and
Enrollment Data"). State-level monthly rows with:
  reporting_period            "201309" (YYYYMM)
  state_name                  "Alaska"
  total_medicaid_and_chip_enrollment
  preliminary_or_updated      P/U
  final_report                Y/N

National total = sum of states per reporting_period, keeping the most-final row
per (state, period). A period only publishes once enough states have reported
(completeness guard), so the newest partial month never ships as a fake dip.
~4-month lag, hence the stale_days override."""
import os
import sys
from collections import defaultdict
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

DATASET = "6165f45b-ca93-5bb5-9d06-db29c692a360"
API = f"https://data.medicaid.gov/api/1/datastore/query/{DATASET}/0"
MIN_STATES = 45          # a month needs at least this many states to count
BASELINE_MONTH = "2024-12"


def aggregate(rows, min_states=MIN_STATES):
    """State rows -> national monthly series [{date: YYYY-MM, value: persons}].
    Keeps the most-final row per (state, period): final_report Y beats N,
    later fetch order beats earlier. Drops months with < min_states states."""
    best = {}
    for row in rows:
        p = str(row.get("reporting_period", "")).strip()
        s = (row.get("state_name") or "").strip()
        raw = row.get("total_medicaid_and_chip_enrollment")
        if len(p) != 6 or not p.isdigit() or not s or raw in (None, ""):
            continue
        try:
            v = int(float(raw))
        except (TypeError, ValueError):
            continue
        key = (s, p)
        is_final = str(row.get("final_report", "")).strip().upper() == "Y"
        if key not in best or is_final or not best[key][1]:
            best[key] = (v, is_final)

    months = defaultdict(list)
    for (s, p), (v, _) in best.items():
        months[f"{p[:4]}-{p[4:6]}"].append(v)

    return [{"date": d, "value": sum(vs)} for d, vs in sorted(months.items())
            if len(vs) >= min_states]


def trim_leading_orphans(series, run=6):
    """Drop isolated early months so the chart starts where coverage is
    CONTINUOUS (v3 lock, 12 Aug 2026 — the creator's 'orphan dot': the source's
    earliest months mostly fail the >=45-states rule, leaving one stranded
    point followed by years of nothing). Keep everything from the first month
    that begins `run` consecutive published months; annotate series start on
    the card instead. Never trims interior gaps — those stay visible."""
    def next_month(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        return f"{y + (m == 12)}-{(m % 12) + 1:02d}"
    dates = [p["date"] for p in series]
    for i in range(len(series)):
        ok, cur = True, dates[i]
        for j in range(1, run):
            if i + j >= len(series) or dates[i + j] != next_month(cur):
                ok = False
                break
            cur = dates[i + j]
        if ok:
            if i:
                print(f"  ⤳ medicaid: trimmed {i} leading orphan month(s) before {dates[i]} "
                      "(pre-continuous coverage)")
            return series[i:]
    return series


def main():
    rows, offset, page_size = [], 0, 500
    while True:
        r = requests.get(API, params={"limit": page_size, "offset": offset},
                         headers=UA, timeout=60)
        r.raise_for_status()
        batch = r.json().get("results", [])
        rows += batch
        if len(batch) < page_size:
            break
        offset += page_size

    series = aggregate(rows)
    if not series:
        raise RuntimeError("aggregated zero national Medicaid enrollment months")
    series = trim_leading_orphans(series)

    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == BASELINE_MONTH), None)

    out = {
        "id": "medicaid_enrollment", "name": "Medicaid & CHIP enrollment",
        "category": "Health & Safety Net", "value": latest["value"], "unit": "people",
        "as_of": latest["date"], "direction": "neutral",
        "source": {"name": "Centers for Medicare & Medicaid Services",
                   "url": "https://data.medicaid.gov/dataset/6165f45b-ca93-5bb5-9d06-db29c692a360"},
        "cadence": "Monthly", "stale_days": 180,
        "note": "Total people enrolled in Medicaid and CHIP, summed from state reports to CMS "
                "(~4-month lag; states revise).",
    }
    if base is not None:
        out["baseline"] = {"label": "Dec 2024", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
