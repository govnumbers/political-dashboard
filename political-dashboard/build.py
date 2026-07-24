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

TOTAL_PLANNED = 15
CATEGORY_ORDER = ["Economy", "Public Finances", "Executive Power", "Immigration"]
ORDER = [
    "inflation", "unemployment", "gas_price", "trade_deficit",
    "national_debt", "budget_deficit",
    "executive_orders",
    "border_encounters", "ice_detention",
]
STALE_DAYS = {"biweek": 30, "as signed": 12, "as-signed": 12, "dai": 5, "week": 14, "month": 55}
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
        delta = '<span class="delta neutral">Average daily population in ICE detention</span>'

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


# ---- page -------------------------------------------------------------------
def build():
    loaded = {}
    for f in glob.glob(os.path.join(DATA, "*.json")):
        try:
            d = json.load(open(f))
            loaded[d["id"]] = d
        except Exception as e:
            print(f"  ! skipping {f}: {e}")

    metrics = [loaded[k] for k in ORDER if k in loaded]
    # group by category, preserving ORDER within each
    sections = []
    for cat in CATEGORY_ORDER:
        cat_metrics = [m for m in metrics if m["category"] == cat]
        if not cat_metrics:
            continue
        tiles = "".join(tile(m) for m in cat_metrics)
        sections.append(f"""
      <section class="category">
        <h2 class="cat-head">{cat}<span class="cat-count">{len(cat_metrics)}</span></h2>
        <div class="grid">{tiles}</div>
      </section>""")
    body = "".join(sections)

    live = len(metrics)
    built = datetime.datetime.utcnow().strftime("%b %-d, %Y %H:%M UTC")

    html = f"""<!doctype html>
<html lang="en" data-theme="dark">
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
    <main>
      {body}
    </main>
    <footer>
      Each figure is collected automatically from an authoritative source and shown against a comparison so a single number has context. Favourable and unfavourable numbers are shown alike, and nothing is removed when it moves in either direction. Each card shows its own data date and flags itself when a figure is older than its source's normal update schedule.
      <div class="built">Site rebuilt {built}. Freshness is judged per metric (see each card's date), not by this build time.</div>
    </footer>
  </div>
  <script>
    // Client-side freshness: flag any card past its stale_after date, judged
    // against the visitor's clock so it stays honest even if the pipeline stops
    // and this page freezes.
    (function () {{
      var now = new Date();
      document.querySelectorAll('.tile[data-stale-after]').forEach(function (el) {{
        var sa = new Date(el.getAttribute('data-stale-after') + 'T23:59:59Z');
        if (isNaN(sa)) return;
        if (now > sa) {{
          el.classList.add('is-stale');
          var f = el.querySelector('.stale-flag');
          if (f) f.hidden = false;
        }}
      }});
    }})();
  </script>
</body>
</html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(html)
    print("wrote", OUT, f"({len(html)} bytes, {live} metrics)")


if __name__ == "__main__":
    build()
