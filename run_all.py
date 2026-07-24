#!/usr/bin/env python3
"""Run every connector, then rebuild the static site.

Reliability contract (see project doc 00 — Reliability hardening):
  • UPTIME: a failing connector never blocks the others and never blocks the
    rebuild — the site always redeploys with last-good data.
  • VISIBILITY: if ANY connector fails (network error, bad data rejected by the
    validators, etc.) we exit non-zero AFTER building, so the GitHub Actions run
    goes red and GitHub emails the repo owner. A green run means everything
    refreshed cleanly; a red run means "look at me" while the site stays up.
"""
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CONNECTORS = [
    "federal_register_eo.py",
    "treasury_debt.py",
    "treasury_deficit.py",
    "bls_inflation.py",
    "bls_unemployment.py",
    "eia_gas.py",
    "census_trade.py",
    "cbp_border.py",
    "ice_detention.py",
]


def run(path):
    print(f"→ {path}", flush=True)
    subprocess.run([sys.executable, os.path.join(HERE, path)], check=True)


failures = []
for c in CONNECTORS:
    try:
        run(os.path.join("connectors", c))
    except subprocess.CalledProcessError as e:
        failures.append(c)
        print(f"  ! {c} FAILED ({e}) — keeping last-good data for this metric", flush=True)

# Always rebuild so the site redeploys with whatever data we have (last-good
# for any connector that failed).
run("build.py")

if failures:
    print(f"\n✗ {len(failures)} connector(s) failed: {', '.join(failures)}", flush=True)
    print("  Site rebuilt with last-good data; failing this run so it is visible.", flush=True)
    sys.exit(1)

print("\n✓ all connectors succeeded.")
