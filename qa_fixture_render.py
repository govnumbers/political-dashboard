#!/usr/bin/env python3
"""Render the FULL v3 board (all 35 cards) from synthetic-but-plausible fixture
data files, in a throwaway copy of the repo — so the presentation layer for
metrics whose connectors haven't produced live data yet can be built, eyeballed
and browser-swept before delivery. Prints the temp path; pass --keep to leave
it on disk (default cleans up after asserting).

Not part of the deploy. The daily pipeline renders only from real data/."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def fixtures(D):
    def w(mid, extra, series=None, value=None, as_of="2026-07", cadence="Monthly",
          unit="", note="Fixture note. Second sentence."):
        out = {"id": mid, "name": mid, "category": "x", "value": value, "unit": unit,
               "as_of": as_of, "direction": "neutral", "cadence": cadence,
               "source": {"name": "Fixture", "url": "https://example.gov"},
               "note": note, "last_checked": "2026-08-12", "stale_after": "2026-12-01"}
        out.update(extra)
        if series:
            out["series"] = series
        json.dump(out, open(os.path.join(D, f"{mid}.json"), "w"))

    mo = lambda n, v0, step: [{"date": f"{2024 + (m + 6) // 12}-{(m + 6) % 12 + 1:02d}",
                               "value": round(v0 + i * step, 3)}
                              for i, m in enumerate(range(n))]
    w("electricity_price", {"baseline": {"label": "At inauguration (Jan 2025)", "value": 0.168}},
      mo(30, 0.16, 0.001), 0.185)
    w("crude_oil", {"baseline": {"label": "x", "value": 13.2},
                    "record": {"value": 13.6, "date": "2026-05"}}, mo(30, 13.0, 0.02), 13.58)
    w("renewable_share", {"baseline": {"label": "x", "value": 23.0}}, mo(30, 21.0, 0.1), 24.1)
    w("ice_composition", {"detail": {"convicted_criminal": 19329, "pending_criminal_charges": 15000,
                                     "other_immigration_violators": 31436, "total_detained": 65765}},
      [{"date": "2026-07", "value": 70.6}], 70.6, cadence="Biweekly")
    w("ice_custody_deaths", {"fy_counts": {str(fy): n for fy, n in
                                           [(2018, 12), (2019, 8), (2020, 21), (2021, 5), (2022, 3),
                                            (2023, 6), (2024, 9), (2025, 32), (2026, 23)]}},
      [{"date": "2025-10", "value": 23}], 23, cadence="As posted")
    w("refugee_admissions", {"ceiling": {"label": "FY2026 presidential ceiling", "value": 7500},
                             "south_africa": 6665}, [{"date": "2026-06", "value": 7730}], 7730)
    w("clemency", {"individuals_covered_approx": 1652,
                   "per_president_individuals": {"biden": 4245, "obama": 1927, "trump1": 237}},
      mo(18, 10, 8), 152, cadence="As granted")
    w("national_emergencies", {"since": "2025-01-20",
                               "prev_terms": {"biden": {"same_point": 5}, "trump1": {"same_point": 4},
                                              "obama": {"same_point": 3}}}, mo(18, 1, 0.5), 10,
      cadence="As signed")
    w("defense_outlays", {"comparison": {"label": "Same point last fiscal year", "value": 640.0}},
      mo(30, 60, 22), 700.5)
    w("foreign_aid", {"comparison": {"label": "Same point FY2025", "value": 52.1}},
      [{"date": f"{y}-09", "value": v} for y, v in
       [(2019, 55), (2021, 60), (2023, 70), (2025, 47.3)]] + [{"date": "2026-06", "value": 38.2}],
      38.2, cadence="Quarterly")
    w("war_powers", {"since": "2025-01-20",
                     "prev_terms": {"biden": {"same_point": 9}, "trump1": {"same_point": 11},
                                    "obama": {"same_point": 8}}}, mo(18, 2, 1), 19, cadence="As filed")
    w("military_deaths", {"per_operation": {"Operation Epic Fury": {"deaths": 14, "wounded": 417},
                                            "Overseas Operations": {"deaths": 4, "wounded": 279}},
                          "wounded_total": 696},
      [{"date": "2026-02", "value": 0}, {"date": "2026-03", "value": 13},
       {"date": "2026-07", "value": 18}], 18, cadence="Weekly")

    # enrich two live cards with the v3 static-import fields their connectors
    # now attach in production
    det_p = os.path.join(D, "ice_detention.json")
    if os.path.exists(det_p):
        det = json.load(open(det_p))
        det["annual_adp"] = {"values": {"2019": 50165, "2020": 33724, "2021": 19461,
                                        "2022": 22630, "2023": 28289, "2024": 37721}}
        json.dump(det, open(det_p, "w"))
    ap_p = os.path.join(D, "approval_rating.json")
    if os.path.exists(ap_p):
        ap = json.load(open(ap_p))
        g = json.load(open(os.path.join(os.path.dirname(D), "connectors", "static",
                                        "gallup_terms.json")))
        ap["gallup"] = {"term_quarter": 7,
                        "same_quarter": {p: g["quarterly"][p].get("7") for p in
                                         ("biden", "trump1", "obama")},
                        "quarterly": g["quarterly"], "inauguration": g["inauguration"]}
        json.dump(ap, open(ap_p, "w"))


def main():
    td = tempfile.mkdtemp(prefix="v3render-")
    dst = os.path.join(td, "repo")
    shutil.copytree(HERE, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "qa_shots"))
    fixtures(os.path.join(dst, "data"))
    r = subprocess.run([sys.executable, "build.py"], cwd=dst, capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit(1)
    html = open(os.path.join(dst, "site", "index.html")).read()
    n = html.count("<article")
    payloads = len(os.listdir(os.path.join(dst, "site", "d")))
    assert n == 35 and payloads == 35, (n, payloads)
    print(f"fixture board: {n} cards, {payloads} payloads → {dst}")
    if "--keep" not in sys.argv:
        shutil.rmtree(td)
        print("(cleaned up; pass --keep to inspect)")
    return dst


if __name__ == "__main__":
    main()
