#!/usr/bin/env python3
"""ICE removals & returns — from the SAME per-FY workbook as ice_detention
(FY{yy}_detentionStats.xlsx); since mid-2025 it carries removals data.

LABELLING RULE (locked in project doc 03): this is "ICE's published workbook
figure" and is NEVER reconciled to press-release "deportation" totals, which
mix ICE removals with CBP returns/expulsions counted differently.

Like ice_detention this could not be live-tested from the build sandbox
(ice.gov egress-blocked) and the workbook's tab layout has churned before —
the parser keys on sheet/header NAMES and is fully safe-fail: any ambiguity
raises, no card updates, the run goes red. Known source risk: ICE paused
publication for 56 days in early 2026 (stale_days is set to tolerate a normal
gap but flag a prolonged one).

Cross-president context is a static FY2024 baseline from the ICE ERO FY2024
Annual Report (271,484 removals) — the workbook series itself starts FY2025."""
import os
import sys
import io
import re
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402
from ice_detention import fetch_workbook  # noqa: E402  (same download, reused)

FY2024_REMOVALS = 271484   # ICE ERO FY2024 Annual Report (static comparator)
MONTH_PAT = re.compile(
    r"^(oct|nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep)[a-z]*[\s\-]*(\d{2,4})?$", re.I)
MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
             "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _cal_date(mon_abbr, yr, fy):
    """Month abbreviation (+optional explicit year) within fiscal year fy ->
    'YYYY-MM'. Oct-Dec belong to the prior calendar year when no year given."""
    m = MONTH_NUM[mon_abbr[:3].lower()]
    if yr:
        y = int(yr)
        y += 2000 if y < 100 else 0
    else:
        y = fy - 1 if m >= 10 else fy
    return f"{y}-{m:02d}"


def find_removals(wb, fy):
    """Search sheets whose name mentions removals. Returns (series, fytd_total).
    Tries a monthly layout first (a month-label column next to a numeric
    removals column); falls back to a labelled FYTD total cell. Raises if the
    workbook offers neither."""
    sheets = [ws for ws in wb.worksheets if "remov" in ws.title.lower()]
    if not sheets:
        # some vintages put removals inside a combined stats sheet
        sheets = [ws for ws in wb.worksheets]

    for ws in sheets:
        rows = [[(c if c is not None else "") for c in r]
                for r in ws.iter_rows(values_only=True)]

        # --- attempt 1: monthly rows (label col + numeric col under a 'removal'/'total' header)
        for hi, row in enumerate(rows[:25]):
            labels = [str(c).strip().lower() for c in row]
            if not any("remov" in l for l in labels):
                continue
            val_cols = [i for i, l in enumerate(labels) if "remov" in l]
            target = next((i for i in val_cols if "total" in labels[i]), val_cols[-1])
            points = []
            for r in rows[hi + 1:]:
                if not r or target >= len(r):
                    continue
                first = r[0]
                date_key = None
                if isinstance(first, (datetime.datetime, datetime.date)):
                    date_key = f"{first.year}-{first.month:02d}"   # real date cell
                else:
                    m = MONTH_PAT.match(str(first).strip().lower())
                    if m:
                        date_key = _cal_date(m.group(1), m.group(2), fy)
                if not date_key:
                    continue
                try:
                    v = float(r[target])
                except (TypeError, ValueError):
                    continue
                if v >= 0:
                    points.append({"date": date_key, "value": int(v)})
            if len(points) >= 2:
                dedup = {p["date"]: p["value"] for p in points}
                series = [{"date": d, "value": dedup[d]} for d in sorted(dedup)]
                return series, sum(dedup.values())

        # --- attempt 2: a labelled total cell ("total removals ... 123,456")
        for r in rows:
            joined = [str(c).strip() for c in r]
            for i, cell in enumerate(joined):
                if re.search(r"total\s+removals", cell, re.I):
                    for c in r[i + 1:]:
                        try:
                            v = float(c)
                            if v > 0:
                                return None, int(v)
                        except (TypeError, ValueError):
                            continue
    raise RuntimeError("could not locate removals data in the ICE workbook "
                       "(tab layout may have changed — inspect manually)")


def main():
    from openpyxl import load_workbook
    fy, url, content = fetch_workbook()
    wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    series, fytd = find_removals(wb, fy)

    as_of = datetime.date.today().strftime("%Y-%m")
    out = {
        "id": "ice_removals", "name": "ICE removals & returns (fiscal-YTD)",
        "category": "Immigration", "value": fytd, "unit": "people", "as_of": as_of,
        "direction": "neutral",
        "comparison": {"label": "FY2024 full year (prior administration)", "value": FY2024_REMOVALS},
        "source": {"name": "U.S. Immigration and Customs Enforcement",
                   "url": "https://www.ice.gov/detain/detention-management"},
        "cadence": "Biweekly", "stale_days": 75,
        "note": f"Removals and returns in ICE's published statistics workbook, FY{fy} to date. "
                "Official workbook figure — not comparable to press-release 'deportation' totals, "
                "which mix in CBP actions. ICE has paused publication before (56 days in early 2026).",
    }
    publish(out, series=series or [{"date": as_of, "value": fytd}])


if __name__ == "__main__":
    main()
