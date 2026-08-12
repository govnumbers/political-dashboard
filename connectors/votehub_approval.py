#!/usr/bin/env python3
"""Presidential approval — VoteHub open poll API (keyless, CC-BY-4.0).

THE BOARD'S ONE OPINION-DERIVED METRIC (locked in project doc 02): labelled as
a poll aggregate, not a government statistic. FiveThirtyEight died in Mar 2025;
VoteHub is the remaining aggregator that is keyless + openly licensed +
transparent about which polls it carries. Fallback if it folds: Gallup, manual.

METHOD (stated on the card): simple unweighted mean of national approval polls
ending in the last 14 days (widened to 30 if fewer than three), one value per
pollster (latest poll wins) so prolific pollsters don't dominate.

Verified structure (Jul 2026): GET api.votehub.com/polls?poll_type=approval ->
bare JSON array (no pagination metadata), OLDEST FIRST, mixed subjects
(Trump, Congress, ...): [{subject: "Donald Trump", pollster,
end_date: "YYYY-MM-DD", answers: [{choice: "Approve", pct: 47.0}, ...]}]

FIRST-RUN FIX (28 Jul 2026): because the array is oldest-first, a small
`limit` truncates away the RECENT polls (limit=500 topped out at Jun 2026).
So: request effectively-everything, filter client-side, and hard-fail if the
newest usable poll is over 45 days old rather than publish a stale number."""
import os
import sys
import datetime
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import publish, load_existing, UA  # noqa: E402

API = "https://api.votehub.com/polls"

# KNOWN-OUTAGE HANDLING (4 Aug 2026, logged in docs 02/04): VoteHub's public
# API stopped ingesting approval/favorability polls after 2026-06-29 while its
# election-race types stay current — verified across every parameter lane,
# including the site chart's own `in_averages_only=true` bucket (the votehub.com
# "live" average line keeps recomputing daily on those stale polls). Rather
# than run red every day for a diagnosed, disclosed condition:
#   • the connector still queries the API EVERY run (the metric revives by
#     itself the day polls reappear — the healthy path below is unchanged);
#   • while quiet, it republishes last-good with `source_stalled_since` and an
#     explicit on-card sentence (plus the client-side stale flag already showing);
#   • at >75 days quiet (mid-Sep 2026) it hard-fails again — the acknowledgment
#     is time-boxed, not indefinite; the fallback ladder is in docs 02/04.
STALL_HARD_FAIL_DAYS = 75
TERM_START = datetime.date(2025, 1, 20)
GALLUP_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "static", "gallup_terms.json")


