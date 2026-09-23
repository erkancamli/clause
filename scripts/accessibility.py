"""Every page, in every language, at three widths, through Deque's axe.

    python3 scripts/accessibility.py            the whole sweep
    python3 scripts/accessibility.py --quick    one language, two widths

Colour, landmarks, heading order and keyboard reach are the parts of an
interface that look finished while being wrong, and looking at them is how
they stay wrong: the fade that put the home page's own words at 2.2 to 1
against the background had been there for weeks and read as a design choice.
This does not look. It runs the rules.

What it needs, and why neither is a dependency of this project: a browser,
which Playwright provides, and axe-core, which is fetched from npm into
.axe/ the first time and kept there. Both are for whoever is auditing, not
for the server, so neither belongs in pyproject.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / ".axe"
ROUTES = ["/", "/cover", "/mine", "/proof", "/how", "/pool", "/company", "/privacy",
          "/rules", "/faq", "/admin", "/profile"]
LANGS = ["en", "tr", "es", "fr", "de", "ru", "ja"]
WIDTHS = [(390, 844), (768, 1024), (1440, 900)]
#: Everything WCAG 2.0, 2.1 and 2.2 ask for at A and AA, and Deque's own
#: practice rules on top, because several of them are the ones that matter.
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]
IMPACT = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, None: 4}


def axe_source() -> str:
    """The engine, fetched once and kept in .axe/."""
    found = next(CACHE.glob("package/axe.min.js"), None)
    if found is None:
        CACHE.mkdir(exist_ok=True)
        print("fetching axe-core from npm…", file=sys.stderr)
        name = subprocess.run(["npm", "pack", "axe-core@latest", "--silent"],
                              cwd=CACHE, capture_output=True, text=True, check=True).stdout.strip()
        with tarfile.open(CACHE / name.splitlines()[-1]) as tar:
            tar.extractall(CACHE)
        found = next(CACHE.glob("package/axe.min.js"))
    return found.read_text()


def a_browser() -> dict[str, str]:
    """Whatever Chromium is actually on this machine.

    Playwright pins a build number and refuses anything else, which is right
    for a test that must reproduce and wrong for an audit that should run
    wherever somebody has a browser. If one is installed under the path
    Playwright was told to look in, that one is used by name.
    """
    import os
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if root.is_dir():
        for candidate in sorted(root.glob("chromium*/chrome-linux/chrome"), reverse=True):
            return {"executable_path": str(candidate)}
    return {}


def sweep(base: str, quick: bool = False) -> dict[str, list[dict]]:
    from playwright.sync_api import sync_playwright

    engine = axe_source()
    langs = ["en"] if quick else LANGS
    widths = WIDTHS[::2] if quick else WIDTHS
    found: dict[str, list[dict]] = defaultdict(list)
    pages = 0
    with sync_playwright() as play:
        browser = play.chromium.launch(**a_browser())
        for lang in langs:
            for width, height in widths:
                page = browser.new_page(viewport={"width": width, "height": height})
                for route in ROUTES:
                    try:
                        page.goto(f"{base}/?lang={lang}#{route}", wait_until="domcontentloaded")
                        page.wait_for_timeout(1300)
                        page.add_script_tag(content=engine)
                        result = page.evaluate(
                            "tags => axe.run(document, {runOnly:{type:'tag', values:tags}})", TAGS)
                    except Exception as error:
                        found["__error__"].append({"where": f"{lang} {width} {route}",
                                                   "why": f"{type(error).__name__}: {error}"})
                        continue
                    pages += 1
                    for rule in result["violations"]:
                        for node in rule["nodes"]:
                            found[rule["id"]].append({
                                "impact": rule["impact"], "help": rule["help"],
                                "where": f"{lang} {width} {route}",
                                "target": (node.get("target") or [""])[0],
                                "html": (node.get("html") or "")[:160],
                                "why": (node.get("failureSummary") or "").replace("\n", " ")[:220]})
                page.close()
        browser.close()
    found["__pages__"] = [{"count": pages}]
    return found


def report(found: dict[str, list[dict]]) -> int:
    pages = found.pop("__pages__", [{"count": 0}])[0]["count"]
    print(f"pages checked: {pages}")
    if not found:
        print("no violations")
        return 0
    rows = sorted(found.items(),
                  key=lambda kv: (IMPACT.get(kv[1][0].get("impact"), 4), -len(kv[1])))
    for rule, hits in rows:
        if rule == "__error__":
            print(f"\n!! could not check {len(hits)} pages")
            for hit in hits[:5]:
                print(f"   {hit['where']}: {hit['why']}")
            continue
        first = hits[0]
        print(f"\n[{first['impact']}] {rule} — {len(hits)} nodes")
        print(f"   {first['help']}")
        print(f"   routes: {', '.join(sorted({h['where'].split()[-1] for h in hits}))}")
        print(f"   langs:  {', '.join(sorted({h['where'].split()[0] for h in hits}))}")
        print(f"   widths: {', '.join(sorted({h['where'].split()[1] for h in hits}))}")
        print(f"   e.g. {first['target']}  ::  {first['html'][:110]}")
        print(f"   why: {first['why'][:180]}")
    return 1


def main() -> int:
    args = sys.argv[1:]
    base = next((a for a in args if a.startswith("http")), "http://127.0.0.1:8000")
    return report(sweep(base, quick="--quick" in args))


if __name__ == "__main__":
    raise SystemExit(main())
