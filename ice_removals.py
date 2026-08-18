#!/usr/bin/env python3
"""Southwest land border encounters (monthly), Customs and Border Protection.

Customs and Border Protection has no API and republishes a new "Southwest Land Border Encounters" CSV each
month (a single file spanning ~4 fiscal years, e.g. "FY23–FY26 (FYTD) … June").
This connector scrapes the official landing page for the newest such CSV,
downloads it, and sums to monthly totals. One file carries deep history, so the
merged series in data/ preserves it. Fully automated: each run picks up whatever
the newest monthly file is, no manual step.

Verified against the real June-2026 file. Real-file gotchas handled here:
  • Two month columns, "Month Grouping" (FYTD/Remaining) and "Month (abbv)" (the
    actual month). We use "Month (abbv)"; naively matching "month" grabs the wrong one.
  • "Encounter Count" vs "Encounter Type", "count" is a substring of "enCOUNTer",
    so we match the full "encounter count", never bare "count".
  • Rows are tagged FYTD (elapsed) or "Remaining" (not-yet-happened months); we
    keep only FYTD so future months don't appear as zero.
  • Fiscal Year cells look like "2026 (FYTD)" → digits stripped to 2026.
  • The file is Southwest-only, so there is NO region column and no filtering.

Framing note: this number is currently DOWN sharply (favourable-to-Trump); it is
included for completeness. direction is 'neutral'; the Title 42→Title 8 shift
(May 2023) is noted on the card. Counts events, not unique people."""
import os
import re
import sys
import csv
import io
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, load_existing  # noqa: E402

LANDING = "https://www.cbp.gov/document/stats/southwest-land-border-encounters"
BASE = "https://www.cbp.gov"
# newest CSV: "sboencounters…fy23…fy26…jun.csv", hyphens optional (Customs and Border Protection has used both)
CSV_RE = re.compile(r'href=["\']([^"\']*sbo-?encounters[^"\']*fy\d\d[^"\']*\.csv)["\']', re.I)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
UA = {"User-Agent": "govnumbers-dashboard/1.0 (+https://political-dashboard-323.pages.dev)"}


def csv_urls():
    """All Southwest-encounters CSV links on the landing page, newest first,
    absolute. [0] is the current monthly file; the rest are older/archived
    files used by the one-time history backfill."""
    r = requests.get(LANDING, headers=UA, timeout=45)
    r.raise_for_status()
    matches = CSV_RE.findall(r.text)          # document order; Customs and Border Protection lists newest month first
    seen = set()
    ordered = [m for m in matches if not (m in seen or seen.add(m))]
    if not ordered:
        raise RuntimeError("no Southwest-encounters CSV link found on Customs and Border Protection landing page")
    return [u if u.startswith("http") else BASE + u for u in ordered]


def newest_csv_url():
    return csv_urls()[0]


def needs_archive(series_dates):
    """True while the stored series has the known holes the archive can fill:
    months before Oct 2022 (Biden's first 21 months) or the Jul–Sep months of
    closed fiscal years that Customs and Border Protection's current file omits."""
    have = set(series_dates)
    if not have:
        return True
    if min(have) > "2021-02":
        return True
    latest_year = int(max(have)[:4])
    for y in range(2021, latest_year):
        for m in ("07", "08", "09"):
            if f"{y}-{m}" not in have:
                return True
    return False


def cal_month(fy, mon_abbr):
    """(fiscal year, calendar-month abbr) -> 'YYYY-MM'. FY Y = Oct(Y-1)..Sep(Y)."""
    m = MONTHS[mon_abbr.strip().lower()[:3]]
    return f"{fy - 1 if m >= 10 else fy}-{m:02d}"


def current_fiscal_year(today=None):
    today = today or datetime.date.today()
    return today.year + (1 if today.month >= 10 else 0)


def parse_csv(text, current_fy=None):
    rows = list(csv.reader(io.StringIO(text)))

    def cols(cells):
        low = [str(c).strip().lower() for c in cells]

        def col(*names):
            for i, h in enumerate(low):
                if any(n in h for n in names):
                    return i
            return None
        # month: the "(abbv)" one, NOT "Month Grouping"; count: full "encounter count"
        return (col("fiscal year", "fiscal yr"), col("month (abbv)", "abbv"),
                col("encounter count"), col("month grouping", "grouping"))

    header_idx = fy_i = mon_i = cnt_i = grp_i = None
    for i, row in enumerate(rows[:15]):
        fy_i, mon_i, cnt_i, grp_i = cols(row)
        if None not in (fy_i, mon_i, cnt_i):
            header_idx = i
            break
    if header_idx is None:
        raise RuntimeError(f"could not find header row in Customs and Border Protection CSV; first rows: {rows[:3]}")

    totals = {}
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= max(fy_i, mon_i, cnt_i):
            continue
        try:
            fy = int(re.sub(r"\D", "", row[fy_i]))          # "2026 (FYTD)" -> 2026
            ym = cal_month(fy, row[mon_i])
            cnt = int(float(re.sub(r"[^\d.]", "", row[cnt_i]) or 0))
        except (ValueError, KeyError):
            continue
        grp = row[grp_i].strip().lower() if (grp_i is not None and grp_i < len(row)) else ""
        if grp not in ("fytd", ""):
            # 'Remaining' means "past the current FY's progress". For the CURRENT
            # fiscal year those months haven't happened, skip, so the future
            # never shows as zero. For a CLOSED fiscal year the same tag sits on
            # months that DID happen (Jul–Sep, beyond the current year's elapsed
            # window), keep them when a real count is present. This is what
            # fills the Jul–Sep holes without any archive file.
            if not (current_fy is not None and fy < current_fy and cnt > 0):
                continue
        totals[ym] = totals.get(ym, 0) + cnt
    return totals


