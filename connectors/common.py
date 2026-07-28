#!/usr/bin/env python3
"""Shared connector plumbing: deep-store / shallow-load, merge-don't-overwrite,
revision detection, sanity validation, and freshness stamping.

Every connector builds a normalised dict and calls `publish(out, series=...)`.
publish() will:
  1. Load the existing data file (last-good), if any.
  2. Merge the new series points into the stored series WITHOUT overwriting the
     whole thing — new dates are added, existing dates are updated in place, and
     any change to a previously-stored value is flagged loudly as a REVISION
     (that's the change-detection feature: a quietly revised official figure
     shows up in both the Actions log and the git diff).
  3. Set value/as_of from the newest series point.
  4. Validate the newest value against validators.BOUNDS (bounds + max-jump vs
     the prior stored point). On failure it raises — the connector then exits
     non-zero, run_all keeps last-good, and the run goes red.
  5. Stamp `last_checked` (today) and compute `stale_after` from the cadence so
     the site can show an honest "may be stale" flag even if the pipeline dies.

Import from a connector with:
    import os, sys; sys.path.insert(0, os.path.dirname(__file__))
    from common import publish, today_iso
"""
import json
import os
import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validators import check, ValidationError, BOUNDS  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# Days after a metric's effective data-date beyond which we call it "may be
# stale". Chosen per cadence to absorb normal release lag but flag a genuinely
# skipped release or a dead pipeline. Longest matching key wins.
STALE_DAYS = {
    "biweek": 30,      # ICE detention republished ~every 2 weeks
    "as signed": 12,   # cumulative count; as_of == run date, so this catches pipeline death
    "as-signed": 12,
    "dai": 5,          # daily (debt)
    "week": 14,        # weekly (gas)
    "month": 70,       # monthly: must clear the SLOWEST reporter (trade lags ~5-6 wks),
                       # so a current latest-available figure never false-flags; still
                       # catches a genuinely missed monthly release (~one full cycle late).
    "as confirmed": 14,  # cumulative count refreshed every run (judges) — catches pipeline death
    "quarter": 130,    # quarterly (GDP, real wages): the next quarter's first estimate
                       # lands ~4 months after the reported quarter ends.
}
DEFAULT_STALE_DAYS = 45

# --- shared fetch helpers (used by the FRED-family connectors) ---------------
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def fred_series(series_id, timeout=45):
    """Fetch a FRED series via the keyless CSV endpoint.
    Returns [(date_str, float_value), ...] ascending; '.' rows (missing obs,
    e.g. the never-published Oct-2025 CPI) are skipped, never interpolated."""
    import csv as _csv
    import io as _io
    import requests as _requests
    r = _requests.get(FRED_CSV, params={"id": series_id}, headers=UA, timeout=timeout)
    r.raise_for_status()
    out = []
    for row in list(_csv.reader(_io.StringIO(r.text)))[1:]:
        if len(row) < 2 or row[1] in (".", ""):
            continue
        try:
            out.append((row[0], float(row[1])))
        except ValueError:
            continue
    if not out:
        raise RuntimeError(f"FRED returned no observations for {series_id}")
    return out


def quarter_month(fred_date):
    """FRED stamps quarterly obs with the quarter's FIRST day (2026-01-01 = Q1).
    Return the quarter's LAST month as 'YYYY-MM' (2026-01-01 -> '2026-03') so
    stored dates reflect when the quarter actually ended (freshness math)."""
    y, m = int(fred_date[:4]), int(fred_date[5:7])
    return f"{y}-{m + 2:02d}"


def today_iso():
    return datetime.date.today().isoformat()


def _path(metric_id):
    return os.path.join(DATA_DIR, f"{metric_id}.json")


