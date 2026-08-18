#!/usr/bin/env python3
"""US military deaths, current named operations, Defense Casualty Analysis System (DMDC), keyless JSON.

v3 register #35 (War & Defense tab). UN-GATED 12 Aug 2026: the creator's
DevTools capture (the proven VoteHub technique) pinned Defense Casualty Analysis System's internal REST
API, and the endpoints answer a plain GET with no cookies or keys, verified
same day from outside a browser:

    /dcas/api/report/wia/casualtySummary/category/totDeath/{op}   (headline)
    /dcas/api/report/wia/casualtySummary/category/totWIA/{op}     (context)
    /dcas/api/report/casualtySummary/monthly/{op}                 (series)

Every response carries apiStatusCode ("SUCCESS" required) and an
extractionDate, Defense Casualty Analysis System's own data date, which becomes as_of (honest
data-dating, not run-dating).

OPERATIONS: Defense Casualty Analysis System split the 2026 Iran conflict's casualties across TWO named
operations in July 2026, "Operation Epic Fury" (OEFU) and a new "Overseas
Operations" (OO) category (the split moved 4 deaths; charted as a definition
change at the build layer). We fetch both and publish the combined total,
with per-operation detail stored alongside. Counts only, never names.

Monthly rows look like {"month_Year": "MARCH 2026", "tot_kia": "7",
"tot_acc": "6", "tot_total": "13", "tot_wia": "342"} plus a GRAND TOTAL row
(skipped by the month parser). kia = hostile, acc = non-hostile; both stored
for the hostile/non-hostile context split.

Legacy context: the DoD's public casualty PDF froze Jan 30 2025 (watch list,
doc 04), this API is the only current official channel."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

BASE = "https://dcas.dmdc.osd.mil/dcas/api/report"
OPS = {"oefu": "Operation Epic Fury", "oo": "Overseas Operations"}
PAGE = "https://dcas.dmdc.osd.mil/dcas/conflictCasualties"
MONTHS = {m.upper(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def _get_json(path):
    r = requests.get(f"{BASE}/{path}", headers=dict(UA, Accept="application/json"), timeout=60)
    r.raise_for_status()
    js = r.json()
    if js.get("apiStatusCode") != "SUCCESS":
        raise RuntimeError(f"Defense Casualty Analysis System {path}: apiStatusCode={js.get('apiStatusCode')!r}")
    return js["data"]


def table_total(data, field="total"):
    """First tableData row's `field` as int (the category-summary endpoints
    return exactly one row)."""
    rows = data.get("tableData") or []
    if not rows:
        raise RuntimeError("Defense Casualty Analysis System: empty tableData")
    return int(float(rows[0][field]))


def parse_extraction_date(data):
    """'August 11, 2026' -> '2026-08-11' (falls back to today on surprises , 
    the run date is then honest as a checked-on date)."""
    s = (data.get("extractionDate") or "").strip()
    try:
        return datetime.datetime.strptime(s, "%B %d, %Y").date().isoformat()
    except ValueError:
        return datetime.date.today().isoformat()


def monthly_points(data):
    """monthly endpoint tableData -> ([{date, deaths, hostile, nonhostile}],)
    ascending; GRAND TOTAL / unparseable rows skipped."""
    out = []
    for row in data.get("tableData") or []:
        my = str(row.get("month_Year") or "").strip().upper()
        parts = my.split()
        if len(parts) != 2 or parts[0] not in MONTHS or not parts[1].isdigit():
            continue  # GRAND TOTAL etc.
        ym = f"{int(parts[1])}-{MONTHS[parts[0]]:02d}"
        def _i(key):
            try:
                return int(float(row.get(key) or 0))
            except (TypeError, ValueError):
                return 0
        out.append({"date": ym, "deaths": _i("tot_total"),
                    "hostile": _i("tot_kia"), "nonhostile": _i("tot_acc")})
    return sorted(out, key=lambda p: p["date"])


def cumulative_series(per_op_months):
    """{op: [monthly dicts]} -> combined cumulative [{date, value}] across ops
    (a month present in any op counts; absent ops contribute 0 that month)."""
    by_month = {}
    for months in per_op_months.values():
        for p in months:
            by_month[p["date"]] = by_month.get(p["date"], 0) + p["deaths"]
    out, cum = [], 0
    for ym in sorted(by_month):
        cum += by_month[ym]
        out.append({"date": ym, "value": cum})
    return out


def main():
    deaths, wia, monthly, as_ofs = {}, {}, {}, []
    for op in OPS:
        d = _get_json(f"wia/casualtySummary/category/totDeath/{op}")
        deaths[op] = table_total(d)
        as_ofs.append(parse_extraction_date(d))
        try:
            wia[op] = table_total(_get_json(f"wia/casualtySummary/category/totWIA/{op}"))
        except Exception as e:  # noqa: BLE001, context only, never blocks deaths
            print(f"  ! military_deaths: WIA fetch skipped for {op} ({e})")
        try:
            monthly[op] = monthly_points(_get_json(f"casualtySummary/monthly/{op}"))
        except Exception as e:  # noqa: BLE001, series enhancement, headline stands
            print(f"  ! military_deaths: monthly series skipped for {op} ({e})")

    total = sum(deaths.values())
    series = cumulative_series(monthly) if monthly else None
    as_of = max(as_ofs) if as_ofs else datetime.date.today().isoformat()

    # cross-check: cumulative series end should equal the summed headline when
    # every operation's monthly table fetched (a Defense Casualty Analysis System-internal consistency test,
    # same philosophy as the ICE dual-split check, mismatch = loud fail)
    if series and len(monthly) == len(OPS) and series[-1]["value"] != total:
        raise RuntimeError(f"Defense Casualty Analysis System consistency check failed: monthly cumulative "
                           f"{series[-1]['value']} != summary total {total}")

    out = {
        "id": "military_deaths", "name": "US military deaths (current operations)",
        "category": "War & Defense", "value": total, "unit": "deaths",
        "as_of": as_of, "direction": "up_is_bad",
        "per_operation": {OPS[op]: {"deaths": deaths.get(op), "wounded": wia.get(op)}
                          for op in OPS},
        "wounded_total": sum(wia.values()) if wia else None,
        "source": {"name": "Defense Casualty Analysis System (DMDC)", "url": PAGE},
        "cadence": "Weekly", "stale_days": 30,
        "note": "US military deaths in the current named operations (Operation Epic Fury "
                "+ Overseas Operations, Defense Casualty Analysis System's own July 2026 split of the Iran conflict), "
                "hostile and non-hostile, as extracted by Defense Casualty Analysis System on its stated date. "
                "Counts cover service members, not civilians or contractors.",
    }
    publish(out, series=series)


if __name__ == "__main__":
    main()
