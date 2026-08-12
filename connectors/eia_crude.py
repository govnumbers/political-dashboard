#!/usr/bin/env python3
"""US crude oil production — EIA (keyless), monthly, history to 1920.

v3 register #15 (Energy tab). "Drill, baby, drill" is signature policy; this
is the official barrel count. Reads favourable (records) — included per the
completeness principle.

SOURCE MECHANICS: EIA's open-data API requires a registration key (rejected —
the board is zero-key, same call as the v1 gas decision), and the dnav XLS
download is the legacy .xls format our stack can't read without a new
dependency. The keyless route is dnav's HTML history page for the series
(`LeafHandler.ashx?n=PET&s=MCRFPUS2&f=M`) — a plain year-by-month table that
has been stable for many years. Parsed with a layout-tolerant regex over the
table rows; anything implausible dies on the validators (loud-fail), and the
creator-download fallback stands if EIA ever blocks the runner.

Units: source reports thousand barrels/day; stored as MILLION barrels/day
(13,451 -> 13.451) to match how the number is quoted everywhere."""
import os
import re
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, UA  # noqa: E402

URL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=MCRFPUS2&f=M"
SERIES_PAGE = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=MCRFPUS2&f=M"
TERM_START = "2025-01"


def parse_dnav_monthly(html):
    """dnav history page -> [{date: YYYY-MM, value: million b/d}] ascending.
    Layout: one <tr> per year — a year cell (e.g. >2025<) followed by up to 12
    value cells Jan..Dec. Tolerates blank cells (future months), thousands
    separators, and decade gaps; ignores everything outside table rows."""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if not cells or not re.fullmatch(r"(19|20)\d{2}", cells[0]):
            continue
        year = int(cells[0])
        for mi, cell in enumerate(cells[1:13], start=1):
            v = cell.replace(",", "")
            if re.fullmatch(r"\d+(\.\d+)?", v):
                out.append({"date": f"{year}-{mi:02d}",
                            "value": round(float(v) / 1000.0, 3)})
    return sorted(out, key=lambda p: p["date"])


def main():
    r = requests.get(URL, headers=UA, timeout=90)
    r.raise_for_status()
    series = parse_dnav_monthly(r.text)
    if len(series) < 100:
        raise RuntimeError(f"dnav crude parse produced only {len(series)} points — layout changed?")
    latest = series[-1]
    base = next((p["value"] for p in series if p["date"] == TERM_START), None)
    record = max(series, key=lambda p: p["value"])

    out = {
        "id": "crude_oil", "name": "US crude oil production",
        "category": "Energy", "value": latest["value"], "unit": "M b/d",
        "as_of": latest["date"], "direction": "neutral",
        "record": {"value": record["value"], "date": record["date"]},
        "source": {"name": "U.S. Energy Information Administration",
                   "url": "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=MCRFPUS2&f=M"},
        "cadence": "Monthly",
        "note": "US field production of crude oil, million barrels per day (EIA monthly, "
                "history to 1920). Production responds to prices and shale economics with "
                "multi-year lags; records were also being set under the prior administration.",
    }
    if base is not None:
        out["baseline"] = {"label": "At inauguration (Jan 2025)", "value": base}
    publish(out, series=series)


if __name__ == "__main__":
    main()
