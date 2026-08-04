#!/usr/bin/env python3
"""Build the static dashboard from data/*.json. No network needed.

Cards are grouped under category headers. Each card shows its own data date
('as of …') prominently and carries a client-side freshness check: a small
"⚠ data may be stale" flag appears whenever the visitor's clock is past the
metric's `stale_after` date. That check runs in the browser, so it keeps
escalating honestly even if the pipeline dies and the page freezes — unlike the
build timestamp, which is always fresh and therefore misleading (it is kept, but
de-emphasised, in the footer)."""
import json
import glob
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "site", "index.html")

TOTAL_PLANNED = 23   # v2 register (project doc 03), locked 28 Jul 2026
CATEGORY_ORDER = [
    "Cost of Living", "Economy & Jobs", "Trade & Tariffs", "Public Finances",
    "Immigration", "Health & Safety Net", "Executive Power & Governance",
]
ORDER = [
    "inflation", "grocery_prices", "gas_price",
    "real_gdp", "unemployment", "real_wages", "federal_workforce",
    "tariff_revenue", "effective_tariff_rate", "trade_deficit",
    "national_debt", "budget_deficit", "interest_on_debt",
    "border_encounters", "ice_removals", "ice_detention",
    "overdose_deaths", "measles_cases", "medicaid_enrollment", "va_claims_backlog",
    "executive_orders", "judges_confirmed", "approval_rating",
]
# Canonical id -> v2 category. Applied at load so the board groups correctly
# even from data files written before the category migration (the connectors
# also stamp the new names; this makes the grouping deterministic either way).
CATEGORIES = {
    "inflation": "Cost of Living", "grocery_prices": "Cost of Living", "gas_price": "Cost of Living",
    "real_gdp": "Economy & Jobs", "unemployment": "Economy & Jobs",
    "real_wages": "Economy & Jobs", "federal_workforce": "Economy & Jobs",
    "tariff_revenue": "Trade & Tariffs", "effective_tariff_rate": "Trade & Tariffs",
    "trade_deficit": "Trade & Tariffs",
    "national_debt": "Public Finances", "budget_deficit": "Public Finances",
    "interest_on_debt": "Public Finances",
    "border_encounters": "Immigration", "ice_removals": "Immigration", "ice_detention": "Immigration",
    "overdose_deaths": "Health & Safety Net", "measles_cases": "Health & Safety Net",
    "medicaid_enrollment": "Health & Safety Net", "va_claims_backlog": "Health & Safety Net",
    "executive_orders": "Executive Power & Governance",
    "judges_confirmed": "Executive Power & Governance",
    "approval_rating": "Executive Power & Governance",
}
STALE_DAYS = {"biweek": 30, "as signed": 12, "as-signed": 12, "as confirmed": 14,
              "dai": 5, "week": 14, "month": 70, "quarter": 130}
DEFAULT_STALE_DAYS = 45


# ---- formatting helpers -----------------------------------------------------
def money_compact(v):
    a = abs(v)
    if a >= 1e12: return f"${v/1e12:.2f}T"
    if a >= 1e9:  return f"${v/1e9:.1f}B"
    if a >= 1e6:  return f"${v/1e6:.1f}M"
    return f"${v:,.0f}"


def num(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,}"


def pretty_date(s):
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            return d.strftime("%b %Y") if fmt == "%Y-%m" else d.strftime("%b %-d, %Y")
        except ValueError:
            continue
    return s


def effective_date(as_of):
    try:
        if len(as_of) == 7:
            y, m = int(as_of[:4]), int(as_of[5:7])
            nm = datetime.date(y + (m == 12), (m % 12) + 1, 1)
            return nm - datetime.timedelta(days=1)
        return datetime.date.fromisoformat(as_of)
    except Exception:
        return datetime.date.today()


def stale_after(m):
    if m.get("stale_after"):
        return m["stale_after"]
    cad = (m.get("cadence") or "").lower()
    days, best = DEFAULT_STALE_DAYS, -1
    for key, d in STALE_DAYS.items():
        if key in cad and len(key) > best:
            days, best = d, len(key)
    return (effective_date(m["as_of"]) + datetime.timedelta(days=days)).isoformat()


# ---- per-metric render ------------------------------------------------------
def render_bars(rows, accent):
    mx = max(r[1] for r in rows) or 1
    out = []
    for label, val, disp, tone in rows:
        w = max(2, round(abs(val) / mx * 100))
        color = {"accent": accent, "muted": "var(--muted)",
                 "critical": "var(--critical)", "good": "var(--good)"}[tone]
        out.append(f"""
        <div class="bar-row">
          <div class="bar-label">{label}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div>
          <div class="bar-val">{disp}</div>
        </div>""")
    return "".join(out)


