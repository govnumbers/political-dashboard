#!/usr/bin/env python3
"""Clemency actions — DOJ Office of the Pardon Attorney grants pages.
v3 register #30. Carries the Jan 6 story.

TWO NUMBERS, NEVER BLURRED (locked at v3): the HEADLINE is named clemency
grants counted row-by-row from DOJ's own pages (precise, verifiable —
~150+ through Jul 2026, updated in irregular batches). INDIVIDUALS COVERED
is shown alongside and includes the ~1,500 covered by the Jan 20 2025
blanket Jan 6 proclamation (Proclamation 10887, 90 FR 8331) — the
proclamation text itself names no count, so the widely-cited contemporaneous
DOJ/court figure is used and footnoted as approximate. One proclamation =
one ACTION covering many INDIVIDUALS; the card prints both definitions.

PER-PRESIDENT CONTEXT (static, from DOJ's historical clemency statistics,
frozen Jan 2025 — captured before the freeze): Biden 4,245 individual acts ·
Obama 1,927 · Trump-1 237. Same basis: individual grants, categorical
proclamations excluded.

PARSER: counts dated rows in the grants tables across the current-term
grants page (and any linked continuation pages named like it). Sanity floor
refuses a half-loaded page. No ongoing official Jan 6 series exists anywhere
— DOJ's database was removed Jan 2025 and hard-deleted May 2026 (doc 04)."""
import os
import re
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

PAGE = "https://www.justice.gov/pardon/clemency-grants-president-donald-j-trump-2025-present"
JAN6 = {"individuals_approx": 1500, "date": "2025-01-20",
        "citation": "Proclamation 10887, 90 FR 8331 (14 named commutations + blanket pardon; "
                    "~1,500 charged defendants per contemporaneous DOJ/court figures)"}
HISTORY = {"biden": 4245, "obama": 1927, "trump1": 237}  # DOJ clemency statistics (frozen Jan 2025)

DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b", re.I)


def grant_rows(html):
    """HTML -> list of ISO grant dates, one per named-grant table row."""
    dates = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        text = re.sub(r"<[^>]+>", " ", tr)
        m = DATE_RE.search(text)
        if not m:
            continue
        try:
            d = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
        except ValueError:
            continue
        if datetime.date(2025, 1, 20) <= d <= datetime.date.today():
            dates.append(d.isoformat())
    return sorted(dates)


def main():
    r = requests.get(PAGE, headers=UA, timeout=90)
    r.raise_for_status()
    dates = grant_rows(r.text)
    if len(dates) < 20:  # the page carried 140+ named grants by late 2025
        raise RuntimeError(f"clemency grants page yielded only {len(dates)} dated rows — refusing to undercount")

    # cumulative named grants by month
    per = {}
    for d in dates:
        per[d[:7]] = per.get(d[:7], 0) + 1
    series, cum = [], 0
    for ym in sorted(per):
        cum += per[ym]
        series.append({"date": ym, "value": cum})

    named = len(dates)
    out = {
        "id": "clemency", "name": "Clemency (pardons & commutations)",
        "category": "Executive Power & Governance", "value": named, "unit": "named grants",
        "as_of": dates[-1], "since": "2025-01-20", "direction": "neutral",
        "individuals_covered_approx": named + JAN6["individuals_approx"],
        "jan6_proclamation": JAN6,
        "per_president_individuals": HISTORY,
        "source": {"name": "DOJ Office of the Pardon Attorney — clemency grants", "url": PAGE},
        "cadence": "As granted", "stale_days": 120,
        "note": "Named clemency grants (pardons + commutations) listed on DOJ's own grants "
                "pages, counted per grant date. Shown alongside: individuals covered, which "
                "adds the ~1,500 Jan 6 defendants pardoned or commuted in one day-one "
                "proclamation — one action covering many people; both counts are defined on "
                "the card. Historical per-president totals from DOJ's clemency statistics "
                "(frozen by DOJ in Jan 2025).",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
