#!/usr/bin/env python3
"""Run every connector, then rebuild the static site. This is what the
scheduled job calls."""
import subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CONNECTORS = [
    "federal_register_eo.py", "treasury_debt.py", "bls_inflation.py",
    "bls_unemployment.py", "eia_gas.py", "census_trade.py",
]

def run(path):
    print(f"→ {path}")
    subprocess.run([sys.executable, os.path.join(HERE, path)], check=True)

for c in CONNECTORS:
    try:
        run(os.path.join("connectors", c))
    except subprocess.CalledProcessError as e:
        print(f"  ! {c} failed ({e}) — keeping last good data for this metric")

run("build.py")
print("done.")