def tile(m):
    cat, name, src = m["category"], m["name"], m["source"]
    accent = "var(--series-1)"
    delta, bars, sub = "", "", m.get("note", "")

    if m["id"] == "executive_orders":
        hero = num(m["value"]); comp = m["comparison"]
        delta = f'<span class="delta neutral">{num(m["value"]-comp["value"])} more than Biden ({num(comp["value"])}) at the same point</span>'
        bars = render_bars([("Trump", m["value"], num(m["value"]), "accent"),
                            ("Biden", comp["value"], num(comp["value"]), "muted")], accent)
        sub = "Since inauguration · " + pretty_date(m["since"])

    elif m["id"] == "national_debt":
        hero = money_compact(m["value"]); base = m["baseline"]
        inc = m["value"] - base["value"]; pct = inc / base["value"] * 100
        delta = f'<span class="delta bad">&#9650; {money_compact(inc)} (+{pct:.1f}%) since inauguration</span>'
        bars = render_bars([("Now", m["value"], money_compact(m["value"]), "critical"),
                            ("Inauguration", base["value"], money_compact(base["value"]), "muted")], accent)
        sub = "Total public debt outstanding"

    elif m["id"] == "budget_deficit":
        hero = f'${m["value"]:,.0f}B'
        sub = m["note"]
        if m.get("comparison"):
            comp = m["comparison"]; diff = m["value"] - comp["value"]
            tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta {tone}">{arrow} ${abs(diff):,.0f}B vs the same point last fiscal year (${comp["value"]:,.0f}B)</span>'
            bars = render_bars([("This FY", m["value"], f'${m["value"]:,.0f}B', "critical"),
                                ("Prior FY", comp["value"], f'${comp["value"]:,.0f}B', "muted")], accent)

    elif m["id"] == "inflation":
        hero = f'{m["value"]}%'; tgt = m["target"]; gap = m["value"] - tgt["value"]
        tone = "bad" if gap > 0 else "good"; arrow = "&#9650;" if gap > 0 else "&#9660;"
        delta = f'<span class="delta {tone}">{arrow} {abs(gap):.1f} pts {"above" if gap>0 else "below"} the Fed&#39;s {tgt["value"]}% target</span>'
        bars = render_bars([("CPI (YoY)", m["value"], f'{m["value"]}%', "critical" if gap > 0 else "good"),
                            ("Fed target", tgt["value"], f'{tgt["value"]}%', "muted")], accent)
        sub = m["note"]

    elif m["id"] == "unemployment":
        hero = f'{m["value"]}%'; base = m["baseline"]; diff = m["value"] - (base["value"] or m["value"])
        tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
        delta = f'<span class="delta {tone}">{arrow} {abs(diff):.1f} pts since inauguration ({base["value"]}%)</span>'
        bars = render_bars([("Now", m["value"], f'{m["value"]}%', "critical" if diff > 0 else "good"),
                            ("Inauguration", base["value"] or 0, f'{base["value"]}%', "muted")], accent)
        sub = m["note"]

    elif m["id"] == "gas_price":
        hero = f'${m["value"]:.2f}'; base = m["baseline"]; diff = m["value"] - base["value"]; pct = diff / base["value"] * 100
        tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
        delta = f'<span class="delta {tone}">{arrow} ${abs(diff):.2f} ({pct:+.0f}%) since inauguration</span>'
        bars = render_bars([("Now", m["value"], f'${m["value"]:.2f}', "critical" if diff > 0 else "good"),
                            ("Inauguration", base["value"], f'${base["value"]:.2f}', "muted")], accent)
        sub = m["note"].split(".")[0]

    elif m["id"] == "trade_deficit":
        hero = f'${m["value"]:.1f}B'; base = m["baseline"]; diff = m["value"] - base["value"]
        tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
        pct = (diff / base["value"] * 100) if base["value"] else 0
        delta = f'<span class="delta {tone}">{arrow} ${abs(diff):.1f}B ({pct:+.0f}%) vs {base["label"].lower()}</span>'
        bars = render_bars([("Latest", m["value"], f'${m["value"]:.1f}B', "critical" if diff > 0 else "good"),
                            (base["label"].split("(")[0].strip()[:12] or "Baseline", base["value"], f'${base["value"]:.1f}B', "muted")], accent)
        sub = m["note"]

    elif m["id"] == "border_encounters":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("comparison"):
            comp = m["comparison"]; diff = m["value"] - comp["value"]
            pct = (diff / comp["value"] * 100) if comp["value"] else 0
            arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta neutral">{arrow} {pct:+.0f}% vs the same month last year ({num(comp["value"])})</span>'
            bars = render_bars([("Latest", m["value"], num(m["value"]), "accent"),
                                ("Yr earlier", comp["value"], num(comp["value"]), "muted")], accent)

    elif m["id"] == "ice_detention":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("currently_detained"):
            delta = f'<span class="delta neutral">Currently detained (point-in-time): {num(m["currently_detained"])}</span>'
        else:
            delta = '<span class="delta neutral">Average daily population in ICE detention</span>'

    # ---- v2 expansion cards (28 Jul 2026) ----
    elif m["id"] == "grocery_prices":
        hero = f'{m["value"]}%'
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]; gap = m["value"] - base["value"]
            tone = "bad" if gap > 0 else "good"; arrow = "&#9650;" if gap > 0 else "&#9660;"
            delta = f'<span class="delta {tone}">{arrow} {abs(gap):.1f} pts vs {base["value"]}% at inauguration</span>'
            bars = render_bars([("Now (YoY)", m["value"], f'{m["value"]}%', "critical" if gap > 0 else "good"),
                                ("Inauguration", base["value"], f'{base["value"]}%', "muted")], accent)

    elif m["id"] == "real_gdp":
        hero = f'{m["value"]:+.1f}%'
        sub = m["note"]
        if m.get("comparison") and m.get("term_avg") is not None:
            comp = m["comparison"]
            delta = (f'<span class="delta neutral">Term average {m["term_avg"]:+.1f}% · '
                     f'{comp["label"]}: {comp["value"]:+.1f}%</span>')
            bars = render_bars([("This term", m["term_avg"], f'{m["term_avg"]:+.1f}%', "accent"),
                                ("Biden", comp["value"], f'{comp["value"]:+.1f}%', "muted")], accent)

    elif m["id"] == "real_wages":
        hero = f'${m["value"]:,.0f}'
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]; diff = m["value"] - base["value"]
            pct = diff / base["value"] * 100 if base["value"] else 0
            tone = "good" if diff > 0 else ("bad" if diff < 0 else "neutral")
            arrow = "&#9650;" if diff > 0 else ("&#9660;" if diff < 0 else "")
            delta = f'<span class="delta {tone}">{arrow} {pct:+.1f}% since the inauguration quarter (${base["value"]:,.0f})</span>'
            bars = render_bars([("Now", m["value"], f'${m["value"]:,.0f}', "accent"),
                                ("Q1 2025", base["value"], f'${base["value"]:,.0f}', "muted")], accent)

    elif m["id"] == "federal_workforce":
        hero = f'{m["value"]:,.0f}k'
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]; diff = m["value"] - base["value"]
            pct = diff / base["value"] * 100 if base["value"] else 0
            arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta neutral">{arrow} {abs(diff):,.0f}k ({pct:+.1f}%) since inauguration ({base["value"]:,.0f}k)</span>'
            bars = render_bars([("Now", m["value"], f'{m["value"]:,.0f}k', "accent"),
                                ("Inauguration", base["value"], f'{base["value"]:,.0f}k', "muted")], accent)

    elif m["id"] == "tariff_revenue":
        hero = f'${m["value"]:,.0f}B'
        sub = m["note"]
        rows = [("This FY, gross", m["value"], f'${m["value"]:,.0f}B', "accent")]
        if m.get("net_fytd") is not None:
            rows.append(("This FY, net", m["net_fytd"], f'${m["net_fytd"]:,.0f}B', "muted"))
        if m.get("comparison"):
            comp = m["comparison"]
            rows.append(("Prior FY, gross", comp["value"], f'${comp["value"]:,.0f}B', "muted"))
            pieces = [f'prior FY gross ${comp["value"]:,.0f}B']
            if m.get("net_fytd") is not None:
                pieces.insert(0, f'net after refunds ${m["net_fytd"]:,.0f}B')
            delta = f'<span class="delta neutral">Gross fiscal-YTD · {" · ".join(pieces)}</span>'
        bars = render_bars(rows, accent)

    elif m["id"] == "effective_tariff_rate":
        hero = f'{m["value"]:.1f}%'
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]
            delta = f'<span class="delta neutral">vs {base["value"]:.1f}% at inauguration</span>'
            bars = render_bars([("Now", m["value"], f'{m["value"]:.1f}%', "accent"),
                                ("Inauguration", base["value"], f'{base["value"]:.1f}%', "muted")], accent)

    elif m["id"] == "interest_on_debt":
        hero = f'${m["value"]:,.0f}B'
        sub = m["note"]
        if m.get("comparison"):
            comp = m["comparison"]; diff = m["value"] - comp["value"]
            tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta {tone}">{arrow} ${abs(diff):,.0f}B vs the same point last fiscal year (${comp["value"]:,.0f}B)</span>'
            bars = render_bars([("This FY", m["value"], f'${m["value"]:,.0f}B', "critical"),
                                ("Prior FY", comp["value"], f'${comp["value"]:,.0f}B', "muted")], accent)

    elif m["id"] == "ice_removals":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("comparison"):
            comp = m["comparison"]
            delta = f'<span class="delta neutral">FY2024 full year (prior administration): {num(comp["value"])}</span>'
            bars = render_bars([("This FY so far", m["value"], num(m["value"]), "accent"),
                                ("FY2024 total", comp["value"], num(comp["value"]), "muted")], accent)

    elif m["id"] == "overdose_deaths":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]; diff = m["value"] - base["value"]
            pct = diff / base["value"] * 100 if base["value"] else 0
            tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta {tone}">{arrow} {num(abs(diff))} ({pct:+.0f}%) vs the 12 months ending at inauguration</span>'
            bars = render_bars([("Latest 12 mo", m["value"], num(m["value"]), "critical" if diff > 0 else "good"),
                                ("To Jan 2025", base["value"], num(base["value"]), "muted")], accent)

    elif m["id"] == "measles_cases":
        hero = num(m["value"])
        sub = m["note"].split(" — ")[0] + "."
        if m.get("comparison"):
            comp = m["comparison"]; diff = m["value"] - comp["value"]
            if diff > 0:
                delta = f'<span class="delta bad">&#9650; already above {comp["label"].lower()} ({num(comp["value"])})</span>'
            else:
                delta = f'<span class="delta neutral">{comp["label"]}: {num(comp["value"])}</span>'
            bars = render_bars([("This year so far", m["value"], num(m["value"]), "critical" if diff > 0 else "accent"),
                                (comp["label"], comp["value"], num(comp["value"]), "muted")], accent)

    elif m["id"] == "medicaid_enrollment":
        hero = f'{m["value"] / 1e6:.1f}M'
        sub = m["note"]
        if m.get("baseline"):
            base = m["baseline"]; diff = m["value"] - base["value"]
            arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta neutral">{arrow} {abs(diff) / 1e6:.1f}M since Dec 2024 ({base["value"] / 1e6:.1f}M)</span>'
            bars = render_bars([("Now", m["value"], f'{m["value"] / 1e6:.1f}M', "accent"),
                                ("Dec 2024", base["value"], f'{base["value"] / 1e6:.1f}M', "muted")], accent)

    elif m["id"] == "va_claims_backlog":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("total_pending"):
            sub += f' Total pending now: {num(m["total_pending"])}.'
        if m.get("baseline"):
            base = m["baseline"]; diff = m["value"] - base["value"]
            pct = diff / base["value"] * 100 if base["value"] else 0
            tone = "bad" if diff > 0 else "good"; arrow = "&#9650;" if diff > 0 else "&#9660;"
            delta = f'<span class="delta {tone}">{arrow} {num(abs(diff))} ({pct:+.0f}%) since inauguration</span>'
            bars = render_bars([("Now", m["value"], num(m["value"]), "critical" if diff > 0 else "good"),
                                ("Inauguration", base["value"], num(base["value"]), "muted")], accent)

    elif m["id"] == "judges_confirmed":
        hero = num(m["value"])
        sub = m["note"]
        if m.get("comparison"):
            comp = m["comparison"]; diff = m["value"] - comp["value"]
            delta = f'<span class="delta neutral">{diff:+,.0f} vs his first term at the same point ({num(comp["value"])})</span>'
            rows = [("This term", m["value"], num(m["value"]), "accent"),
                    ("Term 1", comp["value"], num(comp["value"]), "muted")]
            if m.get("biden_same_point") is not None:
                rows.append(("Biden", m["biden_same_point"], num(m["biden_same_point"]), "muted"))
            bars = render_bars(rows, accent)

    elif m["id"] == "approval_rating":
        hero = f'{m["value"]:.0f}%'
        sub = m["note"]
        if m.get("disapprove") is not None:
            net = m.get("net", m["value"] - m["disapprove"])
            delta = f'<span class="delta neutral">Disapprove {m["disapprove"]:.0f}% · net {net:+.0f}</span>'
            bars = render_bars([("Approve", m["value"], f'{m["value"]:.0f}%', "accent"),
                                ("Disapprove", m["disapprove"], f'{m["disapprove"]:.0f}%', "muted")], accent)

    else:
        hero = str(m.get("value", ""))

    sa = stale_after(m)
    return f"""
    <article class="tile" data-as-of="{m['as_of']}" data-stale-after="{sa}" data-cadence="{m['cadence'].lower()}">
      <div class="tile-cat">{cat}</div>
      <h2 class="tile-name">{name}</h2>
      <div class="hero">{hero}</div>
      {delta}
      <div class="freshness">
        <span class="asof">as of {pretty_date(m['as_of'])}</span>
        <span class="stale-flag" hidden>&#9888; data may be stale</span>
      </div>
      <div class="tile-sub">{sub}</div>
      <div class="bars">{bars}</div>
      <div class="tile-foot">
        <a href="{src['url']}" target="_blank" rel="noopener">{src['name']} &#8599;</a>
        <span>updates {m['cadence'].lower()}</span>
      </div>
    </article>"""


