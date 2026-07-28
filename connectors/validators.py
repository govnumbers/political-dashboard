#!/usr/bin/env python3
"""Per-metric sanity validation, shared by every connector.

Philosophy: bounds reject the IMPOSSIBLE, not the merely surprising. A value
outside these ranges (or a period-over-period jump larger than `max_jump`) is
almost certainly a bad read — a corrupted response, a units error (millions vs
billions), a sign flip, or a source outage returning garbage — not a real move.
So the ranges are deliberately wide: we would rather publish a real but shocking
number than silently drop a true value. When a check fails the connector keeps
last-good data and fails loudly (see common.publish / run_all.py).

`max_jump` is the largest plausible change between two consecutive stored
observations for that metric's cadence (day-over-day for debt, month-over-month
for CPI, etc.). It catches the classic failure where a source briefly returns a
stale or zero value and the delta explodes.
"""


class ValidationError(Exception):
    pass


# min / max = absolute plausible bounds for the published value.
# max_jump  = largest plausible |change| vs the previous stored observation.
BOUNDS = {
    # --- Cost of Living ---
    "inflation":         {"min": -5.0,   "max": 25.0,    "max_jump": 4.0,    "unit": "% YoY"},
    "grocery_prices":    {"min": -10.0,  "max": 30.0,    "max_jump": 5.0,    "unit": "% YoY (food at home)"},
    "gas_price":         {"min": 1.0,    "max": 12.0,    "max_jump": 1.5,    "unit": "$/gal wk-over-wk"},
    # --- Economy & Jobs ---
    "unemployment":      {"min": 1.0,    "max": 30.0,    "max_jump": 4.0,    "unit": "%"},
    "real_gdp":          {"min": -40.0,  "max": 45.0,    "max_jump": 40.0,   "unit": "% SAAR (COVID quarters hit ±33)"},
    "real_wages":        {"min": 250.0,  "max": 550.0,   "max_jump": 25.0,   "unit": "$/wk, 1982-84 dollars"},
    "federal_workforce": {"min": 1500.0, "max": 4000.0,  "max_jump": 400.0,  "unit": "thousand employees (Oct-2025 dropped 179k in one month)"},
    # --- Trade & Tariffs ---
    "tariff_revenue":    {"min": 0.0,    "max": 800.0,   "max_jump": 400.0,  "unit": "$B gross, fiscal-YTD (resets each Oct)"},
    "effective_tariff_rate": {"min": 0.0, "max": 40.0,   "max_jump": 10.0,   "unit": "% of goods imports"},
    "trade_deficit":     {"min": 10.0,   "max": 250.0,   "max_jump": 70.0,   "unit": "$B/mo"},
    # --- Public Finances ---
    "national_debt":     {"min": 3.0e13, "max": 8.0e13,  "max_jump": 1.2e12, "unit": "USD, day-over-day"},
    "budget_deficit":    {"min": 0.0,    "max": 3000.0,  "max_jump": 2200.0, "unit": "$B, fiscal-YTD (resets each Oct)"},
    "interest_on_debt":  {"min": 0.0,    "max": 3000.0,  "max_jump": 1800.0, "unit": "$B, fiscal-YTD (resets each Oct)"},
    # --- Immigration ---
    "border_encounters": {"min": 0.0,    "max": 500000.0,"max_jump": 250000.0,"unit": "encounters/mo"},
    "ice_removals":      {"min": 0.0,    "max": 1500000.0,"max_jump": 500000.0,"unit": "people, fiscal-YTD (resets each Oct; lumpy publication)"},
    "ice_detention":     {"min": 0.0,    "max": 150000.0,"max_jump": 50000.0,"unit": "ADP"},
    # --- Health & Safety Net ---
    "overdose_deaths":   {"min": 20000.0,"max": 200000.0,"max_jump": 15000.0,"unit": "deaths, trailing 12 months"},
    "measles_cases":     {"min": 0.0,    "max": 60000.0, "max_jump": 6000.0, "unit": "confirmed cases, YTD"},
    "medicaid_enrollment": {"min": 4.0e7,"max": 1.3e8,   "max_jump": 6.0e6,  "unit": "people"},
    "va_claims_backlog": {"min": 500.0,  "max": 1.0e6,   "max_jump": 200000.0,"unit": "claims >125 days"},
    # --- Executive Power & Governance ---
    "executive_orders":  {"min": 0.0,    "max": 3000.0,  "max_jump": 500.0,  "unit": "cumulative count"},
    "judges_confirmed":  {"min": 0.0,    "max": 600.0,   "max_jump": 60.0,   "unit": "cumulative count"},
    "approval_rating":   {"min": 15.0,   "max": 85.0,    "max_jump": 12.0,   "unit": "% approve (poll aggregate)"},
}


def check(metric_id, value, prev_value=None):
    """Validate a metric's latest value against its bounds and (if available)
    the previous stored observation. Raises ValidationError on failure.

    Metrics with no entry in BOUNDS are allowed through (a brand-new connector
    is better shipped un-bounded than blocked), but this is logged by the
    caller so we remember to add bounds.
    """
    b = BOUNDS.get(metric_id)
    if b is None:
        return  # no bounds defined yet — caller warns

    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{metric_id}: value {value!r} is not numeric")

    if v != v:  # NaN
        raise ValidationError(f"{metric_id}: value is NaN")

    if v < b["min"] or v > b["max"]:
        raise ValidationError(
            f"{metric_id}: value {v:,g} outside plausible bounds "
            f"[{b['min']:,g}, {b['max']:,g}] ({b['unit']}) — treating as a bad read"
        )

    if prev_value is not None:
        try:
            pv = float(prev_value)
        except (TypeError, ValueError):
            pv = None
        if pv is not None and abs(v - pv) > b["max_jump"]:
            raise ValidationError(
                f"{metric_id}: jump {abs(v - pv):,g} from {pv:,g} to {v:,g} exceeds "
                f"max plausible step {b['max_jump']:,g} ({b['unit']}) — treating as a bad read"
            )


def known_metrics():
    return set(BOUNDS)


if __name__ == "__main__":
    # smoke test
    check("inflation", 3.1, 2.9)
    for bad in [("inflation", 40, 3), ("inflation", 3.1, -2.0), ("national_debt", 0, 4e13)]:
        try:
            check(*bad)
            print("FAIL: should have raised for", bad)
        except ValidationError as e:
            print("ok, rejected:", e)
