#!/usr/bin/env python3
"""Southwest land border encounters (monthly) — CBP.

CBP has no REST API and republishes the encounters CSV at a NEW path every month
(the URL encodes both the publish month and the data-through month, and the
fiscal-year window rolls each October). So this connector scrapes the official
landing page for the newest 'sbo-encounters' CSV link, downloads it, and sums to
monthly totals. The merged series in data/ is the historical store (git gives
revision history), so we survive CBP overwriting/rotating files.

Framing note: this number is currently DOWN sharply — a favourable-to-Trump
figure. It is included precisely because completeness (not cherry-picking) is
what makes the board credible; direction is 'neutral' (no good/bad colouring),
and the Title 42 → Title 8 definitional shift (May 2023) is noted on the card.

Could not be live-tested from the build sandbox (cbp.gov is egress-blocked
there); it runs from GitHub Actions. Any parse failure is safe-fail: no card,
loud red run, last-good preserved."""
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
CSV_RE = re.compile(r'href=["\']([^"\']*sbo-encounters-fy\d\d-fy\d\d-[a-z]{3}[^"\']*\.csv)["\']', re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def newest_csv_url():
    r = requests.get(LANDING, headers=UA, timeout=45)
    r.raise_for_status()
    hrefs = set(CSV_RE.findall(r.text))
    if not hrefs:
        raise RuntimeError("no sbo-encounters CSV link found on CBP landing page")

    def sort_key(h):
        pub = re.search(r"/(\d{4})-(\d{2})/", h)   # publish-month folder
        return (pub.group(0) if pub else "", h)
    best = sorted(hrefs, key=sort_key)[-1]
    return best if best.startswith("http") else BASE + best


def cal_month(fy, mon_abbr):
    """(fiscal year, calendar-month abbr) -> 'YYYY-MM'. FY Y = Oct(Y-1)..Sep(Y)."""
    m = MONTHS[mon_abbr.strip().lower()[:3]]
    year = fy - 1 if m >= 10 else fy
    return f"{year}-{m:02d}"


def main():
    url = newest_csv_url()
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    reader = csv.reader(io.StringIO(r.text))
    rows = list(reader)
    header = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for i, h in enumerate(header):
            if any(n in h for n in names):
                return i
        return None

    fy_i, mon_i, cnt_i = col("fiscal year"), col("month"), col("encounter count", "count")
    region_i = col("land border region", "region")
    if None in (fy_i, mon_i, cnt_i):
        raise RuntimeError(f"unexpected CBP CSV header: {rows[0]}")

    totals = {}
    for row in rows[1:]:
        if not row or len(row) <= max(fy_i, mon_i, cnt_i):
            continue
        if region_i is not None and row[region_i] and "southwest" not in row[region_i].lower():
            continue
        try:
            fy = int(re.sub(r"\D", "", row[fy_i]))
            ym = cal_month(fy, row[mon_i])
            cnt = int(float(re.sub(r"[^\d.]", "", row[cnt_i]) or 0))
        except (ValueError, KeyError):
            continue
        totals[ym] = totals.get(ym, 0) + cnt

    series = [{"date": ym, "value": totals[ym]} for ym in sorted(totals)]
    if not series:
        raise RuntimeError("parsed zero monthly totals from CBP CSV")

    latest = series[-1]
    # same month a year earlier (border flows are seasonal) as the honest comparison
    yoy_key = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"
    yoy = next((p["value"] for p in series if p["date"] == yoy_key), None)
    out = {
        "id": "border_encounters", "name": "Southwest border encounters",
        "category": "Immigration", "value": latest["value"], "unit": "per month", "as_of": latest["date"],
        "direction": "neutral",
        "source": {"name": "U.S. Customs and Border Protection",
                   "url": LANDING},
        "cadence": "Monthly",
        "note": "Monthly Southwest land border encounters. Counts events, not unique people; "
                "composition shifts at the May 2023 Title 42 → Title 8 change.",
    }
    if yoy is not None:
        out["comparison"] = {"label": "Same month, prior year", "value": yoy}
    publish(out, series=series)


if __name__ == "__main__":
    main()