# ---- presentation layer (phase 7): chart payloads ---------------------------
# Expanded views use three reusable templates (own-history / term-aligned /
# vs-benchmark; project doc 03 fixes each metric's pick). build.py pre-computes
# everything chart-ready here in Python and emits one small site/d/<id>.json per
# metric, fetched by the browser on first expand — "store deep, load shallow"
# all the way to the visitor. Browser JS (assets/chart.js, inlined) stays dumb.
#
# President colors (locked with the creator, 29 Jul 2026): the current term is
# red and Biden is blue (party-conventional). The reds/greens the collapsed
# cards use for good/bad deltas are DIFFERENT steps (#d03b3b/#0ca30c) from the
# series red (#e66767) so a direction cue can never impersonate a president
# line. Palette validated (colorblind separation + contrast, dark surface):
# worst adjacent pair ΔE 8.4, all lines also carry legend + direct labels.
ASSETS = os.path.join(HERE, "assets")
SITE_D = os.path.join(HERE, "site", "d")

PRES = {
    "trump2": {"label": "Trump ’25", "color": "#e66767", "inaug": datetime.date(2025, 1, 20)},
    "biden":  {"label": "Biden",     "color": "#3987e5", "inaug": datetime.date(2021, 1, 20)},
    "trump1": {"label": "Trump ’17", "color": "#199e70", "inaug": datetime.date(2017, 1, 20)},
    "obama":  {"label": "Obama",     "color": "#c98500", "inaug": datetime.date(2009, 1, 20)},
}
ACCENT = "#3987e5"      # single-series lines: the metric, not a president
SECOND = "#d95926"      # second non-president series (e.g. net vs gross)
TERM_MONTHS = 48        # aligned charts compare first terms, month 0–48
T2_START = PRES["trump2"]["inaug"]


def _pdate(s):
    return datetime.date(int(s[:4]), int(s[5:7]), 1) if len(s) == 7 else datetime.date.fromisoformat(s)


def _ems(d):
    return int(datetime.datetime(d.year, d.month, d.day,
                                 tzinfo=datetime.timezone.utc).timestamp() * 1000)


def _mon_idx(d, inaug):
    return (d.year - inaug.year) * 12 + (d.month - inaug.month)


def date_points(series):
    return [[_ems(_pdate(p["date"])), p["value"]] for p in series]


def aligned_monthly(series, pres, pct=False, months=TERM_MONTHS):
    """Series -> [[months_in_office, value]] for one president's first term.
    pct=True rebases to % change vs the inauguration month (requires month 0)."""
    inaug = PRES[pres]["inaug"]
    pts = []
    for p in series:
        mi = _mon_idx(_pdate(p["date"]), inaug)
        if 0 <= mi <= months:
            pts.append([mi, p["value"]])
    if not pts:
        return None
    if pct:
        base = next((v for m, v in pts if m == 0), None)
        if base is None:
            return None
        pts = [[m, round((v / base - 1) * 100, 2)] for m, v in pts]
    return pts


def carry_forward(pts, months=TERM_MONTHS):
    """Densify a cumulative counter: months with no events carry the running
    value (that IS the count's meaning — not interpolation of missing data)."""
    if not pts:
        return pts
    out, have = [], dict(pts)
    last = None
    for m in range(0, min(months, max(have)) + 1):
        if m in have:
            last = have[m]
        if last is not None:
            out.append([m, last])
    return out


def aligned_daily_pct(series, pres, months=TERM_MONTHS, thin_days=7):
    """Daily series -> weekly-thinned [[months_in_office, %growth since
    inauguration day]] (exact stored values, sampled — never smoothed)."""
    inaug = PRES[pres]["inaug"]
    rows = sorted((_pdate(p["date"]), p["value"]) for p in series)
    rows = [(d, v) for d, v in rows if 0 <= (d - inaug).days <= months * 30.44 + 15]
    if not rows:
        return None
    base = rows[0][1]
    pts, last = [], None
    for i, (d, v) in enumerate(rows):
        if last is None or (d - last).days >= thin_days or i == len(rows) - 1:
            pts.append([round((d - inaug).days / 30.4375, 2), round((v / base - 1) * 100, 2)])
            last = d
    return pts


