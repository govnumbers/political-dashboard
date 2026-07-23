#!/usr/bin/env python3
"""Build the static dashboard from data/*.json. No network needed."""
import json, glob, os, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "site", "index.html")

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

# ---- per-metric render ------------------------------------------------------
def render_bars(rows, accent):
    mx = max(r[1] for r in rows) or 1
    out = []
    for label, val, disp, tone in rows:
        w = max(2, round(val / mx * 100))
        color = {"accent": accent, "muted": "var(--muted)", "critical": "var(--critical)"}[tone]
        out.append(f"""
        <div class="bar-row">
          <div class="bar-label">{label}</div>
          <div class="bar-track"><div class="bar-fill" style="width:{w}%;background:{color}"></div></div>
          <div class="bar-val">{disp}</div>
        </div>""")
    return "".join(out)

def tile(m):
    cat = m["category"]
    name = m["name"]
    src = m["source"]
    accent = "var(--series-1)"

    if m["id"] == "executive_orders":
        hero = num(m["value"])
        comp = m["comparison"]
        delta = f'<span class="delta neutral">{num(m["value"]-comp["value"])} more than Biden ({num(comp["value"])}) at the same point</span>'
        bars = render_bars([
            ("Trump", m["value"], num(m["value"]), "accent"),
            ("Biden", comp["value"], num(comp["value"]), "muted"),
        ], accent)
        sub = "Since inauguration · " + pretty_date(m["since"])

    elif m["id"] == "national_debt":
        hero = money_compact(m["value"])
        base = m["baseline"]
        inc = m["value"] - base["value"]
        pct = inc / base["value"] * 100
        delta = f'<span class="delta bad">&#9650; {money_compact(inc)} (+{pct:.1f}%) since inauguration</span>'
        bars = render_bars([
            ("Now", m["value"], money_compact(m["value"]), "critical"),
            ("Inauguration", base["value"], money_compact(base["value"]), "muted"),
        ], accent)
        sub = "Total public debt outstanding"

    elif m["id"] == "inflation":
        hero = f'{m["value"]}%'
        tgt = m["target"]
        gap = m["value"] - tgt["value"]
        delta = f'<span class="delta bad">&#9650; {gap:.1f} pts above the Fed&#39;s {tgt["value"]}% target</span>'
        bars = render_bars([
            ("CPI (YoY)", m["value"], f'{m["value"]}%', "critical"),
            ("Fed target", tgt["value"], f'{tgt["value"]}%', "muted"),
        ], accent)
        sub = m["note"]

    elif m["id"] == "unemployment":
        hero = f'{m["value"]}%'
        base = m["baseline"]; diff = m["value"] - base["value"]
        delta = f'<span class="delta bad">&#9650; {diff:.1f} pts since inauguration ({base["value"]}%)</span>'
        bars = render_bars([
            ("Now", m["value"], f'{m["value"]}%', "critical"),
            ("Inauguration", base["value"], f'{base["value"]}%', "muted"),
        ], accent)
        sub = m["note"]

    elif m["id"] == "gas_price":
        hero = f'${m["value"]:.2f}'
        base = m["baseline"]; diff = m["value"] - base["value"]; pct = diff / base["value"] * 100
        delta = f'<span class="delta bad">&#9650; ${diff:.2f} (+{pct:.0f}%) since inauguration</span>'
        bars = render_bars([
            ("Now", m["value"], f'${m["value"]:.2f}', "critical"),
            ("Inauguration", base["value"], f'${base["value"]:.2f}', "muted"),
        ], accent)
        sub = m["note"].split(".")[0]

    elif m["id"] == "trade_deficit":
        hero = f'${m["value"]:.1f}B'
        base = m["baseline"]; diff = m["value"] - base["value"]; pct = diff / base["value"] * 100
        delta = f'<span class="delta bad">&#9650; ${diff:.1f}B (+{pct:.0f}%) vs the prior month</span>'
        bars = render_bars([
            ("May", m["value"], f'${m["value"]:.1f}B', "critical"),
            ("April", base["value"], f'${base["value"]:.1f}B', "muted"),
        ], accent)
        sub = m["note"]

    else:
        hero = str(m.get("value", "")); delta = ""; bars = ""; sub = m.get("note", "")

    return f"""
    <article class="tile">
      <div class="tile-cat">{cat}</div>
      <h2 class="tile-name">{name}</h2>
      <div class="hero">{hero}</div>
      {delta}
      <div class="tile-sub">{sub}</div>
      <div class="bars">{bars}</div>
      <div class="tile-foot">
        <a href="{src['url']}" target="_blank" rel="noopener">{src['name']} &#8599;</a>
        <span>as of {pretty_date(m['as_of'])} · updates {m['cadence'].lower()}</span>
      </div>
    </article>"""

# ---- page -------------------------------------------------------------------
def build():
    metrics = []
    order = ["executive_orders", "national_debt", "inflation", "unemployment", "gas_price", "trade_deficit"]
    loaded = {json.load(open(f))["id"]: json.load(open(f)) for f in glob.glob(os.path.join(DATA, "*.json"))}
    for k in order:
        if k in loaded: metrics.append(loaded[k])
    tiles = "".join(tile(m) for m in metrics)
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
    --series-1:#3987e5; --critical:#d03b3b; --good:#0ca30c;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--plane); color:var(--primary);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif; line-height:1.5;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:56px 24px 80px; }}
  header {{ margin-bottom:44px; }}
  .kicker {{ color:var(--series-1); font-size:12px; letter-spacing:.14em; text-transform:uppercase; font-weight:600; }}
  h1 {{ font-size:30px; font-weight:650; margin:12px 0 10px; letter-spacing:-0.01em; }}
  .lede {{ color:var(--secondary); max-width:60ch; margin:0; }}
  .pilot {{ display:inline-block; margin-top:16px; font-size:12px; color:var(--muted);
           border:1px solid var(--hair); border-radius:100px; padding:5px 12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:18px; }}
  .tile {{ background:var(--surface); border:1px solid var(--hair); border-radius:16px; padding:24px 24px 18px; }}
  .tile-cat {{ color:var(--muted); font-size:11px; letter-spacing:.12em; text-transform:uppercase; font-weight:600; }}
  .tile-name {{ font-size:15px; font-weight:550; color:var(--secondary); margin:6px 0 14px; }}
  .hero {{ font-size:52px; font-weight:660; letter-spacing:-0.02em; line-height:1; }}
  .delta {{ display:block; font-size:13px; font-weight:550; margin-top:12px; }}
  .delta.bad {{ color:var(--critical); }}
  .delta.good {{ color:var(--good); }}
  .delta.neutral {{ color:var(--secondary); }}
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
  footer {{ margin-top:40px; color:var(--muted); font-size:12px; max-width:70ch; }}
  footer a {{ color:var(--secondary); }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="kicker">United States · Trump Administration</div>
      <h1>The record, tracked in data</h1>
      <p class="lede">Official, sourced metrics — pulled automatically from government data, shown with history and comparisons. Every number links to its primary source. You draw the conclusions.</p>
      <div class="pilot">Pilot · 6 of 15 planned metrics</div>
    </header>
    <main class="grid">
      {tiles}
    </main>
    <footer>
      Each figure is collected automatically from an authoritative source and shown against a comparison so a single number has context. Favourable and unfavourable numbers are shown alike, and nothing is removed when it moves in either direction.
      <br><br>Built {built}.
    </footer>
  </div>
</body>
</html>"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(html)
    print("wrote", OUT, f"({len(html)} bytes)")

if __name__ == "__main__":
    build()
