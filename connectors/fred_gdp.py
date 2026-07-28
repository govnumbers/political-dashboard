#!/usr/bin/env python3
"""Real GDP growth (quarterly, annualized) — BEA via FRED (keyless).

A191RL1Q225SBEA = real GDP, % change from preceding quarter, seasonally
adjusted annual rate. History to 1947, so the term-average comparison against
the prior administration's equivalent quarters comes from the same series.

Interpretation caveats carried on the card: estimates are revised twice after
the advance release, and 2025 quarters were whipsawed by tariff-driven import
swings (Q1 2025 negative, Q2–Q3 rebound)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series, quarter_month  # noqa: E402

SERIES = "A191RL1Q225SBEA"
TERM_START = "2025-03"    # Q1 2025 (stored by quarter-end month)
PREV_START = "2021-03"    # Q1 2021 (Biden)


def term_average(series, start, count=None):
    """Average value of quarters from `start` (inclusive), optionally capped at
    `count` quarters. series = [{date, value}] ascending."""
    vals = [p["value"] for p in series if p["date"] >= start]
    if count is not None:
        vals = vals[:count]
    return round(sum(vals) / len(vals), 1) if vals else None


def main():
    series = [{"date": quarter_month(d), "value": v} for d, v in fred_series(SERIES)]
    series.sort(key=lambda p: p["date"])
    latest = series[-1]

    n = len([p for p in series if p["date"] >= TERM_START])
    trump_avg = term_average(series, TERM_START)
    biden_avg = term_average(series, PREV_START, count=n)

    out = {
        "id": "real_gdp", "name": "Real GDP growth",
        "category": "Economy & Jobs", "value": latest["value"], "unit": "% (annualized)",
        "as_of": latest["date"], "direction": "up_is_good",
        "term_avg": trump_avg, "term_quarters": n,
        "source": {"name": "Bureau of Economic Analysis (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/A191RL1Q225SBEA"},
        "cadence": "Quarterly",
        "note": "Quarter-on-quarter growth of inflation-adjusted GDP, annualized. Estimates are "
                "revised; 2025 quarters were whipsawed by tariff-driven import swings.",
    }
    if biden_avg is not None:
        out["comparison"] = {"label": f"Biden, first {n} quarters (avg)", "value": biden_avg}
    publish(out, series=series)


if __name__ == "__main__":
    main()
