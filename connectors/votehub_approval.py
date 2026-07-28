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
from common import publish, UA  # noqa: E402

API = "https://api.votehub.com/polls"


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
    from_date = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
    r = requests.get(API, params={"poll_type": "approval",
                                  "subject": "donald-trump",
                                  "from_date": from_date},
                     headers=UA, timeout=120)
    r.raise_for_status()
    js = r.json()
    polls = js if isinstance(js, list) else (js.get("polls") or js.get("results")
                                             or js.get("data") or [])
    app, dis, n, as_of = average_polls(polls, datetime.date.today())

    age = (datetime.date.today() - datetime.date.fromisoformat(as_of)).days
    if age > 45:
        raise RuntimeError(f"newest usable approval poll is {age} days old — "
                           "feed looks stale or truncated; not publishing")

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
    publish(out, series=[{"date": as_of, "value": app}])


if __name__ == "__main__":
    main()
