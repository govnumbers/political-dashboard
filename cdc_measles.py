#!/usr/bin/env python3
"""Effective tariff rate, customs duties as a share of goods imports. COMPUTED
from two official series (the card states the formula; we do not claim any
academic "average tariff rate"):

  rate = monthly GROSS customs duties (Treasury MTS table 4, whole $)
         ÷ monthly goods imports, BOP basis (Census/BEA via FRED BOPGIMP, $M)
         × 100

Both inputs keyless. Gross (not net) duties in the numerator on purpose: 2026
court-ordered refunds make net negative in some months, which would produce a
meaningless negative "rate"; the tariff_revenue card carries the gross-vs-net
story. Imports lag duties by ~1 month, so the rate's as_of trails the tariff
card slightly, expected, not a bug."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, fred_series  # noqa: E402
from treasury_tariffs import fetch_customs_rows  # noqa: E402  (same keyless API)

IMPORTS_SERIES = "BOPGIMP"   # Imports of Goods: Balance of Payments Basis, $M, monthly
TERM_START = "2025-01"


def compute_rate(duty_rows, import_pairs):
    """duty_rows: mts_table_4 rows (whole dollars, current_month_gross_rcpt_amt).
    import_pairs: [(YYYY-MM-DD, millions)]. Returns [{date: YYYY-MM, value: %}]
    for months present in BOTH series."""
    imports_m = {d[:7]: v for d, v in import_pairs}
    out = []
    for row in duty_rows:
        ym = row["record_date"][:7]
        imp = imports_m.get(ym)
        if not imp:
            continue
        try:
            duties_m = float(row["current_month_gross_rcpt_amt"]) / 1e6
        except (TypeError, ValueError, KeyError):
            continue
        if imp > 0:
            out.append({"date": ym, "value": round(duties_m / imp * 100, 2)})
    out.sort(key=lambda p: p["date"])
    return out


def main():
    series = compute_rate(fetch_customs_rows(), fred_series(IMPORTS_SERIES))
    if not series:
        raise RuntimeError("computed zero effective-tariff-rate points")
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)

    out = {
        "id": "effective_tariff_rate", "name": "Effective tariff rate",
        "category": "Trade & Tariffs", "value": latest["value"], "unit": "%",
        "as_of": latest["date"], "direction": "neutral",
        "source": {"name": "Computed: Treasury MTS ÷ Census/BEA imports (via FRED)",
                   "url": "https://fred.stlouisfed.org/series/BOPGIMP"},
        "cadence": "Monthly",
        "note": "Gross customs duties collected as a share of goods imports that month, the "
                "average tariff actually paid at the border. Computed transparently from two "
                "official series; shifts in the import mix move it as well as policy.",
    }
    if base is not None:
        out["baseline"] = {"label": "At inauguration (Jan 2025)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
