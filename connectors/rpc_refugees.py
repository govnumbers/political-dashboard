#!/usr/bin/env python3
"""Refugee admissions — State Dept Refugee Processing Center monthly PDF.
v3 register #22. THE BOARD'S FIRST PDF PARSER.

DEPENDENCY NOTE (delivery checklist): requires `pypdf` — the workflow's
install line must read `pip install requests openpyxl pypdf` (one-line
hand-edit on GitHub; .github/ is remote-write-protected).

SOURCE MECHANICS: monthly "Refugee Arrivals by State and Nationality as of
{Month DD, YYYY}" PDFs at rpc.state.gov, dated to month-end. Publication is
irregular (Nov 2025 never posted) — the connector probes the last several
month-ends and takes the newest that exists, so a skipped month degrades to
the prior month's data instead of failing. Headline = fiscal-year-to-date
grand total vs the presidential ceiling (7,500 for FY2026 — the lowest ever
set). Arrivals can exceed the ceiling: court-ordered and follow-to-join
cases sit outside it — the card says so.

The 'Grand Total' figure is extracted from the PDF text; a South Africa row
is captured opportunistically as the composition context line (≈86% of FY26
arrivals at lock — the *who*, not just the how-many, is the record)."""
import os
import re
import sys
import io
import datetime
import calendar
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

BASE = "https://www.rpc.state.gov/documents/"
NAME = "Refugee Arrivals by State and Nationality as of {month} {day}, {year}.pdf"
ARCHIVE_PAGE = "https://www.rpc.state.gov/archives/"
CEILINGS = {2026: 7500, 2025: 125000, 2024: 125000}  # presidential determinations
# (FY2025's ceiling was set under the prior administration; USRAP was suspended
#  by EO on 27 Jan 2025 — the card's note carries this.)


def month_end_candidates(today, back=8):
    """Newest-first list of month-end dates to probe."""
    out, y, m = [], today.year, today.month
    for _ in range(back):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(datetime.date(y, m, calendar.monthrange(y, m)[1]))
    return out


def fetch_newest_pdf(today=None):
    today = today or datetime.date.today()
    for d in month_end_candidates(today):
        url = BASE + NAME.format(month=d.strftime("%B"), day=d.day, year=d.year).replace(" ", "%20")
        try:
            r = requests.get(url, headers=UA, timeout=90)
            if r.status_code == 200 and r.content[:5] == b"%PDF-":
                return d, url, r.content
        except requests.RequestException:
            continue
    raise RuntimeError("no RPC arrivals PDF found in the last 8 month-ends")


def extract_totals(pdf_bytes):
    """PDF -> (grand_total, south_africa_or_None). Text-layer extraction;
    'Grand Total' takes the LAST plausible integer on its line."""
    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    if not text.strip():
        raise RuntimeError("RPC PDF has no extractable text layer")

    def last_int(line):
        nums = re.findall(r"\b\d{1,3}(?:,\d{3})*\b", line)
        return int(nums[-1].replace(",", "")) if nums else None

    grand, sa = None, None
    for line in text.splitlines():
        l = line.strip()
        if re.match(r"grand total", l, re.I):
            grand = last_int(l) or grand
        elif re.match(r"south africa", l, re.I):
            sa = last_int(l) or sa
    if grand is None:
        raise RuntimeError("'Grand Total' not found in RPC PDF text (layout changed)")
    return grand, sa


def fy_of(d):
    return d.year + 1 if d.month >= 10 else d.year


def main():
    as_of_date, url, content = fetch_newest_pdf()
    grand, south_africa = extract_totals(content)
    fy = fy_of(as_of_date)
    ceiling = CEILINGS.get(fy)

    out = {
        "id": "refugee_admissions", "name": "Refugee admissions (fiscal-YTD)",
        "category": "Immigration", "value": grand, "unit": "arrivals",
        "as_of": as_of_date.isoformat(), "direction": "neutral",
        "source": {"name": "State Dept Refugee Processing Center (monthly report)",
                   "url": url},
        "cadence": "Monthly", "stale_days": 100,
        "note": f"Refugees admitted FY{fy} to date, from the State Department's monthly "
                "arrivals report. Admissions can exceed the ceiling because court-ordered "
                "and follow-to-join cases sit outside it. USRAP was suspended by executive "
                "order in Jan 2025; admissions since are dominated by the reprioritised "
                "program (composition shown from the same report).",
    }
    if ceiling:
        out["ceiling"] = {"label": f"FY{fy} presidential ceiling", "value": ceiling}
    if south_africa is not None:
        out["south_africa"] = south_africa
    publish(out, series=[{"date": as_of_date.strftime("%Y-%m"), "value": grand}])


if __name__ == "__main__":
    main()
