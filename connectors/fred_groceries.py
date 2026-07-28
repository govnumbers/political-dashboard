#!/usr/bin/env python3
"""Grocery prices (CPI food at home, year over year) — BLS via FRED (keyless).

CUSR0000SAF11 = CPI-U "food at home" (the grocery-store basket), seasonally
adjusted index. We compute the year-over-year % change per month, which is the
standard way this is quoted. Labelled SA on the card; the NSA variant
(CUUR0000SAF11) is what BLS headlines quote — differences are small and we say
which one we use.

Known permanent hole: BLS never published October 2025 CPI (government
shutdown). fred_series() skips the missing observation, and the YoY calc
naturally skips any month whose year-ago base is absent — gaps are shown,
never interpolated."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series  # noqa: E402

SERIES = "CUSR0000SAF11"
TERM_START = "2025-01"


def yoy_from_index(pairs):
    """pairs: [(YYYY-MM-DD, index_value)]. Returns [{date: YYYY-MM, value: yoy%}]
    for every month whose year-ago index exists (missing months drop out on
    both ends — the Oct-2025 hole removes Oct-2025 AND Oct-2026 YoY)."""
    idx = {d[:7]: v for d, v in pairs}
    out = []
    for ym in sorted(idx):
        y, m = int(ym[:4]), ym[5:7]
        base = idx.get(f"{y - 1}-{m}")
        if base:
            out.append({"date": ym, "value": round((idx[ym] - base) / base * 100, 1)})
    return out


def main():
    series = yoy_from_index(fred_series(SERIES))
    if not series:
        raise RuntimeError("computed zero grocery YoY points")
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)

    out = {
        "id": "grocery_prices", "name": "Grocery prices (food at home, YoY)",
        "category": "Cost of Living", "value": latest["value"], "unit": "%",
        "as_of": latest["date"], "direction": "up_is_bad",
        "source": {"name": "Bureau of Labor Statistics (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/CUSR0000SAF11"},
        "cadence": "Monthly",
        "note": "Grocery-store (food-at-home) prices vs a year earlier, seasonally adjusted. "
                "Oct 2025 is missing at the source (never published due to the government shutdown).",
    }
    if base is not None:
        out["baseline"] = {"label": "At inauguration (Jan 2025)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
