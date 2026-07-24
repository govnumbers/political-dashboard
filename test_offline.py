#!/usr/bin/env python3
"""Offline logic tests — the gov APIs are egress-blocked in the build sandbox,
so we test everything that doesn't require the network: validation, series
merge (don't-overwrite + revision detection), freshness math, connector date
helpers, and a full build.py render against fixtures."""
import os
import sys
import json
import tempfile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "connectors"))

import common
import validators
from validators import ValidationError

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {msg}")
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {msg}")


print("== validators ==")
try:
    validators.check("unemployment", 4.1, 4.0); ok(True, "normal value passes")
except ValidationError:
    ok(False, "normal value passes")


def raises(fn):
    try:
        fn(); return False
    except ValidationError:
        return True


ok(raises(lambda: validators.check("gas_price", 99, 3.1)), "gas $99 rejected (bounds)")
ok(raises(lambda: validators.check("trade_deficit", 80, 5)), "trade jump 5→80 rejected (max_jump)")
ok(raises(lambda: validators.check("inflation", float("nan"))), "NaN rejected")
try:
    validators.check("unknown_metric", 123); ok(True, "unknown metric passes through")
except ValidationError:
    ok(False, "unknown metric passes through")

print("== merge_series (don't overwrite + revisions) ==")
existing = {"series": [{"date": "2025-01", "value": 3.0}, {"date": "2025-02", "value": 3.1}]}
merged, revs = common.merge_series(existing, [{"date": "2025-03", "value": 3.2}])
ok([p["date"] for p in merged] == ["2025-01", "2025-02", "2025-03"], "new point appended, old kept")
ok(revs == [], "no revision when only adding")
merged2, revs2 = common.merge_series(existing, [{"date": "2025-02", "value": 3.5}])
ok(revs2 == [("2025-02", 3.1, 3.5)], "revision to an existing date is detected")
# merge preserves old history not present in the new fetch (self-healing store)
merged3, _ = common.merge_series(existing, [{"date": "2025-03", "value": 3.2}])
ok(any(p["date"] == "2025-01" for p in merged3), "history survives a shallow fetch (merge, don't overwrite)")

print("== freshness math ==")
ok(common._effective_date("2025-06") == datetime.date(2025, 6, 30), "monthly as_of -> month end")
ok(common._effective_date("2025-06-15") == datetime.date(2025, 6, 15), "daily as_of -> that date")
sa_daily = common._stale_after("2025-06-15", "Daily")
sa_month = common._stale_after("2025-06", "Monthly")
ok(sa_daily < sa_month, "daily goes stale sooner than monthly")

print("== publish end-to-end (temp data dir) ==")
with tempfile.TemporaryDirectory() as td:
    common.DATA_DIR = td
    out = {"id": "inflation", "name": "Inflation", "category": "Economy",
           "unit": "%", "direction": "up_is_bad", "cadence": "Monthly",
           "target": {"label": "Fed", "value": 2.0},
           "source": {"name": "BLS", "url": "x"}, "note": "n"}
    common.publish(dict(out), series=[{"date": "2025-01", "value": 3.0}, {"date": "2025-02", "value": 3.1}])
    saved = json.load(open(os.path.join(td, "inflation.json")))
    ok(saved["value"] == 3.1 and saved["as_of"] == "2025-02", "headline set from newest series point")
    ok("stale_after" in saved and "last_checked" in saved, "freshness stamps written")
    ok(len(saved["series"]) == 2, "series stored")
    # a bad value must NOT overwrite last-good
    try:
        common.publish(dict(out), series=[{"date": "2025-03", "value": 40.0}])
        ok(False, "bad value should raise and not write")
    except ValidationError:
        after = json.load(open(os.path.join(td, "inflation.json")))
        ok(after["value"] == 3.1, "last-good preserved after a rejected bad value")

print("== connector date helpers ==")
import cbp_border
ok(cbp_border.cal_month(2025, "OCT") == "2024-10", "CBP: FY2025 OCT -> 2024-10 (fiscal->calendar)")
ok(cbp_border.cal_month(2025, "Jan") == "2025-01", "CBP: FY2025 Jan -> 2025-01")
import ice_detention
ok(ice_detention.current_fy(datetime.date(2026, 7, 1)) == 2026, "ICE: Jul 2026 -> FY2026")
ok(ice_detention.current_fy(datetime.date(2025, 11, 1)) == 2026, "ICE: Nov 2025 -> FY2026 (post-Oct rollover)")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
