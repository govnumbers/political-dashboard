#!/usr/bin/env python3
"""Real wages — median usual weekly earnings, inflation-adjusted — BLS/CPS via
FRED (keyless).

LES1252881600Q = median usual weekly earnings of full-time wage and salary
workers, constant 1982-84 dollars, quarterly, history to 1979. The median
(rather than an average) is robust to the top of the distribution, which makes
it the honest "is the typical worker's pay beating inflation" measure.

Known permanent hole: Q4 2025 was never collected (the Oct–Nov 2025 shutdown
killed that quarter's survey). The gap is shown, never interpolated."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series, quarter_month  # noqa: E402

SERIES = "LES1252881600Q"
TERM_START = "2025-03"    # Q1 2025, stored by quarter-end month


def main():
    series = [{"date": quarter_month(d), "value": round(v, 0)} for d, v in fred_series(SERIES)]
    series.sort(key=lambda p: p["date"])
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)

    out = {
        "id": "real_wages", "name": "Real wages (median weekly earnings)",
        "category": "Economy & Jobs", "value": latest["value"], "unit": "$/wk (1982-84 $)",
        "as_of": latest["date"], "direction": "up_is_good",
        "source": {"name": "Bureau of Labor Statistics (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/LES1252881600Q"},
        "cadence": "Quarterly",
        "note": "Median usual weekly earnings, full-time workers, in constant (1982-84) dollars — "
                "pay adjusted for inflation. Q4 2025 is missing at the source (shutdown).",
    }
    if base is not None:
        out["baseline"] = {"label": "Q1 2025 (inauguration quarter)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
