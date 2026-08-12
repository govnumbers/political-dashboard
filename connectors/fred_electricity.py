#!/usr/bin/env python3
"""Electricity price (residential, US city average) — BLS via FRED (keyless).

APU000072610 = BLS average price, electricity per kWh, US city average (NSA —
average-price series aren't seasonally adjusted; the card says so). Stored in
dollars per kWh exactly as published (e.g. 0.185); display formats as cents.

v3 register #14 (Energy tab, locked 12 Aug 2026). The other half of the
home-energy bill next to gas — rising in the data-center-demand era. Same
keyless FRED CSV pipe as gas/groceries: zero new source risk."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series  # noqa: E402

SERIES = "APU000072610"
TERM_START = "2025-01"


def monthly_points(pairs):
    """[(YYYY-MM-DD, $/kWh)] -> [{date: YYYY-MM, value}] (native monthly)."""
    return [{"date": d[:7], "value": round(v, 3)} for d, v in pairs]


def main():
    series = monthly_points(fred_series(SERIES))
    if not series:
        raise RuntimeError("FRED returned no electricity price points")
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)

    out = {
        "id": "electricity_price", "name": "Electricity price (residential)",
        "category": "Energy", "value": latest["value"], "unit": "$/kWh",
        "as_of": latest["date"], "direction": "up_is_bad",
        "source": {"name": "Bureau of Labor Statistics (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/APU000072610"},
        "cadence": "Monthly",
        "note": "US city average residential price per kilowatt-hour (BLS average-price "
                "series, not seasonally adjusted). Rates are set by state regulators and "
                "utilities; the federal channels run through permitting and equipment costs.",
    }
    if base is not None:
        out["baseline"] = {"label": "At inauguration (Jan 2025)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