def gdp_index(series, pres, quarters=16):
    """Quarterly annualized rates -> compounded index, 100 at the inauguration
    quarter's start (transparent formula: ×(1+r/100)^(1/4) per quarter)."""
    inaug = PRES[pres]["inaug"]
    pts, idx = [[0, 100.0]], 100.0
    n = 0
    for p in series:
        d = _pdate(p["date"])                      # stored as quarter-END month
        mi = _mon_idx(d, inaug) + 1                # months elapsed at quarter end
        if mi <= 0 or n >= quarters:
            continue
        if mi > TERM_MONTHS:
            break
        idx *= (1 + p["value"] / 100) ** 0.25
        pts.append([mi, round(idx, 2)])
        n += 1
    return pts if len(pts) > 1 else None


def _pseries(ids, series, **kw):
    """Aligned series list for the given presidents, newest-term first (fixed
    entity colors; presidents with no reachable data simply drop out)."""
    out = []
    for pid in ids:
        fn = kw.get("fn") or (lambda s, p: aligned_monthly(s, p, pct=kw.get("pct", False)))
        pts = fn(series, pid)
        if pts:
            out.append({"label": PRES[pid]["label"], "color": PRES[pid]["color"], "pts": pts})
    return out


GAP_SHUTDOWN = "Oct ’25 not published (shutdown)"


