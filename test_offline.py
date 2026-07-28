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

print("== v2 expansion: pure-logic tests (no network) ==")


def raises_runtime(fn):
    try:
        fn(); return False
    except RuntimeError:
        return True


ok(common.quarter_month("2026-01-01") == "2026-03", "FRED quarter start -> quarter-end month")
ok(common.quarter_month("2025-10-01") == "2025-12", "Q4 maps to December")

import fred_groceries
yoy = fred_groceries.yoy_from_index([
    ("2024-09-01", 300.0), ("2024-10-01", 300.0), ("2024-11-01", 300.0),
    ("2025-09-01", 309.0), ("2025-11-01", 306.0),   # Oct 2025 missing (shutdown hole)
    ("2026-10-01", 320.0),                            # year-ago base missing
])
ok({p["date"]: p["value"] for p in yoy} == {"2025-09": 3.0, "2025-11": 2.0},
   "groceries YoY: computed where base exists; missing months drop out both ends")

import fred_gdp
gdp_series = [{"date": "2025-03", "value": -0.6}, {"date": "2025-06", "value": 3.8},
              {"date": "2025-09", "value": 4.4}]
ok(fred_gdp.term_average(gdp_series, "2025-03") == 2.5, "GDP term average")
ok(fred_gdp.term_average(gdp_series, "2025-03", count=2) == 1.6, "GDP capped-quarters average")

import treasury_interest
tot = treasury_interest.sum_fytd([
    {"record_date": "2026-06-30", "fytd_expense_amt": "900000000000"},
    {"record_date": "2026-06-30", "fytd_expense_amt": "200000000000"},
    {"record_date": "2026-06-30", "fytd_expense_amt": "-15500000000"},  # negative line summed too
])
ok(tot == [{"date": "2026-06", "value": 1084.5}], "interest: sums ALL lines incl. negatives")

import tariff_rate
rate = tariff_rate.compute_rate(
    [{"record_date": "2026-05-31", "current_month_gross_rcpt_amt": "24000000000"},
     {"record_date": "2026-06-30", "current_month_gross_rcpt_amt": "23000000000"}],  # no import obs yet
    [("2026-05-01", 317045.0)])
ok(rate == [{"date": "2026-05", "value": 7.57}], "tariff rate: duties/imports %, months present in both only")

import cdc_overdoses
od = cdc_overdoses.rows_to_series([
    {"year": "2026", "month": "February", "data_value": "67531", "predicted_value": "68641"},
    {"year": "2026", "month": "January", "data_value": "68669", "predicted_value": "69402"},
    {"year": "2026", "month": "Smarch", "data_value": "1", "predicted_value": "1"},   # junk month
])
ok([p["value"] for p in od] == [69402, 68641], "overdoses: predicted_value used, junk dropped, sorted")

import cms_medicaid
agg = cms_medicaid.aggregate(
    [{"reporting_period": "202603", "state_name": f"State{i}",
      "total_medicaid_and_chip_enrollment": "1000000", "final_report": "N"} for i in range(46)]
    + [{"reporting_period": "202603", "state_name": "State0",
        "total_medicaid_and_chip_enrollment": "1100000", "final_report": "Y"},     # final beats preliminary
       {"reporting_period": "202604", "state_name": "OnlyOne",
        "total_medicaid_and_chip_enrollment": "999", "final_report": "Y"}])         # <45 states -> dropped
ok(agg == [{"date": "2026-03", "value": 46100000}],
   "medicaid: final row wins, states summed, sparse month dropped")

import fjc_judges
_pairs = [("Donald J. Trump", datetime.date(2025, 6, 1)),
          ("Donald J. Trump", datetime.date(2017, 5, 1)),
          ("Joseph R. Biden", datetime.date(2021, 5, 1)),
          ("Barack Obama", datetime.date(2009, 5, 1))]
ok(fjc_judges.count_window(_pairs, "Trump", datetime.date(2017, 1, 20), 200) == 1,
   "judges: first-term window counts only its own confirmations")
ok(fjc_judges.count_window(_pairs, "Biden", datetime.date(2021, 1, 20), 200) == 1,
   "judges: Biden window")
ok(fjc_judges._parse_date("11/20/2025") == datetime.date(2025, 11, 20), "judges: M/D/YYYY dates parse")

import cdc_measles
_as_of, _ytd, _yr = cdc_measles.parse_page(
    "<p>As of June 4, 2026, 2,030 confirmed* measles cases were reported in the United States in 2026.</p>")
ok((_as_of, _ytd, _yr) == ("2026-06-04", 2030, 2026), "measles: page sentence anchor parses")
ok(raises_runtime(lambda: cdc_measles.parse_page("<p>totally different page</p>")),
   "measles: restructured page raises (safe-fail)")

import votehub_approval
_today = datetime.date(2026, 7, 28)
app, dis, n, as_of = votehub_approval.average_polls([
    {"subject": "Donald Trump", "pollster": "A", "end_date": "2026-07-25",
     "answers": [{"choice": "Approve", "pct": 40.0}, {"choice": "Disapprove", "pct": 56.0}]},
    {"subject": "Donald Trump", "pollster": "A", "end_date": "2026-07-20",   # older poll, same pollster
     "answers": [{"choice": "Approve", "pct": 44.0}, {"choice": "Disapprove", "pct": 52.0}]},
    {"subject": "Donald Trump", "pollster": "B", "end_date": "2026-07-24",
     "answers": [{"choice": "Approve", "pct": 42.0}, {"choice": "Disapprove", "pct": 54.0}]},
    {"subject": "Donald Trump", "pollster": "C", "end_date": "2026-07-18",
     "answers": [{"choice": "Approve", "pct": 38.0}, {"choice": "Disapprove", "pct": 58.0}]},
    {"subject": "Congress", "pollster": "D", "end_date": "2026-07-25",
     "answers": [{"choice": "Approve", "pct": 20.0}, {"choice": "Disapprove", "pct": 70.0}]},
], _today)
ok((app, dis, n, as_of) == (40.0, 56.0, 3, "2026-07-25"),
   "approval: latest-per-pollster, Trump-only, simple mean, as_of = newest poll")

import ice_removals
ok(ice_removals._cal_date("Oct", None, 2026) == "2025-10", "ICE removals: Oct in FY2026 -> Oct 2025")
ok(ice_removals._cal_date("Jun", None, 2026) == "2026-06", "ICE removals: Jun in FY2026 -> Jun 2026")

print("== stale_days override ==")
with tempfile.TemporaryDirectory() as td:
    common.DATA_DIR = td
    slow = {"id": "overdose_deaths", "name": "x", "category": "Health & Safety Net",
            "unit": "deaths", "direction": "up_is_bad", "cadence": "Monthly",
            "stale_days": 240, "source": {"name": "CDC", "url": "x"}, "note": "n"}
    common.publish(dict(slow), series=[{"date": "2026-02", "value": 68641}])
    saved = json.load(open(os.path.join(td, "overdose_deaths.json")))
    ok(saved["stale_after"] == "2026-10-26", "stale_days=240 overrides the 70-day monthly clock")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
