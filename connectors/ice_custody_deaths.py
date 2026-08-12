#!/usr/bin/env python3
"""Deaths in ICE custody — ICE's Detainee Death Reporting page (official,
per-death dated rows). v3 register #21.

SOURCE: ice.gov/detain/detainee-death-reporting — HTML tables per fiscal
year, one row per death (Date of Death, Name). History to FY2018. We COUNT
dated rows; names are never stored or published. FY2025 = 32 deaths, the
deadliest year in ~two decades; the connector recounts every fiscal year on
every run, so late-posted deaths (documented multi-week lags) revise history
upward through the normal merge/revision machinery rather than being missed.

DEFINITION BREAK (charted at build): in June 2026 ICE rescinded reporting of
deaths within 30 days of RELEASE (Directive 11003.6) — the series narrows
going forward; the card marks it like Title 42.

Headline = deaths in the CURRENT fiscal year to date (resets each October —
validator bounds are written for that shape). Series = one point per FY.
Parser is layout-tolerant: any date-like cell inside a table row counts as a
death record; sanity floor requires a plausible number of historical rows so
a half-loaded page can't publish an undercount."""
import os
import re
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

URL = "https://www.ice.gov/detain/detainee-death-reporting"
DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "mdy"),
    (re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b", re.I), "Bdy"),
]


def death_dates(html):
    """Page HTML -> sorted list of ISO dates, one per death row.
    Scans <tr> rows only (narrative text with dates can't leak in) and takes
    the FIRST date found in each row."""
    dates = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        text = re.sub(r"<[^>]+>", " ", tr)
        found = None
        for pat, kind in DATE_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            try:
                if kind == "mdy":
                    found = datetime.date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                else:
                    found = datetime.datetime.strptime(
                        f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
            except ValueError:
                continue
            break
        if found and datetime.date(2017, 10, 1) <= found <= datetime.date.today():
            dates.append(found)
    return sorted(dates)


def fy_of(d):
    return d.year + 1 if d.month >= 10 else d.year


def fy_counts(dates):
    out = {}
    for d in dates:
        out[fy_of(d)] = out.get(fy_of(d), 0) + 1
    return out


def main():
    r = requests.get(URL, headers=UA, timeout=90)
    r.raise_for_status()
    dates = death_dates(r.text)
    if len(dates) < 40:  # FY2018-24 alone exceed this; fewer = half-loaded page
        raise RuntimeError(f"death-reporting page yielded only {len(dates)} dated rows — refusing to undercount")

    counts = fy_counts(dates)
    current_fy = fy_of(datetime.date.today())
    fytd = counts.get(current_fy, 0)
    series = [{"date": f"{fy - 1}-10", "value": n} for fy, n in sorted(counts.items())]
    # series dates = each FY's start month; the current FY's point revises upward as deaths post

    out = {
        "id": "ice_custody_deaths", "name": "Deaths in ICE custody",
        "category": "Immigration", "value": fytd, "unit": f"deaths, FY{current_fy} to date",
        "as_of": datetime.date.today().isoformat(), "direction": "up_is_bad",
        "fy_counts": {str(fy): n for fy, n in sorted(counts.items())},
        "source": {"name": "ICE Detainee Death Reporting", "url": URL},
        "cadence": "As posted", "stale_days": 90,
        "note": "Deaths in ICE custody, counted from ICE's own per-death reporting page "
                "(one dated row per death; names never republished). ICE posts with "
                "documented delays, so recent counts revise upward. Since June 2026 ICE "
                "no longer reports deaths within 30 days of release — the series narrows "
                "from that date (marked on the chart).",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
