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
    # --- Economy ---
    "inflation":         {"min": -5.0,   "max": 25.0,    "max_jump": 4.0,    "unit": "% YoY"},
    "unemployment":      {"min": 1.0,    "max": 30.0,    "max_jump": 4.0,    "unit": "%"},
    "gas_price":         {"min": 1.0,    "max": 12.0,    "max_jump": 1.5,    "unit": "$/gal wk-over-wk"},
    "trade_deficit":     {"min": 10.0,   "max": 250.0,   "max_jump": 70.0,   "unit": "$B/mo"},
    # --- Public Finances ---
    "national_debt":     {"min": 3.0e13, "max": 8.0e13,  "max_jump": 1.2e12, "unit": "USD, day-over-day"},
    "budget_deficit":    {"min": 0.0,    "max": 4000.0,  "max_jump": 900.0,  "unit": "$B, fiscal-YTD"},
    # --- Executive Power ---
    "executive_orders":  {"min": 0.0,    "max": 3000.0,  "max_jump": 500.0,  "unit": "cumulative count"},
    # --- Immigration ---
    "border_encounters": {"min": 0.0,    "max": 500000.0,"max_jump": 250000.0,"unit": "encounters/mo"},
    "ice_detention":     {"min": 0.0,    "max": 150000.0,"max_jump": 50000.0,"unit": "ADP"},
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