def attach_gallup(out, today):
    """v3 lock: attach the sourced Gallup one-time import (quarterly averages,
    Biden/Trump-1/Obama) so the card can compare vs Biden at the same point in
    term and draw the months-in-office view. Enhancement-only: a problem here
    never blocks the live metric. Term quarters = 3-month blocks from Jan 20."""
    import json as _json
    try:
        with open(GALLUP_STATIC) as f:
            g = _json.load(f)
        months_in = (today.year - TERM_START.year) * 12 + (today.month - TERM_START.month) \
            - (1 if today.day < TERM_START.day else 0)
        quarter = max(1, min(16, months_in // 3 + 1))
        same_q = {}
        for pid in ("biden", "trump1", "obama"):
            v = g["quarterly"].get(pid, {}).get(str(quarter))
            if v is not None:
                same_q[pid] = v
        out["gallup"] = {"term_quarter": quarter, "same_quarter": same_q,
                         "quarterly": g["quarterly"], "inauguration": g["inauguration"],
                         "method_note": g["_method_note"], "source_note": g["_source"]}
    except Exception as e:  # noqa: BLE001
        print(f"  ! approval: Gallup import skipped this run ({e})")
    return out


def stalled_output(existing, today, reason):
    """Build the disclosed last-good payload for a quiet source. Raises if
    there is no last-good to hold, or the acknowledgment window is exhausted."""
    if not existing or existing.get("value") is None:
        raise RuntimeError(f"approval source stalled and no last-good data to hold ({reason})")
    last_poll = str(existing.get("as_of", ""))[:10]
    quiet_days = (today - datetime.date.fromisoformat(last_poll)).days
    if quiet_days > STALL_HARD_FAIL_DAYS:
        raise RuntimeError(
            f"approval feed quiet for {quiet_days} days (newest poll {last_poll}) — "
            "acknowledgment window exhausted; pick the fallback (docs 02/04)")
    pretty = datetime.date.fromisoformat(last_poll).strftime("%b %-d, %Y")
    out = {k: v for k, v in existing.items()
           if k not in ("last_checked", "stale_after", "series")}
    out["source_stalled_since"] = last_poll
    out["note"] = (f"Simple average of {existing.get('n_polls', '?')} national polls "
                   "(one per pollster). Opinion data, not a government statistic — the "
                   "board's one survey-derived metric. VoteHub's public feed has carried "
                   f"no new national approval poll since {pretty}; the figure shown is "
                   "the last aggregate, checked daily.")
    print(f"  ⚠ approval: VoteHub public feed quiet {quiet_days} days "
          f"(newest poll {last_poll}); holding last-good with on-card disclosure; "
          f"hard-fails at {STALL_HARD_FAIL_DAYS} days ({reason})")
    return out


def average_polls(polls, today, window_days=14, min_polls=3):
    """-> (approve_avg, disapprove_avg, n_polls, window_used). One entry per
    pollster (latest end_date wins) inside the window; widens to 30 days if
    thin. Raises if still fewer than 2 polls."""
    def parse(p):
        try:
            end = datetime.date.fromisoformat(str(p.get("end_date", ""))[:10])
        except ValueError:
            return None
        app = dis = None
        for a in p.get("answers", []):
            c = str(a.get("choice", "")).lower()
            try:
                pct = float(a.get("pct"))
            except (TypeError, ValueError):
                continue
            if c.startswith("approv"):
                app = pct
            elif c.startswith("disapprov"):
                dis = pct
        if app is None or dis is None:
            return None
        return {"pollster": p.get("pollster") or "?", "end": end, "app": app, "dis": dis}

    parsed = [q for q in (parse(p) for p in polls
                          if "trump" in str(p.get("subject", "")).lower()) if q]
    for window in (window_days, 30):
        recent = [q for q in parsed if (today - q["end"]).days <= window]
        by_pollster = {}
        for q in sorted(recent, key=lambda x: x["end"]):
            by_pollster[q["pollster"]] = q          # latest poll per pollster wins
        if len(by_pollster) >= min_polls or window == 30:
            polls_used = list(by_pollster.values())
            break
    if len(polls_used) < 2:
        raise RuntimeError(f"only {len(polls_used)} usable approval polls in the last 30 days")
    n = len(polls_used)
    app = round(sum(q["app"] for q in polls_used) / n, 1)
    dis = round(sum(q["dis"] for q in polls_used) / n, 1)
    as_of = max(q["end"] for q in polls_used).isoformat()
    return app, dis, n, as_of


def main():
    # SECOND-RUN FIX (28 Jul 2026): the API has NO pagination and caps large
    # limits server-side (a big `limit` still topped out at Jun-2026 polls).
    # The documented route (votehub.com/polls/api) is date filtering:
    # `from_date` = "polls whose end date is on or after this date", plus a
    # `subject` filter — so ask precisely for recent Trump approval polls.
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=45)).isoformat()
    r = requests.get(API, params={"poll_type": "approval",
                                  "subject": "donald-trump",
                                  "from_date": from_date},
                     headers=UA, timeout=120)
    r.raise_for_status()
    js = r.json()
    polls = js if isinstance(js, list) else (js.get("polls") or js.get("results")
                                             or js.get("data") or [])
    try:
        app, dis, n, as_of = average_polls(polls, today)
        age = (today - datetime.date.fromisoformat(as_of)).days
        if age > 45:
            raise RuntimeError(f"newest usable approval poll is {age} days old — "
                               "feed looks stale or truncated; not publishing")
    except RuntimeError as e:
        # A diagnosed quiet source, not an infra failure (network errors above
        # still raise → red). Republish last-good with explicit disclosure.
        publish(attach_gallup(stalled_output(load_existing("approval_rating"), today, str(e)),
                              today), series=[])
        return

    out = {
        "id": "approval_rating", "name": "Presidential approval",
        "category": "Executive Power & Governance", "value": app, "unit": "% approve",
        "as_of": as_of, "direction": "neutral",
        "disapprove": dis, "net": round(app - dis, 1), "n_polls": n,
        "source": {"name": "VoteHub poll aggregate (CC-BY)",
                   "url": "https://votehub.com/polls/"},
        "cadence": "Weekly",
        "note": f"Simple average of {n} national polls (one per pollster, last ~2 weeks). "
                "Opinion data, not a government statistic — the board's one survey-derived metric.",
    }
    publish(attach_gallup(out, today), series=[{"date": as_of, "value": app}])


if __name__ == "__main__":
    main()
