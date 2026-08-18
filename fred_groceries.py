#!/usr/bin/env python3
"""Clemency actions, Department of Justice Office of the Pardon Attorney grants pages.
v3 register #30. Carries the Jan 6 story.

TWO NUMBERS, NEVER BLURRED (locked at v3): the HEADLINE is named clemency
grants counted row-by-row from Department of Justice's own pages (precise, verifiable , 
~150+ through Jul 2026, updated in irregular batches). INDIVIDUALS COVERED
is shown alongside and includes the ~1,500 covered by the Jan 20 2025
blanket Jan 6 proclamation (Proclamation 10887, 90 FR 8331), the
proclamation text itself names no count, so the widely-cited contemporaneous
Department of Justice/court figure is used and footnoted as approximate. One proclamation =
one ACTION covering many INDIVIDUALS; the card prints both definitions.

PER-PRESIDENT CONTEXT (static, from Department of Justice's historical clemency statistics,
frozen Jan 2025, captured before the freeze): Biden 4,245 individual acts ·
Obama 1,927 · Trump-1 237. Same basis: individual grants, categorical
proclamations excluded.

PARSER: counts dated rows in the grants tables across the current-term
grants page (and any linked continuation pages named like it). Sanity floor
refuses a half-loaded page. No ongoing official Jan 6 series exists anywhere
,  Department of Justice's database was removed Jan 2025 and hard-deleted May 2026 (doc 04)."""
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
                    "~1,500 charged defendants per contemporaneous Department of Justice/court figures)"}
HISTORY = {"biden": 4245, "obama": 1927, "trump1": 237}  # Department of Justice clemency statistics (frozen Jan 2025)

DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\b", re.I)

# FIRST-LIVE-RUN FIX (12 Aug 2026): individual table rows carry only the
# SENTENCING date (in parentheses), the GRANT dates live in <strong> batch
# headings shaped "July 3, 2026 – 17 Pardons" / "May 28, 2025 - 16 Pardons and
# 6 Commutations" (hyphen OR en-dash; some marked "(Amended)"). So the counts
# come from Department of Justice's own stated batch totals, not row dates.
BATCH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})\s*[-–, ]\s*([^<]{0,120}?(?:Pardons?|Commutations?)[^<]{0,40})",
    re.I)


def grant_batches(html):
    """HTML -> [(iso_date, count, amended)] from Department of Justice's own batch headings.
    Counts are summed integers in the heading phrase ('16 Pardons and 6
    Commutations' -> 22). '(Amended)' batches are returned flagged and
    EXCLUDED from totals by the caller, amendments restate existing grants;
    counting them would double-count (stated in the method note)."""
    out = []
    for m in BATCH_RE.finditer(html):
        try:
            d = datetime.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y").date()
        except ValueError:
            continue
        if not (datetime.date(2025, 1, 20) <= d <= datetime.date.today()):
            continue
        phrase = m.group(4)
        nums = [int(n) for n in re.findall(r"\b(\d{1,4})\b", phrase)]
        if not nums:
            continue
        out.append((d.isoformat(), sum(nums), "amended" in phrase.lower()))
    return sorted(out)


def main():
    r = requests.get(PAGE, headers=UA, timeout=90)
    r.raise_for_status()
    batches = grant_batches(r.text)
    counted = [(d, n) for d, n, amended in batches if not amended]
    if sum(n for _, n in counted) < 50:  # the page carried 140+ named grants by late 2025
        raise RuntimeError(f"clemency batch headings summed to only "
                           f"{sum(n for _, n in counted)}, refusing to undercount")

    # cumulative named grants by month, from Department of Justice's own batch headings
    per = {}
    for d, n in counted:
        per[d[:7]] = per.get(d[:7], 0) + n
    series, cum = [], 0
    for ym in sorted(per):
        cum += per[ym]
        series.append({"date": ym, "value": cum})

    named = sum(n for _, n in counted)
    dates = [d for d, _ in counted]
    out = {
        "id": "clemency", "name": "Clemency (pardons & commutations)",
        "category": "Executive Power & Governance", "value": named, "unit": "named grants",
        "as_of": dates[-1], "since": "2025-01-20", "direction": "neutral",
        "individuals_covered_approx": named + JAN6["individuals_approx"],
        "jan6_proclamation": JAN6,
        "per_president_individuals": HISTORY,
        "source": {"name": "Department of Justice Office of the Pardon Attorney, clemency grants", "url": PAGE},
        "cadence": "As granted", "stale_days": 120,
        "note": "Named clemency grants (pardons + commutations) from Department of Justice's own grants page, "
                "summed from its dated batch headings ('(Amended)' batches excluded to avoid "
                "double-counting restated grants). Shown alongside: individuals covered, which "
                "adds the ~1,500 Jan 6 defendants pardoned or commuted in one day-one "
                "proclamation, one action covering many people; both counts are defined on "
                "the card. Historical per-president totals from Department of Justice's clemency statistics "
                "(frozen by Department of Justice in Jan 2025).",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