def payload(m, loaded):
    """The chart payload for one metric — everything assets/chart.js needs.
    Falls back to an honest 'history accrues from here' state when the stored
    series is still too short to chart."""
    mid = m["id"]
    S = m.get("series") or []
    fx = {"id": mid, "asOf": pretty_date(m["as_of"]), "cadence": m["cadence"].lower(),
          "srcName": m["source"]["name"], "srcUrl": m["source"]["url"],
          "template": "line", "xType": "date", "series": []}

    def own(title, fmt, area=True, rng=None, gaps=None, unit=None, label=None):
        fx.update(chartTitle=title, fmt=fmt, zeroBase=True, area=area,
                  series=[{"label": label or m["name"], "color": ACCENT, "pts": date_points(S)}],
                  markers=[{"x": _ems(T2_START), "label": "Inauguration", "kind": "inaug"}])
        if unit:
            fx["unitLabel"] = unit
        if gaps:
            fx["gaps"] = gaps
        first = _pdate(S[0]["date"]) if S else T2_START
        if rng is None:
            rng = (T2_START - first).days > 3 * 365
        if rng:
            fx.update(rangeToggle=True, termStart=_ems(T2_START))

    def aligned(title, fmt, sers, unit=None, markers=None, gaps=None, dots=None,
                zero=True, baseline=None, fmt_axis=None):
        fx.update(chartTitle=title, fmt=fmt, xType="months", xMax=TERM_MONTHS,
                  zeroBase=zero, direct=True, series=sers)
        if unit:
            fx["unitLabel"] = unit
        if markers:
            fx["markers"] = markers
        if gaps:
            fx["gaps"] = gaps
        if dots:
            fx["dots"] = dots
        if baseline is not None:
            fx["baseline"] = baseline
        if fmt_axis:
            fx["fmtAxis"] = fmt_axis

    def accrue(title, body):
        fx.update(chartTitle=title, series=[], accrueTitle="History accrues from here",
                  accrueBody=body)

    # ---------------- Cost of Living ----------------
    if mid == "inflation":
        own("CPI-U inflation, year over year — 2018 to now", "pct", unit="CPI-U YoY")
        fx.update(benchmark=(m.get("target") or {}).get("value", 2.0), benchmarkLabel="Fed target 2%",
                  gaps=[{"x": _ems(datetime.date(2025, 10, 15)), "label": GAP_SHUTDOWN}],
                  channels="tariffs feed into import prices; fiscal policy shapes demand; energy policy moves fuel costs.",
                  limits="the Federal Reserve independently sets interest-rate policy, and global supply and demand drive most short-run movement.",
                  caveats=["October 2025 CPI was never published (federal shutdown) — the line breaks rather than estimating a value.",
                           "BLS sample reductions in 2025 widen the error bars on recent readings."])

    elif mid == "grocery_prices":
        own("Grocery inflation (food at home), year over year — 1953 to now", "pct", unit="Food-at-home YoY")
        fx.update(gaps=[{"x": _ems(datetime.date(2025, 10, 15)), "label": GAP_SHUTDOWN}],
                  channels="tariffs on imported food, energy and transport costs, farm-labor supply via immigration policy.",
                  limits="weather, animal disease (e.g. avian flu in eggs) and global commodity markets set most short-run food prices.",
                  caveats=["October 2025 CPI was never published (federal shutdown) — the gap is shown, not interpolated.",
                           "Year-over-year change in the BLS food-at-home index — the grocery-store basket."])

    elif mid == "gas_price":
        own("US average pump price, regular — weekly since 1990", "usd2", unit="$/gal")
        fx.update(channels="drilling and permitting policy, strategic-reserve releases, sanctions on producer states.",
                  limits="global crude markets set most of the pump price; OPEC+ supply decisions and demand swings dominate.",
                  caveats=["EIA weekly survey, national average for regular grade; state prices vary widely around it."])

    # ---------------- Economy & Jobs ----------------
    elif mid == "real_gdp":
        sers = _pseries(["trump2", "biden", "trump1", "obama"], S, fn=gdp_index)
        aligned("Real GDP, compounded index — 100 at each inauguration quarter", "idx",
                sers, unit="Index (=100 at inauguration)", zero=False, baseline=100)
        fx.update(channels="fiscal policy, tariffs, regulation, immigration (labor supply).",
                  limits="business cycles, Federal Reserve policy and global conditions dominate quarterly moves; tariff-driven import swings whipsawed 2025 readings in both directions.",
                  caveats=["Index compounds the official quarterly annualized rates: ×(1+r/100)^¼ per quarter, from 100 at the start of each president’s inauguration quarter.",
                           "GDP estimates are revised repeatedly (advance → second → third); recent quarters will move. Q4-2025 estimates were built on shutdown-impaired inputs."])

    elif mid == "unemployment":
        sers = _pseries(["trump2", "biden", "trump1"], S)
        aligned("Unemployment rate, by months in office", "pct", sers, unit="U-3 rate",
                gaps=[{"x": _mon_idx(datetime.date(2025, 10, 1), T2_START), "label": GAP_SHUTDOWN}])
        fx.update(channels="fiscal policy, federal hiring and firing, trade policy, immigration enforcement (labor supply).",
                  limits="the business cycle and Fed policy drive most changes; presidents inherit trends.",
                  caveats=["Oct 2025’s household survey was lost to the shutdown — the line breaks, nothing is estimated. The Aug 2025 dismissal of the BLS commissioner is a data-independence caveat, stated factually: methodology is unchanged and the series remains the official count.",
                           "Obama-era months predate the stored series (which starts 2017) — a candidate one-time backfill."])

    elif mid == "real_wages":
        sers = _pseries(["trump2", "biden", "trump1", "obama"], S, pct=True)
        aligned("Real median weekly earnings, % change since inauguration quarter", "pctsign", sers,
                unit="% vs inauguration qtr",
                gaps=[{"x": _mon_idx(datetime.date(2025, 12, 1), T2_START), "label": "Q4 ’25 not collected (shutdown)"}])
        fx.update(channels="tax policy, labor regulation, tariffs (consumer prices), immigration policy (labor supply).",
                  limits="productivity and labor-market tightness set the trend; the series is quarterly and noisy.",
                  caveats=["Q4 2025 is a permanent hole — the shutdown killed that quarter’s survey collection; the break is shown, never filled.",
                           "Constant-dollar (inflation-adjusted) median usual weekly earnings, full-time workers; % of each president’s inauguration-quarter level."])

    elif mid == "federal_workforce":
        sers = _pseries(["trump2", "biden", "trump1", "obama"], S, pct=True)
        aligned("Federal civilian employment, % change since inauguration", "pctsign", sers,
                unit="% vs inauguration")
        fx.update(channels="direct — hiring freezes, reductions in force, deferred-resignation programs, reorganisations.",
                  limits="includes the self-funded ~600k Postal Service; courts have reversed some separations; deferred-resignation staff counted as employed while still paid, which delayed the visible drop until Oct 2025.",
                  caveats=["Percent of each president’s inauguration-month workforce (BLS monthly count, incl. Postal Service).",
                           "Obama’s month-14 spike is the temporary 2010 Census hiring — a reminder that single months mislead."])

    # ---------------- Trade & Tariffs ----------------
    elif mid == "tariff_revenue":
        sers = [{"label": "Gross, fiscal-YTD", "color": ACCENT, "pts": date_points(S)}]
        net = m.get("series_net")
        if net:
            sers.append({"label": "Net of refunds", "color": SECOND, "pts": date_points(net)})
        fx.update(chartTitle="Customs duties, fiscal-YTD by month — resets each October", fmt="usdB",
                  zeroBase=True, series=sers, unitLabel="FYTD ($B)",
                  markers=[{"x": _ems(T2_START), "label": "Inauguration", "kind": "inaug"}],
                  channels="direct — the president sets tariff rates by proclamation under trade statutes and IEEPA.",
                  limits="duties are remitted by importers; revenue depends on import volumes, which tariffs suppress; courts can order refunds — visible in 2026 as negative net months.",
                  caveats=["Fiscal-year-to-date, so lines saw-tooth back toward zero every October.",
                           "Gross and net shown together (once the net line lands, from the same Treasury table): June 2026 alone saw $49B of court-ordered refunds — either figure without the other misleads."
                           if not net else
                           "Gross and net of refunds shown together: June 2026 alone saw $49B of court-ordered refunds — either figure without the other misleads."])

    elif mid == "effective_tariff_rate":
        own("Effective tariff rate: duties ÷ goods imports, monthly", "pct2", unit="Duties ÷ imports")
        fx.update(channels="as tariff revenue — rates are set by proclamation.",
                  limits="the measured rate reflects the import mix as well as policy: imports shifting toward exempt goods lowers it with no policy change; refund months distort it.",
                  caveats=["A transparent computed ratio of two official series (Treasury customs duties ÷ Census/BEA goods imports) — not an academic ‘average tariff rate’.",
                           "Gross-duties numerator, labelled as such; heavy-refund months overstate or understate the true rate."])

    elif mid == "trade_deficit":
        own("Goods & services trade balance, monthly since 1992", "usdB", unit="Balance ($B)")
        fx.update(channels="tariffs, trade agreements, export controls.",
                  limits="the balance is driven by macro saving-investment flows, exchange rates and growth differentials; tariff front-running whipsawed 2025 monthly readings.",
                  caveats=["Negative = deficit. The 2025 spikes are importers front-running announced tariffs, then the snap-back — single months mislead here more than usual."])

    # ---------------- Public Finances ----------------
    elif mid == "national_debt":
        sers = _pseries(["trump2", "biden", "trump1"], S, fn=aligned_daily_pct)
        aligned("Total public debt, % growth since each inauguration", "pctsign", sers,
                unit="% growth", fmt_axis="pctsign")
        fx.update(channels="signed tax and spending legislation (incl. the 2025 reconciliation law), tariff receipts.",
                  limits="most spending is mandatory programs enacted decades ago; interest compounds automatically; Congress holds the purse.",
                  caveats=["Each line starts at 0% on that president’s inauguration day (Treasury daily series, weekly-sampled); Obama’s line needs a one-time backfill — the stored series begins 2017.",
                           "Growth is in percent so different starting debt levels compare honestly; dollar levels are on the collapsed card."])

    elif mid == "budget_deficit":
        own("Federal deficit, fiscal-YTD by month — resets each October", "usdB",
            area=False, unit="FYTD ($B)")
        fx.update(channels="proposed budgets, signed legislation, tariff receipts, workforce cuts.",
                  limits="mandatory spending and interest dominate outlays; fiscal years straddle administrations (FY2025 began under Biden).",
                  caveats=["Fiscal-year-to-date, so the line saw-tooths each October; compare same months across teeth, not adjacent points."])

    elif mid == "interest_on_debt":
        own("Interest on the public debt, fiscal-YTD by month", "usdB", area=False, unit="FYTD ($B)")
        fx.update(channels="deficits add to the stock of debt to be financed.",
                  limits="interest rates — set by markets and the Fed — drive the cost of rolling the existing $36T+; much of today’s bill was locked in by past borrowing.",
                  caveats=["Sums all ~38 Treasury expense categories, including negative amortization lines; single months are lumpy from premium timing — the FYTD line is the honest read."])

    # ---------------- Immigration ----------------
    elif mid == "border_encounters":
        sers = _pseries(["trump2", "biden"], S)
        aligned("Southwest border encounters per month, by months in office", "count", sers,
                unit="Encounters / mo",
                markers=[{"x": _mon_idx(datetime.date(2023, 5, 1), PRES["biden"]["inaug"]),
                          "label": "Title 42 ends — definition change", "kind": "break"}],
                gaps=[{"x": 21, "label": "Biden data begins Oct ’22 (current CBP file)"}])
        fx.update(channels="direct — border policy, asylum rules, processing regimes, military deployment.",
                  limits="push factors abroad and smuggling economics also move flows; counts are events, not unique people; Title 42→Title 8 changes comparability across eras.",
                  caveats=["The dashed marker is a definition break: pandemic-era Title 42 expulsions ended May 2023 — counts either side aren’t directly comparable. Marked, never smoothed.",
                           "Line breaks are real holes (CBP’s current file omits Jul–Sep of closed fiscal years); the archive backfill fills them and Biden’s first 21 months."])

    elif mid == "ice_removals":
        annual = m.get("annual_history") or []
        if annual:
            bars, label_idx = [], []
            for i, p in enumerate(annual):
                bars.append([i, p["value"], "’" + str(p["fy"])[2:], "FY" + str(p["fy"])])
            last_fy = annual[-1]["fy"]
            for fy in range(last_fy + 1, 2026):   # unpublished closed years: labelled holes
                bars.append([len(bars), None, "’" + str(fy)[2:], f"FY{fy} — annual report pending"])
            bars.append([len(bars), m["value"], "’26*", f"FY2026 to date ({pretty_date(m['as_of'])})"])
            vals = [(b[1] or 0) for b in bars]
            label_idx = sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)[:2] + [len(bars) - 1]
            fx.update(template="bars", xType="bars",
                      chartTitle="ICE removals by fiscal year — ’26 is year-to-date", fmt="count",
                      series=[{"label": "Removals", "color": ACCENT, "pts": bars}],
                      labelIdx=sorted(set(label_idx)), unitLabel="Removals")
        else:
            accrue("ICE removals, fiscal-YTD",
                   "The workbook series starts FY2025 and accrues with each ICE snapshot "
                   "(roughly biweekly). Annual history FY2012–FY2024 from ICE’s ERO annual "
                   "reports is a one-time static import that lands with the next data run.")
        fx.update(channels="direct — enforcement priorities, funding (the 2025 reconciliation law tripled ICE’s budget), agreements with receiving countries.",
                  limits="court injunctions, detention capacity and receiving-country cooperation constrain removals; official counts exclude some Border Patrol actions and lag events.",
                  caveats=["ICE’s published workbook figure — never reconciled to press-release ‘deportation’ totals, which mix in CBP actions counted differently.",
                           "Annual bars are ICE ERO annual-report totals (static, sourced); FY2025’s full-year total joins when ICE publishes its annual report. ICE paused publication for 56 days in early 2026 — gaps show as gaps."])

    elif mid == "ice_detention":
        if len(S) >= 4:
            own("Average daily population in ICE detention (FY-to-date)", "count",
                rng=False, unit="ADP")
        else:
            accrue("Average daily population in ICE detention",
                   f"First dated snapshot: FY2026-to-date average of {m['value']:,.0f} "
                   f"(data through {pretty_date(m['as_of'])})"
                   + (f", with {m['currently_detained']:,.0f} currently detained as context. "
                      if m.get("currently_detained") else ". ")
                   + "ICE publishes dated workbook snapshots roughly every two weeks — each "
                     "release adds a point and this chart draws itself as the record builds.")
        fx.update(channels="direct — detention funding, facility contracts, arrest priorities.",
                  limits="capacity is set by congressional appropriations; ADP is a FY-to-date average that smooths spikes (not a point-in-time headcount — labelled as such).",
                  caveats=["The workbook’s two independent ADP splits are cross-checked every run and must agree within 1% before a value publishes."])

    # ---------------- Health & Safety Net ----------------
    elif mid == "overdose_deaths":
        own("Drug overdose deaths, trailing-12-month total — 2015 to now", "count",
            unit="Deaths (12-mo)")
        fx.update(channels="fentanyl interdiction at the border, precursor-focused trade pressure, treatment and naloxone funding.",
                  limits="the decline began mid-2023; street-supply changes, state programs and naloxone availability drive much of it; provisional data revises for months.",
                  caveats=["CDC provisional estimates (predicted counts); the most recent ~6 months revise as reports complete."])

    elif mid == "measles_cases":
        bars = []
        for i, p in enumerate(S):
            y = p["date"][:4]
            last = i == len(S) - 1
            bars.append([i, p["value"], "’" + y[2:] + ("*" if last else ""),
                         y + (f" (to {pretty_date(m['as_of'])})" if last else "")])
        vals = [b[1] for b in bars]
        top = sorted(range(len(vals)), key=lambda i: vals[i], reverse=True)[:3]
        fx.update(template="bars", xType="bars", fmt="count",
                  chartTitle="Confirmed measles cases by year — the last bar is year-to-date",
                  series=[{"label": "Confirmed cases", "color": ACCENT, "pts": bars}],
                  labelIdx=sorted(set(top)), unitLabel="Cases",
                  channels="federal vaccine policy, CDC/ACIP recommendations and messaging, outbreak-response funding.",
                  limits="outbreaks are local, driven by community vaccination rates and exposure events; counts are confirmed-only and revised retroactively.",
                  caveats=["The final bar is a partial year and already exceeds 2025 — the worst full year since 1992. Measles was declared eliminated in the US in 2000.",
                           "CDC merged its ‘unvaccinated’ and ‘unknown-status’ categories in 2025; history revises as cases are re-bucketed."])

    elif mid == "medicaid_enrollment":
        own("Medicaid & CHIP enrollment, monthly — 2014 to now", "count", unit="Enrolled")
        fx.update(channels="eligibility and work-requirement rules (2025 reconciliation law), verification requirements, funding formulas.",
                  limits="the post-pandemic unwinding decline began in 2023 under Biden; most 2025-law provisions phase in through 2027–28; states administer enrollment.",
                  caveats=["~4-month reporting lag; states restate preliminary months — revisions are logged, not hidden.",
                           "The full arc matters: ACA expansion, pandemic continuous-enrollment surge, the 2023 unwinding, and the current decline are all policy eras."])

    elif mid == "va_claims_backlog":
        if len(S) >= 5:
            own("VA claims backlog, weekly — claims pending >125 days", "count",
                rng=None, unit="Claims >125 days")
        else:
            accrue("VA claims backlog, weekly",
                   f"Live tracking starts now: {m['value']:,.0f} claims pending >125 days "
                   f"(week ending {pretty_date(m['as_of'])}), vs ~{(m.get('baseline') or {}).get('value', 257253):,.0f} "
                   "at inauguration. The weekly archive back to 2018 is being backfilled a batch "
                   "per day from VA’s own report files — the full curve (including the 418k peak "
                   "of Jan 2024) draws itself in as it lands.")
        fx.update(channels="direct — VA staffing, overtime, claims automation.",
                  limits="the backlog also falls when intake slows; the official definition (rating claims >125 days) excludes other queues — total pending is shown for context.",
                  caveats=["VA’s own backlog definition (rating claims pending >125 days), from the Monday Morning Workload Report; total pending shown alongside as the definition-gaming guard.",
                           "Education-claims data was absent from the reports Oct 2025–Jul 2026 (annotated, not estimated)."])

    # ---------------- Executive Power & Governance ----------------
    elif mid == "executive_orders":
        t2 = carry_forward(aligned_monthly(S, "trump2") or [])
        sers = [{"label": PRES["trump2"]["label"], "color": PRES["trump2"]["color"], "pts": t2}] if t2 else []
        prev = m.get("prev_terms") or {}
        for pid in ("biden", "obama"):
            pts = prev.get(pid)
            if pts:
                mm = carry_forward([[p["month"], p["value"]] for p in pts])
                sers.append({"label": PRES[pid]["label"], "color": PRES[pid]["color"], "pts": mm})
        dots = []
        if "biden" not in prev and m.get("comparison"):
            months_in = round((datetime.date.today() - T2_START).days / 30.4375, 1)
            dots = [{"x": min(months_in, TERM_MONTHS), "y": m["comparison"]["value"],
                     "label": f"Biden, same point ({num(m['comparison']['value'])})",
                     "color": PRES["biden"]["color"]}]
        aligned("Cumulative executive orders signed, by months in office", "count", sers,
                unit="Orders (cumulative)", dots=dots)
        fx.update(channels="entirely the president’s instrument.",
                  limits="orders direct the executive branch only; courts block or narrow many; a count measures activity, not effect.",
                  caveats=["Cumulative count of signed orders (Federal Register)."
                           + ("" if "biden" in prev else " Biden’s and Obama’s full monthly curves land with the next data run — until then the dot marks Biden’s total at the same point in term.")])

    elif mid == "judges_confirmed":
        al = m.get("aligned") or {}
        sers, dots = [], []
        for pid in ("trump2", "trump1", "biden"):
            pts = al.get(pid)
            if pts:
                sers.append({"label": PRES[pid]["label"], "color": PRES[pid]["color"],
                             "pts": carry_forward([[p["month"], p["value"]] for p in pts])})
        if not sers:
            t2 = carry_forward(aligned_monthly(S, "trump2") or [])
            if t2:
                sers = [{"label": PRES["trump2"]["label"], "color": PRES["trump2"]["color"], "pts": t2}]
            months_in = round((datetime.date.today() - T2_START).days / 30.4375, 1)
            if m.get("comparison"):
                dots.append({"x": min(months_in, TERM_MONTHS), "y": m["comparison"]["value"],
                             "label": f"Term 1 ({num(m['comparison']['value'])})",
                             "color": PRES["trump1"]["color"]})
            if m.get("biden_same_point") is not None:
                dots.append({"x": min(months_in, TERM_MONTHS), "y": m["biden_same_point"],
                             "label": f"Biden ({num(m['biden_same_point'])})",
                             "color": PRES["biden"]["color"]})
        aligned("Cumulative Article III judges confirmed, by months in office", "count", sers,
                unit="Judges (cumulative)", dots=dots)
        fx.update(channels="direct — the president nominates.",
                  limits="the Senate confirms on its own calendar; available vacancies set the ceiling; the count records confirmations, which commissions trail by days.",
                  caveats=["Counted by Senate confirmation date from the FJC’s directory of every federal judge since 1789 — the cleanest cross-president dataset on the board."])

    elif mid == "approval_rating":
        t2 = aligned_monthly([{"date": p["date"][:7], "value": p["value"]} for p in S], "trump2")
        if t2 and len(t2) >= 4:
            aligned("Approval, by months in office", "pct",
                    [{"label": PRES["trump2"]["label"], "color": PRES["trump2"]["color"], "pts": t2}],
                    unit="% approve")
        else:
            accrue("Presidential approval, weekly aggregate",
                   f"The weekly aggregate starts accruing now ({m['value']:.0f}% approve / "
                   f"{m.get('disapprove', 0):.0f}% disapprove as of {pretty_date(m['as_of'])}). "
                   "A sourced cross-president comparison (prior presidents at the same point in "
                   "term) is planned as a one-time historical import, clearly labelled as survey data.")
        fx.update(channels="public opinion responds to everything on this board — it is the electorate’s own scoreboard, not a government statistic.",
                  limits="poll aggregates smooth single-poll noise but inherit house effects and modelling choices; this is the board’s one survey-derived metric, labelled as such.",
                  caveats=["Simple average of recent national polls, one per pollster (VoteHub, CC-BY); the poll list is linked from the source. Opinion data, not a government statistic."])

    else:
        accrue(m.get("name", mid), "History for this metric accrues with each data run.")

    return fx