def main():
    cur_fy = current_fiscal_year()
    urls = csv_urls()
    r = requests.get(urls[0], headers=UA, timeout=60)
    r.raise_for_status()
    totals = parse_csv(r.text, current_fy=cur_fy)
    if not totals:
        raise RuntimeError("parsed zero monthly totals from Customs and Border Protection CSV")

    # --- one-time archive backfill (phase 7): older files on the same landing
    # page carry the months the current file omits (pre-Oct-2022 and closed-FY
    # Jul–Sep). Attempted at most every 30 days while holes remain; the newest
    # file's numbers always win on overlap; merge-don't-overwrite + revision
    # logging in common.py guard the store. Failure only skips the enhancement.
    existing = load_existing("border_encounters")
    stored_dates = [p["date"] for p in (existing or {}).get("series", [])]
    last_try = (existing or {}).get("archive_checked", "")
    cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    archive_checked = None
    if needs_archive(set(stored_dates) | set(totals)) and last_try < cutoff:
        for u in urls[1:3]:
            try:
                r2 = requests.get(u, headers=UA, timeout=60)
                r2.raise_for_status()
                older = parse_csv(r2.text, current_fy=cur_fy)
                added = {ym: v for ym, v in older.items() if ym not in totals}
                totals.update(added)
                print(f"  ✓ border_encounters: archive file added {len(added)} months ({u.rsplit('/', 1)[-1]})")
            except Exception as e:                                # noqa: BLE001
                print(f"  ! border_encounters: archive fetch failed ({e}), will retry in 30 days")
        archive_checked = datetime.date.today().isoformat()

    series = [{"date": ym, "value": totals[ym]} for ym in sorted(totals)]

    latest = series[-1]
    yoy_key = f"{int(latest['date'][:4]) - 1}{latest['date'][4:]}"   # same month, prior year
    yoy = next((p["value"] for p in series if p["date"] == yoy_key), None)
    out = {
        "id": "border_encounters", "name": "Southwest border encounters",
        "category": "Immigration", "value": latest["value"], "unit": "per month", "as_of": latest["date"],
        "direction": "neutral",
        "source": {"name": "U.S. Customs and Border Protection", "url": LANDING},
        "cadence": "Monthly",
        "note": "Monthly Southwest land border encounters. Counts events, not unique people; "
                "composition shifts at the May 2023 Title 42 → Title 8 change.",
    }
    if yoy is not None:
        out["comparison"] = {"label": "Same month, prior year", "value": yoy}

    # --- v3: verified Office of Homeland Security Statistics closed-history backfill (Oct 2013 – Sep 2022) ---
    # From DHS Office of Homeland Security Statistics's final (discontinued Jan 2025) monthly tables, parsed
    # against the real workbook the creator hand-downloaded; definition match
    # PROVEN on the 24-month overlap with Customs and Border Protection's live series (agrees to Office of Homeland Security Statistics's
    # rounding everywhere, provenance + verification inside the static file).
    # Only pre-Oct-2022 months ship, so this can never touch the live series.
    # Enhancement-only: a problem here never blocks the live metric.
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "static", "border_ohss_backfill.json")) as f:
            bf = _json.load(f)
        have = set(stored_dates) | {p["date"] for p in series}
        add = [p for p in bf["series"] if p["date"] < "2022-10" and p["date"] not in have]
        if add:
            series = sorted(add + series, key=lambda p: p["date"])
            print(f"  ✓ border: Office of Homeland Security Statistics backfill added {len(add)} closed-history months "
                  f"({add[0]['date']} → {add[-1]['date']})")
    except Exception as e:  # noqa: BLE001
        print(f"  ! border: Office of Homeland Security Statistics backfill skipped this run ({e})")
    if archive_checked:
        out["archive_checked"] = archive_checked
    elif existing and existing.get("archive_checked"):
        out["archive_checked"] = existing["archive_checked"]
    publish(out, series=series)


if __name__ == "__main__":
    main()