def load_existing(metric_id):
    p = _path(metric_id)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def _effective_date(as_of):
    """Turn an as_of ('YYYY-MM-DD' or 'YYYY-MM') into the date the figure is
    'good through' — end of month for monthly periods, the date itself
    otherwise. Used only for the staleness clock."""
    try:
        if len(as_of) == 7:  # YYYY-MM
            y, m = int(as_of[:4]), int(as_of[5:7])
            nm = datetime.date(y + (m == 12), (m % 12) + 1, 1)
            return nm - datetime.timedelta(days=1)
        return datetime.date.fromisoformat(as_of)
    except Exception:
        return datetime.date.today()


def _stale_after(as_of, cadence):
    cad = (cadence or "").lower()
    days = DEFAULT_STALE_DAYS
    best = -1
    for key, d in STALE_DAYS.items():
        if key in cad and len(key) > best:
            days, best = d, len(key)
    return (_effective_date(as_of) + datetime.timedelta(days=days)).isoformat()


def merge_series(existing, new_points):
    """Merge new_points [{date, value}, ...] into the existing series.
    Returns (merged_ascending, revisions) where revisions is a list of
    (date, old_value, new_value) for any previously-stored date whose value
    changed by more than a rounding epsilon."""
    by_date = {}
    if existing:
        for pt in existing.get("series", []):
            by_date[pt["date"]] = pt["value"]

    revisions = []
    for pt in new_points or []:
        d, v = pt["date"], pt["value"]
        if d in by_date:
            old = by_date[d]
            try:
                changed = abs(float(old) - float(v)) > 1e-9
            except (TypeError, ValueError):
                changed = old != v
            if changed:
                revisions.append((d, old, v))
        by_date[d] = v

    merged = [{"date": d, "value": by_date[d]} for d in sorted(by_date)]
    return merged, revisions


def publish(out, series=None):
    """Validate, merge, freshness-stamp, and write data/<id>.json.
    `out` is the normalised metric dict (must include id, as_of, value or a
    non-empty series, cadence). `series` is the list of {date, value} points
    fetched this run (deep). Raises ValidationError if the newest value fails
    sanity checks — in which case NOTHING is written (last-good preserved)."""
    mid = out["id"]
    existing = load_existing(mid)

    # --- merge series (deep store) ---
    if series:
        merged, revisions = merge_series(existing, series)
        out["series"] = merged
        if revisions:
            for d, old, new in revisions:
                print(f"  ⤳ REVISION {mid} {d}: {old} → {new} (source revised a past value)")
        # newest point defines the headline value/as_of unless caller overrode
        if merged:
            newest = merged[-1]
            out.setdefault("value", newest["value"])
            out.setdefault("as_of", newest["date"])
    elif existing and "series" in existing:
        out["series"] = existing["series"]  # preserve history if this run had no series

    # --- previous stored value for the jump check ---
    prev_value = None
    if out.get("series") and len(out["series"]) >= 2:
        prev_value = out["series"][-2]["value"]
    elif existing:
        prev_value = existing.get("value")

    # --- sanity validation (may raise) ---
    if mid not in BOUNDS:
        print(f"  ! WARNING: no validation bounds defined for '{mid}' — publishing unchecked")
    check(mid, out["value"], prev_value)

    # --- freshness stamps ---
    out["last_checked"] = today_iso()
    if out.get("stale_days"):
        # Per-metric override for series that publish far behind real time
        # (overdose deaths ~5 months, Medicaid ~4, ICE workbook gaps): the
        # cadence-based clock would false-flag a perfectly current
        # latest-available figure.
        out["stale_after"] = (_effective_date(out["as_of"])
                              + datetime.timedelta(days=int(out["stale_days"]))).isoformat()
    else:
        out["stale_after"] = _stale_after(out["as_of"], out.get("cadence", ""))

    with open(_path(mid), "w") as f:
        json.dump(out, f, indent=2)
    n = len(out.get("series", []))
    print(f"  ✓ {mid}: {out['value']} as of {out['as_of']} ({n} pts, stale after {out['stale_after']})")
    return out