# ---- page -------------------------------------------------------------------
def _slug(cat):
    return cat.lower().replace(" & ", "-").replace(" ", "-")


def build():
    loaded = {}
    for f in glob.glob(os.path.join(DATA, "*.json")):
        try:
            d = json.load(open(f))
            # canonical v2 category (deterministic grouping even from data
            # files written before the Jul-2026 category migration)
            d["category"] = CATEGORIES.get(d["id"], d.get("category", ""))
            loaded[d["id"]] = d
        except Exception as e:
            print(f"  ! skipping {f}: {e}")

    metrics = [loaded[k] for k in ORDER if k in loaded]
    # ---- per-metric chart payloads -> site/d/<id>.json (fetched on expand) ----
    os.makedirs(SITE_D, exist_ok=True)
    payload_fail = []
    for m in metrics:
        try:
            fx = payload(m, loaded)
            with open(os.path.join(SITE_D, f"{m['id']}.json"), "w") as f:
                json.dump(fx, f, separators=(",", ":"))
        except Exception as e:
            payload_fail.append((m["id"], e))
            print(f"  ! payload failed for {m['id']}: {e} (card ships collapsed-only)")

    expandable = {m["id"] for m in metrics} - {mid for mid, _ in payload_fail}
    expand_btn = (
        '<button class="expand-btn" type="button" aria-expanded="false">'
        '<span>History &amp; context</span>'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<polyline points="6 9 12 15 18 9"></polyline></svg></button>'
        '<div class="detail" hidden></div>')

    # group by category, preserving ORDER within each; tabs with an All default
    sections, tab_btns = [], ['<button class="tab active" type="button" data-tab="all">All</button>']
    for cat in CATEGORY_ORDER:
        cat_metrics = [m for m in metrics if m["category"] == cat]
        if not cat_metrics:
            continue
        slug = _slug(cat)
        tiles = []
        for m in cat_metrics:
            h = tile(m)
            h = h.replace('<article class="tile" ',
                          f'<article class="tile" id="card-{m["id"]}" data-id="{m["id"]}" ', 1)
            if m["id"] in expandable:
                h = h.replace('<div class="tile-foot">', expand_btn + '\n      <div class="tile-foot">', 1)
            tiles.append(h)
        tab_btns.append(f'<button class="tab" type="button" data-tab="{slug}">{cat}</button>')
        sections.append(f"""
      <section class="category" data-tab="{slug}" id="{slug}">
        <h2 class="cat-head">{cat}<span class="cat-count">{len(cat_metrics)}</span></h2>
        <div class="grid">{"".join(tiles)}</div>
      </section>""")
    body = "".join(sections)
    tabs_html = "".join(tab_btns)

    chart_js = ""
    js_path = os.path.join(ASSETS, "chart.js")
    if os.path.exists(js_path):
        chart_js = open(js_path).read()
    else:
        print("  ! assets/chart.js missing — shipping collapsed-only board")

    live = len(metrics)
    built = datetime.datetime.utcnow().strftime("%b %-d, %Y %H:%M UTC")

    html = f"""<!doctype html>
<html lang="en" data-theme="dark" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trump Administration — Tracked in Data</title>
<style>
  :root {{
    --plane:#0d0d0d; --surface:#1a1a19; --primary:#ffffff; --secondary:#c3c2b7;
    --muted:#898781; --hair:rgba(255,255,255,0.10); --grid:#2c2c2a;
    --series-1:#3987e5; --critical:#d03b3b; --good:#0ca30c; --warn:#e0a83b;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--plane); color:var(--primary);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:56px 24px 80px; }}
  header {{ margin-bottom:36px; }}
  .kicker {{ color:var(--series-1); font-size:12px; letter-spacing:.14em; text-transform:uppercase; font-weight:600; }}
  h1 {{ font-size:30px; font-weight:650; margin:12px 0 10px; letter-spacing:-0.01em; }}
  .lede {{ color:var(--secondary); max-width:60ch; margin:0; }}
  .pilot {{ display:inline-block; margin-top:16px; font-size:12px; color:var(--muted);
           border:1px solid var(--hair); border-radius:100px; padding:5px 12px; }}
  .category {{ margin-top:40px; }}
  .cat-head {{ font-size:13px; font-weight:600; letter-spacing:.12em; text-transform:uppercase;
              color:var(--secondary); margin:0 0 16px; padding-bottom:10px;
              border-bottom:1px solid var(--hair); display:flex; align-items:center; gap:10px; }}
  .cat-count {{ color:var(--muted); font-weight:500; font-size:12px;
               border:1px solid var(--hair); border-radius:100px; padding:1px 8px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:18px; }}
  .tile {{ background:var(--surface); border:1px solid var(--hair); border-radius:16px; padding:24px 24px 18px; }}
  .tile.is-stale {{ border-color:rgba(224,168,59,0.45); }}
  .tile-cat {{ color:var(--muted); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:600; }}
  .tile-name {{ font-size:15px; font-weight:550; color:var(--secondary); margin:6px 0 14px; }}
  .hero {{ font-size:52px; font-weight:660; letter-spacing:-0.02em; line-height:1; }}
  .delta {{ display:block; font-size:13px; font-weight:550; margin-top:12px; }}
  .delta.bad {{ color:var(--critical); }}
  .delta.good {{ color:var(--good); }}
  .delta.neutral {{ color:var(--secondary); }}
  .freshness {{ display:flex; align-items:center; gap:10px; margin-top:10px; flex-wrap:wrap; }}
  .asof {{ font-size:12px; color:var(--secondary); font-weight:550; }}
  .stale-flag {{ font-size:11px; font-weight:600; color:var(--warn);
                border:1px solid rgba(224,168,59,0.4); border-radius:100px; padding:2px 8px; }}
  .tile-sub {{ color:var(--muted); font-size:12.5px; margin-top:8px; min-height:1.4em; }}
  .bars {{ margin:18px 0 6px; display:flex; flex-direction:column; gap:9px; }}
  .bar-row {{ display:grid; grid-template-columns:88px 1fr auto; align-items:center; gap:10px; }}
  .bar-label {{ color:var(--secondary); font-size:12px; }}
  .bar-track {{ background:var(--grid); border-radius:4px; height:10px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; }}
  .bar-val {{ color:var(--primary); font-size:12px; font-variant-numeric:tabular-nums; }}
  .tile-foot {{ display:flex; justify-content:space-between; align-items:center; gap:10px;
               margin-top:14px; padding-top:14px; border-top:1px solid var(--hair);
               font-size:11.5px; color:var(--muted); flex-wrap:wrap; }}
  .tile-foot a {{ color:var(--secondary); text-decoration:none; font-weight:550; }}
  .tile-foot a:hover {{ color:var(--series-1); }}
  /* ---- category tabs (All default; JS-off shows the whole board) ---- */
  .tabs {{ display:flex; gap:8px; overflow-x:auto; margin:30px 0 0; padding:2px 0 8px; scrollbar-width:none; }}
  .tabs::-webkit-scrollbar {{ display:none; }}
  .tab {{ white-space:nowrap; font-size:12.5px; font-weight:600; color:var(--secondary); background:none;
         border:1px solid var(--hair); border-radius:100px; padding:7px 14px; cursor:pointer; font-family:inherit; }}
  .tab:hover {{ color:var(--primary); border-color:rgba(255,255,255,0.28); }}
  .tab.active {{ color:var(--primary); border-color:var(--series-1); background:rgba(57,135,229,0.12); }}
  .no-js .tabs {{ display:none; }}
  .category[hidden] {{ display:none; }}

  /* ---- expandable cards ---- */
  .expand-btn {{ width:100%; margin-top:14px; background:none; font-family:inherit;
                border:1px solid var(--hair); border-radius:10px; color:var(--secondary);
                font-size:12px; font-weight:600; padding:8px 10px; cursor:pointer;
                display:flex; align-items:center; justify-content:center; gap:8px; }}
  .expand-btn:hover {{ color:var(--primary); border-color:rgba(255,255,255,0.3); }}
  .expand-btn svg {{ transition:transform .25s ease; }}
  .tile.open .expand-btn svg {{ transform:rotate(180deg); }}
  .no-js .expand-btn {{ display:none; }}
  .tile.open {{ grid-column:1 / -1; }}
  .detail {{ margin-top:18px; border-top:1px solid var(--hair); padding-top:18px; animation:reveal .28s ease; }}
  .detail[hidden] {{ display:none; }}
  @keyframes reveal {{ from {{ opacity:0; transform:translateY(-4px); }} to {{ opacity:1; transform:none; }} }}
  .chart-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:10px; }}
  .chart-title {{ font-size:13px; font-weight:600; color:var(--secondary); }}
  .chart-ctrl {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .ctrl-btn {{ font-size:11.5px; font-weight:600; color:var(--muted); background:none; font-family:inherit;
              border:1px solid var(--hair); border-radius:8px; padding:4px 10px; cursor:pointer; }}
  .ctrl-btn:hover {{ color:var(--primary); }}
  .ctrl-btn.active {{ color:var(--primary); border-color:var(--series-1); background:rgba(57,135,229,0.12); }}
  .legend {{ display:flex; gap:14px; flex-wrap:wrap; margin:0 0 8px; }}
  .lg {{ display:flex; align-items:center; gap:7px; font-size:12px; color:var(--secondary); font-weight:550; }}
  .lg .key {{ width:14px; height:0; border-top:2.5px solid; border-radius:2px; }}
  .chart-box {{ position:relative; outline:none; border-radius:8px; }}
  .chart-box:focus-visible {{ box-shadow:0 0 0 2px rgba(57,135,229,0.5); }}
  .chart-box svg {{ display:block; }}
  .chart-box svg text {{ font-family:inherit; }}
  .tooltip {{ position:absolute; pointer-events:none; background:#232322; border:1px solid var(--hair);
             border-radius:10px; padding:8px 11px; font-size:12px; display:none; z-index:5;
             box-shadow:0 6px 20px rgba(0,0,0,0.5); min-width:120px; }}
  .tt-x {{ color:var(--muted); font-size:11px; margin-bottom:2px; font-weight:600; }}
  .tt-row {{ display:flex; align-items:center; gap:7px; margin-top:4px; }}
  .tt-key {{ width:11px; border-top:2.5px solid; border-radius:2px; flex:none; }}
  .tt-val {{ font-weight:650; color:var(--primary); font-variant-numeric:tabular-nums; }}
  .tt-lab {{ color:var(--secondary); font-size:11.5px; }}
  .dtable {{ max-height:280px; overflow:auto; border:1px solid var(--hair); border-radius:10px; }}
  .dtable table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  .dtable th {{ position:sticky; top:0; background:var(--surface); text-align:right; padding:7px 12px;
               color:var(--muted); font-weight:600; border-bottom:1px solid var(--hair); }}
  .dtable th:first-child, .dtable td:first-child {{ text-align:left; }}
  .dtable td {{ padding:5px 12px; text-align:right; color:var(--secondary);
               font-variant-numeric:tabular-nums; border-bottom:1px solid rgba(255,255,255,0.04); }}
  .accrue {{ border:1px dashed rgba(255,255,255,0.18); border-radius:12px; padding:28px 22px;
            text-align:center; color:var(--muted); font-size:12.5px; }}
  .accrue b {{ display:block; color:var(--secondary); font-size:13px; margin-bottom:6px; font-weight:600; }}
  .furniture {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:16px; }}
  @media (max-width:720px) {{ .furniture {{ grid-template-columns:1fr; }} }}
  .fbox {{ background:rgba(255,255,255,0.03); border:1px solid var(--hair); border-radius:12px; padding:14px 16px; }}
  .fbox h4 {{ margin:0 0 8px; font-size:11px; letter-spacing:.1em; text-transform:uppercase;
             color:var(--muted); font-weight:650; }}
  .fbox p {{ margin:0; font-size:12.5px; color:var(--secondary); line-height:1.55; }}
  .fbox p + p {{ margin-top:7px; }}
  .fbox .flabel {{ font-weight:650; color:var(--primary); }}
  .detail-meta {{ display:flex; gap:6px 18px; flex-wrap:wrap; margin-top:14px; font-size:11.5px;
                 color:var(--muted); align-items:center; }}
  .detail-meta a {{ color:var(--secondary); font-weight:550; text-decoration:none; }}
  .detail-meta a:hover {{ color:var(--series-1); }}

  footer {{ margin-top:48px; color:var(--muted); font-size:12px; max-width:70ch; }}
  footer a {{ color:var(--secondary); }}
  .built {{ opacity:.6; font-size:11px; margin-top:14px; }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="kicker">United States · Trump Administration</div>
      <h1>The record, tracked in data</h1>
      <p class="lede">Official, sourced metrics — pulled automatically from government data, shown with history and comparisons. Every number links to its primary source. You draw the conclusions.</p>
      <div class="pilot">Pilot · {live} of {TOTAL_PLANNED} planned metrics</div>
    </header>
    <nav class="tabs" id="tabs" aria-label="Categories">{tabs_html}</nav>
    <main>
      {body}
    </main>
    <footer>
      Each figure is collected automatically from an authoritative source and shown against a comparison so a single number has context. Favourable and unfavourable numbers are shown alike, and nothing is removed when it moves in either direction. Each card shows its own data date and flags itself when a figure is older than its source's normal update schedule. Expanded charts show the full stored history — gaps in official publication render as gaps, definition changes are marked on the chart, and every chart can be read as a table or downloaded as the exact data served.
      <div class="built">Site rebuilt {built}. Freshness is judged per metric (see each card's date), not by this build time.</div>
    </footer>
  </div>
  <script>
%%CHARTJS%%
  </script>
</body>
</html>"""
    html = html.replace("%%CHARTJS%%", chart_js)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(html)
    print("wrote", OUT, f"({len(html)} bytes, {live} metrics, "
          f"{len(expandable)} expandable, {len(os.listdir(SITE_D))} series payloads)")
    if payload_fail:
        print(f"  ! {len(payload_fail)} payload(s) failed — board still shipped")


if __name__ == "__main__":
    build()
