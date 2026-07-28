#!/usr/bin/env python3
"""Federal judges confirmed (Article III) — Federal Judicial Center biographical
directory export (judicial-branch .gov, updated nightly, keyless CSV).

judges.csv is Article-III-only by construction (every lifetime federal judge
since 1789) — which cleanly excludes magistrate/bankruptcy judges. Appointment
fields repeat per appointment ("Appointing President (1)"… "(6)"), so columns
are detected by name pattern, not position. We count SENATE CONFIRMATION dates
(commissions trail votes by days; the FJC row itself can appear a few days
after the vote — acceptable lag for this cadence).

The same file yields the term-aligned comparison: Trump's first term and
Biden's term counted over the equivalent number of days — the cleanest
cross-president dataset on the board."""
import os
import sys
import csv
import io
import re
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, today_iso, UA  # noqa: E402

CSV_URL = "https://www.fjc.gov/sites/default/files/history/judges.csv"
TERM2 = datetime.date(2025, 1, 20)
TERM1 = datetime.date(2017, 1, 20)
BIDEN = datetime.date(2021, 1, 20)


def _parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def appointment_pairs(text):
    """CSV text -> [(president_name, confirmation_date), ...] across every
    numbered appointment column pair."""
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []

    def cols(prefix):
        out = {}
        for c in fields:
            m = re.match(rf"^{prefix}\s*(?:\((\d+)\))?$", c.strip(), re.IGNORECASE)
            if m:
                out[m.group(1) or "1"] = c
        return out

    pres_cols = cols("Appointing President")
    conf_cols = cols("Confirmation Date")
    if not pres_cols or not conf_cols:
        raise RuntimeError(f"FJC export columns not recognised (have {len(fields)} columns)")

    pairs = []
    for row in reader:
        for k, pcol in pres_cols.items():
            ccol = conf_cols.get(k)
            if not ccol:
                continue
            pres = (row.get(pcol) or "").strip()
            conf = _parse_date(row.get(ccol))
            if pres and conf:
                pairs.append((pres, conf))
    return pairs


def count_window(pairs, president_substr, start, days):
    end = start + datetime.timedelta(days=days)
    return sum(1 for pres, d in pairs
               if president_substr in pres and start <= d <= end)


def main():
    r = requests.get(CSV_URL, headers=UA, timeout=120)
    r.raise_for_status()
    pairs = appointment_pairs(r.text)

    today = datetime.date.today()
    days_in = (today - TERM2).days

    term2 = [(p, d) for p, d in pairs if "Trump" in p and d >= TERM2]
    trump1 = count_window(pairs, "Trump", TERM1, days_in)
    biden = count_window(pairs, "Biden", BIDEN, days_in)

    # cumulative-by-month series for the pace chart
    monthly = {}
    for _, d in term2:
        ym = d.strftime("%Y-%m")
        monthly[ym] = monthly.get(ym, 0) + 1
    cum, series = 0, []
    for ym in sorted(monthly):
        cum += monthly[ym]
        series.append({"date": ym, "value": cum})

    out = {
        "id": "judges_confirmed", "name": "Federal judges confirmed (Article III)",
        "category": "Executive Power & Governance", "value": len(term2), "unit": "judges",
        "as_of": today_iso(), "since": TERM2.isoformat(), "direction": "neutral",
        "comparison": {"label": "His first term at the same point", "value": trump1},
        "biden_same_point": biden,
        "source": {"name": "Federal Judicial Center — biographical directory",
                   "url": "https://www.fjc.gov/history/judges/biographical-directory-article-iii-federal-judges-export"},
        "cadence": "As confirmed",
        "note": "Lifetime (Article III) judges confirmed this term, counted by Senate "
                "confirmation date from the FJC's directory of every federal judge since 1789.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
