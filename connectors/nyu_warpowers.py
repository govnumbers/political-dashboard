#!/usr/bin/env python3
"""War-powers notifications — NYU Reiss Center War Powers Resolution Reporting
project (CSV compilation of official reports). v3 register #34.

LABELLED NON-GOVERNMENT SOURCE (the board's second, precedent VoteHub): the
project compiles every unclassified WPR 48-hour and periodic report to
Congress since 1973, each entry linking the underlying official document.
The card names the compiler. No official machine-readable list exists; the
recorded fallback (doc 04) is congress.gov executive communications (free
key + text matching) if the project ever stops.

This is the DEFINED PROXY for US military action abroad — the register's
answer to strike/casualty tallies that have no official dataset (boat-strike
deaths etc., rejected on principle in doc 07).

PARSER: discovers the CSV link on the project page (or uses a cached URL),
then label-keys the date column (first column whose values overwhelmingly
parse as dates). Headline = reports transmitted this term; context = prior
terms at the same point plus full-term totals, computed from the same file
every run. Verified current through Jul 10 2026 at lock."""
import csv
import io
import os
import re
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

SITE = "https://warpowers.lawandsecurity.org/"
TERM_START = datetime.date(2025, 1, 20)
TERMS = {"trump2": ("2025-01-20", None),
         "biden": ("2021-01-20", "2025-01-19"),
         "trump1": ("2017-01-20", "2021-01-19"),
         "obama": ("2009-01-20", "2013-01-19")}


def find_csv_url(html, base=SITE):
    cands = re.findall(r'href="([^"]+\.csv[^"]*)"', html, re.I)
    if not cands:
        raise RuntimeError("no CSV link found on the war-powers project page (site changed)")
    url = cands[0]
    if url.startswith("/"):
        url = base.rstrip("/") + url
    elif not url.startswith("http"):
        url = base.rstrip("/") + "/" + url
    return url


def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def report_dates(csv_text):
    """CSV text -> sorted report dates. The date column is detected, not
    assumed: the column where the most values parse as dates wins (and must
    clear 60% parseability + 50 rows to be believed)."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    if len(rows) < 10:
        raise RuntimeError("war-powers CSV implausibly small")
    header, body = rows[0], rows[1:]
    best_col, best_hits = None, 0
    for ci in range(len(header)):
        hits = sum(1 for r in body[:400] if ci < len(r) and _parse_date(r[ci]))
        if hits > best_hits:
            best_col, best_hits = ci, hits
    sample = min(len(body), 400)
    if best_col is None or best_hits < max(50, int(0.6 * sample)):
        raise RuntimeError("could not identify a date column in the war-powers CSV")
    dates = [d for r in body if best_col < len(r) for d in [_parse_date(r[best_col])] if d]
    if len(dates) < 80:  # >100 reports exist since 1973
        raise RuntimeError(f"war-powers CSV yielded only {len(dates)} dated reports — refusing")
    return sorted(dates)


def count_window(dates, start, end=None, days_cap=None):
    end = end or datetime.date.today()
    if days_cap is not None:
        end = min(end, start + datetime.timedelta(days=days_cap))
    return sum(1 for d in dates if start <= d <= end)


def main():
    page = requests.get(SITE, headers=UA, timeout=90)
    page.raise_for_status()
    csv_url = find_csv_url(page.text)
    r = requests.get(csv_url, headers=UA, timeout=90)
    r.raise_for_status()
    dates = report_dates(r.text)

    days_in = (datetime.date.today() - TERM_START).days
    this_term = [d for d in dates if d >= TERM_START]
    per = {}
    for d in this_term:
        per[d.strftime("%Y-%m")] = per.get(d.strftime("%Y-%m"), 0) + 1
    series, cum = [], 0
    for ym in sorted(per):
        cum += per[ym]
        series.append({"date": ym, "value": cum})

    prev = {}
    for pid, (s, e) in TERMS.items():
        if pid == "trump2":
            continue
        start = datetime.date.fromisoformat(s)
        end = datetime.date.fromisoformat(e)
        prev[pid] = {"same_point": count_window(dates, start, end, days_cap=days_in),
                     "full_term": count_window(dates, start, end)}

    out = {
        "id": "war_powers", "name": "War-powers reports to Congress",
        "category": "War & Defense", "value": len(this_term), "unit": "reports",
        "as_of": max(dates).isoformat(), "since": TERM_START.isoformat(),
        "direction": "neutral", "prev_terms": prev,
        "source": {"name": "NYU Reiss Center — War Powers Resolution Reporting project "
                           "(compilation of official reports)", "url": SITE},
        "cadence": "As filed", "stale_days": 120,
        "note": "War Powers Resolution reports transmitted to Congress this term — the "
                "officially defined record of US military action abroad (48-hour and "
                "periodic reports; each links its official document). Compiled by an "
                "academic project, named here because no official machine-readable list "
                "exists. Counts are a floor: classified annexes and disputed reporting "
                "duties mean not all activity is reported.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
