#!/usr/bin/env python3
"""Federal civilian employment, Bureau of Labor Statistics Current Employment Statistics via FRED
(keyless).

CES9091000001 = all federal government employees, thousands, seasonally
adjusted, monthly, history to 1939, the official monthly count from the jobs
report. Includes the ~600k self-funded Postal Service (the ex-Postal variant
is CES9091100001 if a cleaner signal is ever preferred; the card notes the
inclusion).

Measurement caveats carried on the card: deferred-resignation employees were
counted as employed while still being paid (which delayed the visible drop
until Oct 2025), and courts have reversed some separations."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series  # noqa: E402

SERIES = "CES9091000001"
TERM_START = "2025-01"


def main():
    series = [{"date": d[:7], "value": round(v, 1)} for d, v in fred_series(SERIES)]
    series.sort(key=lambda p: p["date"])
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)

    out = {
        "id": "federal_workforce", "name": "Federal workforce (civilian employment)",
        "category": "Economy & Jobs", "value": latest["value"], "unit": "thousand employees",
        "as_of": latest["date"], "direction": "neutral",
        "source": {"name": "Bureau of Labor Statistics (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/CES9091000001"},
        "cadence": "Monthly",
        "note": "All federal civilian employees incl. the Postal Service, from the monthly jobs "
                "report. Staff on paid deferred resignation counted as employed until they left "
                "payrolls (visible as the Oct 2025 drop).",
    }
    if base is not None:
        out["baseline"] = {"label": "At inauguration (Jan 2025)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
