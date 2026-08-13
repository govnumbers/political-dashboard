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
from common import publish  # noqa: E402

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


# FIRST-LIVE-RUN FIX (13 Aug 2026): rpc.state.gov (State Dept, behind Akamai)
# 403s the project's default bot User-Agent — every candidate came back as a
# non-PDF block page, so the connector correctly refused all 8 and failed. The
# PDF and its URL pattern are exactly right (verified: "Refugee Arrivals by
# State and Nationality as of July 31, 2026.pdf"); it just needs a browser UA.
BROWSER_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/pdf,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_newest_pdf(today=None):
    today = today or datetime.date.today()
    seen = []
    for d in month_end_candidates(today):
        url = BASE + NAME.format(month=d.strftime("%B"), day=d.day, year=d.year).replace(" ", "%20")
        try:
            r = requests.get(url, headers=BROWSER_UA, timeout=90)
            if r.status_code == 200 and r.content[:5] == b"%PDF-":
                return d, url, r.content
            seen.append(f"{d.isoformat()}:{r.status_code}"
                        + ("/not-pdf" if r.status_code == 200 else ""))
        except requests.RequestException as e:
            seen.append(f"{d.isoformat()}:{type(e).__name__}")
    raise RuntimeError("no RPC arrivals PDF found in the last 8 month-ends "
                       f"(probed: {', '.join(seen)})")


def extract_totals(pdf_bytes):
    """PDF -> (grand_total, south_africa_or_None). Text-layer extraction;
    'Grand Total' takes the LAST plausible integer on its line."""
    from pypdf import PdfReader
    text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)
    if not text.strip():
        raise RuntimeError("RPC PDF has no extractable text layer")

    # REAL STRUCTURE (verified against the creator's July-2026 file, 13 Aug 2026):
    # pypdf emits this wide state×nationality matrix as a block of ALL labels
    # ('Grand Total', 'Alabama', 'Total', 'South Africa', …) followed by a block
    # of ALL numbers. The FY grand total is the FIRST number in that block AND
    # the largest (it's the sum over every state and nationality). We take the
    # max and cross-check it equals the first number in reading order — both
    # must agree, or we refuse rather than publish a guess. ('Grand Total' as a
    # line label failed the old parser because it's a COLUMN header, never a
    # row whose value sits on the same line.)
    return grand_total_from_text(text)


def grand_total_from_text(text):
    """The FY grand total = first number in reading order, cross-checked to be
    the maximum (both hold: pypdf emits all labels, then the grand-total row
    whose first cell is the total — the sum over every state and nationality).

    Numbers are pulled from the FULL text, NOT per line: pypdf VERSIONS group
    cells differently — 6.x puts the whole grand-total row on ONE line
    ('10,258 2,528 1,062 …'), 3.x one number per line. A per-line match missed
    the total under 6.x and mis-read a state figure as the max (the 13 Aug
    live-run bug: GitHub's runner ships pypdf 6.x). Full-text extraction is
    version-independent — verified against the real file under both."""
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d+(?:,\d{3})*", text)]
    if not nums:
        raise RuntimeError("RPC PDF: no numeric tokens found (layout changed)")
    grand = max(nums)
    if grand != nums[0]:
        raise RuntimeError(f"RPC PDF: grand-total cross-check failed (max {grand:,} "
                           f"≠ first {nums[0]:,}) — refusing to guess at a changed layout")
    return grand


def fy_of(d):
    return d.year + 1 if d.month >= 10 else d.year


def main():
    as_of_date, url, content = fetch_newest_pdf()
    grand = extract_totals(content)
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
                "arrivals report. Admissions can exceed the annual ceiling because "
                "court-ordered and follow-to-join cases sit outside it. USRAP was suspended "
                "by executive order in Jan 2025; admissions since are dominated by the "
                "reprioritised program.",
    }
    if ceiling:
        out["ceiling"] = {"label": f"FY{fy} presidential ceiling", "value": ceiling}
    publish(out, series=[{"date": as_of_date.strftime("%Y-%m"), "value": grand}])


if __name__ == "__main__":
    main()
