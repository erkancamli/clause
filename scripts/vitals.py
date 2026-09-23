"""What the page costs a person on a cheap phone on a slow connection.

    python3 scripts/vitals.py http://127.0.0.1:8000           the usual routes
    python3 scripts/vitals.py http://127.0.0.1:8000 /cover    only this one
    python3 scripts/vitals.py http://127.0.0.1:8000 --fast    no throttling

Against a laptop on fibre every page is instant, which is why a site can
spend four seconds of somebody's morning for weeks without anyone noticing.
This drives a browser with the processor slowed four times and the line held
to 1.6 Mbit, which is roughly a mid-range Android on a bad cell, and reports
the three measures Google's Core Web Vitals are made of:

  LCP  when the largest thing on the screen finished drawing   good < 2.5 s
  CLS  how far the page moved under the reader's eyes          good < 0.1
  INP  is an interaction measure and is not taken here; the longest task is
       reported instead, because a main thread busy for half a second is
       what makes a tap feel ignored.

Neither Playwright nor a browser is a dependency of this project: both are
for whoever is measuring, and the browser is whatever Playwright has put
under PLAYWRIGHT_BROWSERS_PATH.
"""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys

ROUTES = ["/", "/cover", "/mine", "/how", "/proof"]
RUNS = 3

PROBE = """
window.__lcp=0; window.__lcpel=''; window.__cls=0; window.__long=[];
new PerformanceObserver(function(l){ l.getEntries().forEach(function(e){
  window.__lcp=Math.round(e.startTime);
  window.__lcpel=e.element?(e.element.tagName.toLowerCase()+(e.element.id?'#'+e.element.id:'')):'';
});}).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(function(l){ l.getEntries().forEach(function(e){
  if(!e.hadRecentInput) window.__cls+=e.value;
});}).observe({type:'layout-shift',buffered:true});
new PerformanceObserver(function(l){ l.getEntries().forEach(function(e){
  window.__long.push(Math.round(e.duration));
});}).observe({type:'longtask',buffered:true});
"""

READ = """() => {
  const nav = performance.getEntriesByType('navigation')[0];
  const fcp = performance.getEntriesByName('first-contentful-paint')[0];
  const res = performance.getEntriesByType('resource');
  return {
    ttfb: Math.round(nav.responseStart),
    fcp: fcp ? Math.round(fcp.startTime) : 0,
    lcp: window.__lcp, lcpel: window.__lcpel,
    cls: Math.round(window.__cls*1000)/1000,
    task: window.__long.length ? Math.max.apply(null, window.__long) : 0,
    slow: window.__long.filter(d => d > 50).length,
    reqs: res.length + 1,
    kb: Math.round((nav.encodedBodySize + res.reduce((s,r)=>s+r.encodedBodySize,0))/1024),
  };
}"""


def browser_path() -> str | None:
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    found = sorted(glob.glob(os.path.join(root, "chromium*", "chrome-linux", "chrome")))
    return found[0] if found else None


def main() -> int:
    from playwright.sync_api import sync_playwright

    args = sys.argv[1:]
    base = next((a for a in args if a.startswith("http")), "http://127.0.0.1:8000")
    routes = [a for a in args if a.startswith("/")] or ROUTES
    fast = "--fast" in args

    rows = []
    with sync_playwright() as play:
        browser = play.chromium.launch(executable_path=browser_path())
        for route in routes:
            takes = []
            for _ in range(RUNS):
                # A fresh context every run: a warm cache measures the second
                # visit, and the first visit is the one that loses people.
                context = browser.new_context(viewport={"width": 390, "height": 844})
                page = context.new_page()
                page.add_init_script(PROBE)
                if not fast:
                    cdp = context.new_cdp_session(page)
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    cdp.send("Network.enable")
                    cdp.send("Network.emulateNetworkConditions", {
                        "offline": False, "latency": 150,
                        "downloadThroughput": int(1.6 * 1024 * 1024 / 8),
                        "uploadThroughput": int(750 * 1024 / 8)})
                page.goto(base.rstrip("/") + "/#" + route, wait_until="load")
                page.wait_for_timeout(3000)
                takes.append(page.evaluate(READ))
                context.close()
            # The middle run of three, so that one unlucky garbage collection
            # does not become the number anybody quotes.
            middle = {k: (statistics.median([t[k] for t in takes]) if isinstance(takes[0][k], (int, float))
                          else takes[0][k]) for k in takes[0]}
            middle["route"] = route
            rows.append(middle)
        browser.close()

    if "--json" in sys.argv:
        print(json.dumps(rows, indent=1))
        return 0
    print(f"{'route':<9}{'TTFB':>6}{'FCP':>7}{'LCP':>7}{'CLS':>7}{'task':>7}{'>50ms':>7}{'reqs':>6}{'KB':>6}  largest")
    bad = 0
    for r in rows:
        flag = ""
        if r["lcp"] > 2500 or r["cls"] > 0.1:
            flag = "  <-- over budget"
            bad += 1
        print(f"{r['route']:<9}{r['ttfb']:>5.0f}ms{r['fcp']:>6.0f}ms{r['lcp']:>6.0f}ms"
              f"{r['cls']:>7.3f}{r['task']:>6.0f}ms{r['slow']:>7.0f}{r['reqs']:>6.0f}{r['kb']:>6.0f}"
              f"  {r['lcpel']}{flag}")
    print("\nbudget: LCP under 2.5 s, CLS under 0.1, on a four-times-slowed phone at 1.6 Mbit")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
