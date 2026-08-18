#!/usr/bin/env python3
"""Phase-7 QA harness (offline): serve site/ locally, expand every card,
fail on any console error, screenshot key states. Not part of the deploy."""
import asyncio
import http.server
import json
import os
import threading
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
OUT = os.path.join(HERE, "qa_shots")
PORT = 8377

IDS = json.load(open(os.path.join(HERE, "metrics.json")))["metrics"]
IDS = [m["id"] for m in IDS]
IDS = [{"gas": "gas_price"}.get(i, i) for i in IDS]


def serve():
    os.chdir(SITE)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main():
    os.makedirs(OUT, exist_ok=True)
    serve()
    errors, failures = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page(viewport={"width": 1280, "height": 900})
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        pg.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
        await pg.goto(f"http://127.0.0.1:{PORT}/")
        await pg.wait_for_timeout(400)
        await pg.screenshot(path=f"{OUT}/01-top.png")

        # expand every card; each must produce a chart, bars, table, or accrue state
        for mid in IDS:
            btn = await pg.query_selector(f"#card-{mid} .expand-btn")
            if not btn:
                failures.append(f"{mid}: no expand button")
                continue
            await pg.eval_on_selector(f"#card-{mid} .expand-btn", "b => b.click()")
            await pg.wait_for_timeout(250)
            got = await pg.eval_on_selector(
                f"#card-{mid} .detail",
                "d => ({svg: !!d.querySelector('svg'), accrue: !!d.querySelector('.accrue'),"
                " furniture: !!d.querySelector('.furniture'), meta: !!d.querySelector('.detail-meta')})")
            if not (got["svg"] or got["accrue"]):
                failures.append(f"{mid}: no chart and no accrue state")
            if not got["furniture"] or not got["meta"]:
                failures.append(f"{mid}: missing furniture/meta")

        # visual spot checks (the recolored president charts + key states)
        for mid, name in [("national_debt", "02-debt-red-blue"),
                          ("federal_workforce", "03-workforce-4pres"),
                          ("executive_orders", "04-eo-red-line"),
                          ("border_encounters", "05-border"),
                          ("ice_removals", "06-ice-annual-bars"),
                          ("real_gdp", "07-gdp-index"),
                          ("tariff_revenue", "08-tariff"),
                          ("va_claims_backlog", "09-va-accrue"),
                          ("inflation", "10-inflation")]:
            el = await pg.query_selector(f"#card-{mid}")
            if el:
                await el.screenshot(path=f"{OUT}/{name}.png")

        # every payload fetch must have succeeded (no failed d/*.json)
        misses = await pg.evaluate(
            "Array.from(document.querySelectorAll('.tile[data-id]'))"
            ".filter(c => c.classList.contains('open') && !c._fx).map(c => c.dataset.id)")
        for mid in misses:
            failures.append(f"{mid}: payload fetch failed")

        # table view via the demoted "values" link still works post-redesign
        await pg.eval_on_selector("#card-national_debt", """c => {
            [...c.querySelectorAll('.detail-meta a')].find(b => b.textContent === 'Table').click(); }""")
        await pg.wait_for_timeout(150)
        has_table = await pg.eval_on_selector("#card-national_debt", "c => !!c.querySelector('.dtable table')")
        if not has_table:
            failures.append("debt: values/table view missing")

        # tabs: Immigration filter + deep link
        await pg.eval_on_selector('[data-tab="immigration"]', "b => b.click()")
        await pg.wait_for_timeout(150)
        vis = await pg.evaluate(
            "Array.from(document.querySelectorAll('.category:not([hidden])')).map(s => s.dataset.tab)")
        if vis != ["immigration"]:
            failures.append(f"tab filter wrong: {vis}")
        await pg.goto(f"http://127.0.0.1:{PORT}/#m/measles_cases")
        await pg.wait_for_timeout(500)
        open_ok = await pg.eval_on_selector("#card-measles_cases", "c => c.classList.contains('open')")
        if not open_ok:
            failures.append("deep link #m/measles_cases did not expand")
        await pg.screenshot(path=f"{OUT}/11-deeplink-measles.png")

        # JS disabled: whole board visible, no expand affordances, no tabs
        ctx = await browser.new_context(java_script_enabled=False)
        pn = await ctx.new_page()
        await pn.goto(f"http://127.0.0.1:{PORT}/")
        await pn.wait_for_timeout(200)
        nojs = await pn.evaluate(
            "({tabs: getComputedStyle(document.querySelector('.tabs')).display,"
            "  btn: getComputedStyle(document.querySelector('.expand-btn')).display,"
            "  cards: document.querySelectorAll('.tile').length,"
            "  sections: document.querySelectorAll('.category:not([hidden])').length})")
        if not (nojs["tabs"] == "none" and nojs["btn"] == "none"
                and nojs["cards"] == len(IDS) and nojs["sections"] >= 7):
            failures.append(f"JS-off degradation wrong: {nojs}")
        await pn.screenshot(path=f"{OUT}/12-nojs.png")
        await ctx.close()

        # mobile
        pm = await browser.new_page(viewport={"width": 390, "height": 844})
        await pm.goto(f"http://127.0.0.1:{PORT}/#m/national_debt")
        await pm.wait_for_timeout(600)
        await (await pm.query_selector("#card-national_debt")).screenshot(path=f"{OUT}/13-mobile-debt.png")

        await browser.close()

    print("console errors:", errors if errors else "none")
    print("failures:", failures if failures else "none")
    print("payload sizes:",
          {f: os.path.getsize(os.path.join(SITE, 'd', f)) // 1024 for f in sorted(os.listdir(os.path.join(SITE, 'd')))[:5]}, "…")
    print("homepage KB:", os.path.getsize(os.path.join(SITE, "index.html")) // 1024)
    return 1 if (errors or failures) else 0


raise SystemExit(asyncio.run(main()))
