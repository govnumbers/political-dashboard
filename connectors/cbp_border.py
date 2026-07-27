#!/usr/bin/env python3
"""Southwest land border encounters (monthly) — CBP.

CBP has no API and republishes a new "Southwest Land Border Encounters" CSV each
month (a single file spanning ~4 fiscal years, e.g. "FY23–FY26 (FYTD) … June").
This connector scrapes the official landing page for the newest such CSV,
downloads it, and sums to monthly totals. One file carries deep history, so the
merged series in data/ preserves it. Fully automated: each run picks up whatever
the newest monthly file is — no manual step.

Verified against the real June-2026 file. Real-file gotchas handled here:
  • Two month columns — "Month Grouping" (FYTD/Remaining) and "Month (abbv)" (the
    actual month). We use "Month (abbv)"; naively matching "month" grabs the wrong one.
  • "Encounter Count" vs "Encounter Type" — "count" is a substring of "enCOUNTer",
    so we match the full "encounter count", never bare "count".
  • Rows are tagged FYTD (elapsed) or "Remaining" (not-yet-happened months); we
    keep only FYTD so future months don't appear as zero.
  • Fiscal Year cells look like "2026 (FYTD)" → digits stripped to 2026.
  • The file is Southwest-only, so there is NO region column and no filtering.

Framing note: this number is currently DOWN sharply (favourable-to-Trump); it is
included for completeness. direction is 'neutral'; the Title 42→Title 8 shift
(May 2023) is noted on the card. Counts events, not unique people."""
import os
import re
import sys
import csv
import io
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish  # noqa: E402

LANDING = "https://www.cbp.gov/document/stats/southwest-land-border-encounters"
BASE = "https://www.cbp.gov"
# newest CSV: "sboencounters…fy23…fy26…jun.csv" — hyphens optional (CBP has used both)
CSV_RE = re.compile(r'href=["\']([^"\']*sbo-?encounters[^"\']*fy\d\d[^"\']*\.csv)["\']', re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def newest_csv_url():
    r = requests.get(LANDING, headers=UA, timeout=45)
    r.raise_for_status()
    matches = CSV_RE.findall(r.text)          # document order; CBP lists newest month first
    seen = set()
    ordered = [m for m in matches if not (m in seen or seen.add(m))]
    if not ordered:
        raise RuntimeError("no Southwest-encounters CSV link found on CBP landing page")
    best = ordered[0]
    return best if best.startswith("http") else BASE + best


def cal_month(fy, mon_abbr):
    """(fiscal year, calendar-month abbr) -> 'YYYY-MM'. FY Y = Oct(Y-1)..Sep(Y)."""
    m = MONTHS[mon_abbr.strip().lower()[:3]]
    return f"{fy - 1 if m >= 10 else fy}-{m:02d}"


def parse_csv(text):
    rows = list(csv.reader(io.StringIO(text)))

    def cols(cells):
        low = [str(c).strip().lower() for c in cells]

        def col(*names):
            for i, h in enumerate(low):
                if any(n in h for n in names):
                    return i
            return None
        # month: the "(abbv)" one, NOT "Month Grouping"; count: full "encounter count"
        return (col("fiscal year", "fiscal yr"), col("month (abbv)", "abbv"),
                col("encounter count"), col("month grouping", "grouping"))

    header_idx = fy_i = mon_i = cnt_i = grp_i = None
    for i, row in enumerate(rows[:15]):
        fy_i, mon_i, cnt_i, grp_i = cols(row)
        if None not in (fy_i, mon_i, cnt_i):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(f"could not find header row in CBP CSV; first rows: {rows[:3]}")

    totals = {}
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= max(fy_i, mon_i, cnt_i):
            continue
        if grp_i is not None and grp_i < len(row) and row[grp_i].strip().lower() not in ("fytd", ""):
            continue   # skip 'Remaining' (months that haven't happened yet)
        try:
            fy = int(re.sub(r"\D", "", row[fy_i]))          # "2026 (FYTD)" -> 2026
            ym = cal_month(fy, row[mon_i])
            cnt = int(float(re.sub(r"[^\d.]", "", row[cnt_i]) or 0))
        except (ValueError, KeyError):
            continue
        totals[ym] = totals.get(ym, 0) + cnt
    return totals


def main():
    url = newest_csv_url()
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    totals = parse_csv(r.text)

    series = [{"date": ym, "value": totals[ym]} for ym in sorted(totals)]
    if not series:
        raise RuntimeError("parsed zero monthly totals from CBP CSV")

    latest = series[-1]
    yoy_key = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"   # same month, prior year
    yoy = next((p["value"] for p in series if p["date"] == yoy_key), None)
    out = {
        "id": "border_encounters", "name": "Southwest border encounters",
        "category": "Immigration", "value": latest["value"], "unit": "per month", "as_of": latest["date"],
        "direction": "neutral",
        "source": {"name": "U.S. Customs and Border Protection", "url": LANDING},
        "cadence": "Monthly",
        "note": "Monthly Southwest land border encounters. Counts events, not unique people; "
                "composition shifts at the May 2023 Title 42 → Title 8 change.",
    }
    if yoy is not None:
        out["comparison"] = {"label": "Same month, prior year", "value": yoy}
    publish(out, series=series)


if __name__ == "__main__":
    main()
