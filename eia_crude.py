#!/usr/bin/env python3
"""CPI-U index level, the deflator for real-price views. Bureau of Labor Statistics via FRED (keyless).

CPIAUCSL = Consumer Price Index for All Urban Consumers, US city average, all items,
seasonally adjusted (1982-84 = 100). This is NOT a card: it is a support series that
build.py uses to convert nominal gas and electricity prices into real (inflation-
adjusted) prices. Same keyless FRED CSV pipe as gas/electricity, so zero new source risk.

On success it overwrites data/cpi_index.json with the full monthly history; if the fetch
fails or looks wrong it raises, run_all keeps the last-good file and the run goes red."""
import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import fred_series  # noqa: E402

SERIES = "CPIAUCSL"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cpi_index.json")


def main():
    pairs = fred_series(SERIES)
    series = [{"date": d[:7], "value": round(v, 3)} for d, v in pairs]
    if len(series) < 300 or series[-1]["value"] < 250:
        raise RuntimeError(f"CPI fetch looks wrong ({len(series)} pts, "
                           f"latest {series[-1] if series else None})")
    out = {
        "id": "cpi_index", "name": "CPI-U index (deflator)", "category": "",
        "source": {"name": "Bureau of Labor Statistics (CPI-U, US city average, all items)",
                   "url": "https://fred.stlouisfed.org/series/CPIAUCSL"},
        "cadence": "Monthly", "as_of": series[-1]["date"],
        "last_checked": datetime.date.today().isoformat(),
        "note": "Consumer Price Index for All Urban Consumers (1982-84=100). "
                "Deflator for real-price views only; not shown as its own card.",
        "series": series,
    }
    json.dump(out, open(OUT, "w"))
    print(f"  cpi_index: {len(series)} monthly points, latest {series[-1]['date']} = {series[-1]['value']}")


if __name__ == "__main__":
    main()
