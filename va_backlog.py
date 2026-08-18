#!/usr/bin/env python3
"""Measles cases, Centers for Disease Control and Prevention measles surveillance page (weekly-updated HTML; no
published API, so this is a deliberate, tightly-anchored scrape, safe-fail on
any structure change).

Verified page language (Jul 2026):
  "As of June 4, 2026, 2,030 confirmed* measles cases were reported in the
   United States in 2026."
  "For the full year of 2025, a total of 2,288 confirmed* measles cases..."

HONEST FRESHNESS: as_of is the page's OWN "as of" date, not our run date, if
Centers for Disease Control and Prevention stops updating (the page was ~8 weeks behind by late Jul 2026), the card's
stale flag fires on the source's staleness, which is exactly the transparency
the product wants.

Historical annual counts (static, from the same Centers for Disease Control and Prevention surveillance reporting)
give the chart its context; the current year's point updates in place."""
import os
import sys
import re
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

PAGE = "https://www.cdc.gov/measles/data-research/index.html"

# Centers for Disease Control and Prevention annual confirmed measles cases (static context; current year comes live).
HISTORICAL = {
    2015: 188, 2016: 86, 2017: 120, 2018: 375, 2019: 1274,
    2020: 13, 2021: 49, 2022: 121, 2023: 59, 2024: 285, 2025: 2288,
}

CURRENT_PAT = re.compile(
    r"As of\s+([A-Z][a-z]+ \d{1,2}, \d{4}),?\s+([\d,]+)\s+confirmed\*?\s+measles cases?\s+"
    r"were reported in the United States in\s+(\d{4})", re.I)
PRIOR_PAT = re.compile(
    r"full year of\s+(\d{4}),\s+a total of\s+([\d,]+)\s+confirmed", re.I)


def parse_page(html):
    """Returns (as_of_iso, ytd_count, year). Raises if the sentence anchor is gone."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    m = CURRENT_PAT.search(text)
    if not m:
        raise RuntimeError("Centers for Disease Control and Prevention measles page sentence anchor not found (page restructured?)")
    as_of = datetime.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    return as_of, int(m.group(2).replace(",", "")), int(m.group(3))


def main():
    r = requests.get(PAGE, headers=UA, timeout=60)
    r.raise_for_status()
    as_of, ytd, year = parse_page(r.text)

    series = [{"date": f"{y}-12", "value": v} for y, v in sorted(HISTORICAL.items())]
    series.append({"date": f"{year}-12", "value": ytd})   # current year, updates in place

    prior = HISTORICAL.get(year - 1)
    out = {
        "id": "measles_cases", "name": f"Measles cases ({year} to date)",
        "category": "Health & Safety Net", "value": ytd, "unit": "confirmed cases",
        "as_of": as_of, "direction": "up_is_bad",
        "source": {"name": "Centers for Disease Control and Prevention, measles cases and outbreaks",
                   "url": "https://www.cdc.gov/measles/data-research/index.html"},
        "cadence": "Weekly", "stale_days": 45,
        "note": "Confirmed cases reported to Centers for Disease Control and Prevention, year to date, dated by Centers for Disease Control and Prevention's own 'as of' line, "
                "if this card flags stale, Centers for Disease Control and Prevention has stopped updating. Measles was declared "
                "eliminated in the US in 2000; 2025's total was the worst since 1992.",
    }
    if prior is not None:
        out["comparison"] = {"label": f"Full year {year - 1}", "value": prior}
    publish(out, series=series)


if __name__ == "__main__":
    main()
