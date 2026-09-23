"""The six rules the engine cannot check, checked anyway.

    python3 scripts/beyond_axe.py http://127.0.0.1:8000
    python3 scripts/beyond_axe.py http://127.0.0.1:8000 --full     seven languages
    python3 scripts/beyond_axe.py http://127.0.0.1:8000 --only reflow,target

axe-core's own README claims it finds "on average 57% of WCAG issues", and
parsing its rule index shows those rules reach 23 of the 55 A and AA success
criteria. The other 32 are not softer requirements. They are the ones that
need a viewport resized, a stylesheet forced in, a key pressed, or two
rectangles compared -- work a rule engine reading one static document cannot
do, which is exactly why they survive a sweep that comes back empty.

Six of the 32 are mechanical enough to be a script rather than a morning:

  1.4.10 Reflow             320 css px, and 1280 at 400% -- no sideways scroll
  1.4.12 Text Spacing       the four properties forced in, nothing clipped
  2.4.11 Focus Not Obscured a focused control is not under a sticky bar
  2.5.8  Target Size        24 css px, or the spacing exception's circles
  2.4.7  Focus Visible      focusing a control changes what is on the screen
  2.4.3  Focus Order        every control reachable, and in the order it reads

Each one prints what failed, where, and by how much, because "fails 2.5.8" is
not something anybody can fix and "22 px, needs 24" is.

Neither Playwright nor a browser is a dependency of this project: both are for
whoever is auditing, and the browser is whatever Playwright has put under
PLAYWRIGHT_BROWSERS_PATH.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

ROUTES = ["/", "/cover", "/mine", "/proof", "/how", "/pool", "/company", "/privacy",
          "/rules", "/faq", "/admin", "/profile"]
LANGS = ["en", "tr", "es", "fr", "de", "ru", "ja"]
CHECKS = ["reflow", "spacing", "obscured", "target", "visible", "order"]
#: 320 because the criterion says so, and then a width on either side of every
#: breakpoint this stylesheet has, because a breakpoint is where a layout was
#: told to change its mind and those are the places it changes it wrongly.
WIDTHS = [(320, 256), (360, 740), (390, 844), (412, 900), (430, 932), (480, 800),
          (520, 800), (560, 800), (600, 900), (640, 900), (700, 900), (760, 900),
          (780, 900), (820, 1000), (860, 1000), (900, 1000), (1000, 900),
          (1120, 900), (1180, 900), (1280, 900), (1440, 900)]

#: 1.4.12's four values, exactly as the criterion states them.
TEXT_SPACING = """
  *, *::before, *::after {
    line-height: 1.5 !important;
    letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important;
  }
  p { margin-bottom: 2em !important; }
"""


def a_browser() -> dict[str, str]:
    """Whatever Chromium is actually on this machine."""
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if root.is_dir():
        for candidate in sorted(root.glob("chromium*/chrome-linux/chrome"), reverse=True):
            return {"executable_path": str(candidate)}
    return {}


# ---------------------------------------------------------------- 1.4.10 ----

REFLOW = """() => {
  const doc = document.documentElement;
  const over = doc.scrollWidth - doc.clientWidth;
  if (over <= 1) return null;
  // Naming the widest thing is the difference between a number and a fix.
  let worst = null;
  for (const el of document.querySelectorAll('body *')) {
    const box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) continue;
    if (box.right <= doc.clientWidth + 1) continue;
    const past = box.right - doc.clientWidth;
    if (!worst || past > worst.past) {
      worst = {past: Math.round(past),
               what: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
                     (el.className && typeof el.className === 'string'
                        ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '')};
    }
  }
  return {over: Math.round(over), worst};
}"""


# ---------------------------------------------------------------- 1.4.12 ----

CLIPPED = """() => {
  // F104: text cut off by a box that was sized for the old line height.
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const style = getComputedStyle(el);
    if (style.overflowY !== 'hidden' && style.overflow !== 'hidden') continue;
    if (!el.textContent.trim()) continue;
    // Clipping is the whole point of a visually hidden label; it is read,
    // not seen, and 1.4.12 is about what a sighted reader loses.
    const box = el.getBoundingClientRect();
    if (box.height <= 2 || box.width <= 2) continue;
    if (style.clipPath && style.clipPath !== 'none') continue;
    const cut = el.scrollHeight - el.clientHeight;
    if (cut <= 2 || el.clientHeight === 0) continue;
    // A line clamped on purpose says so, and says how many lines it keeps.
    if (style.webkitLineClamp && style.webkitLineClamp !== 'none') continue;
    if (style.textOverflow === 'ellipsis' && style.whiteSpace === 'nowrap') continue;
    bad.push({cut: Math.round(cut),
              what: el.tagName.toLowerCase() + (el.id ? '#' + el.id : ''),
              said: el.textContent.trim().slice(0, 40)});
  }
  return bad.slice(0, 6);
}"""


# ----------------------------------------------------------------- 2.5.8 ----

TARGETS = """() => {
  const SEL = 'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"]),[role="button"],[role="menuitem"],[role="tab"]';
  const live = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (el.disabled) continue;
    const box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    // 2.5.8's own exceptions. "Inline" covers a link sitting in a sentence,
    // whose size is the sentence's to decide, not the author's.
    if (el.tagName === 'A' && style.display === 'inline') continue;
    if (el.type === 'radio' || el.type === 'checkbox') {
      // The label is the target when it is one.
      const label = el.closest('label') || document.querySelector('label[for="' + el.id + '"]');
      if (label) { const lb = label.getBoundingClientRect();
                   if (lb.width >= 24 && lb.height >= 24) continue; }
    }
    live.push({el, box});
  }
  const small = live.filter(t => t.box.width < 24 || t.box.height < 24);
  const bad = [];
  for (const t of small) {
    // The spacing exception: a 24px circle on this target may touch nothing
    // that is on another target's 24px circle.
    const cx = t.box.left + t.box.width / 2, cy = t.box.top + t.box.height / 2;
    let crowded = null;
    for (const other of live) {
      if (other === t) continue;
      const ox = other.box.left + other.box.width / 2, oy = other.box.top + other.box.height / 2;
      const gap = Math.hypot(cx - ox, cy - oy);
      if (gap < 24 && (crowded === null || gap < crowded)) crowded = gap;
    }
    if (crowded === null) continue;           // small, but alone: it passes
    bad.push({
      w: Math.round(t.box.width), h: Math.round(t.box.height),
      gap: Math.round(crowded),
      what: t.el.tagName.toLowerCase() + (t.el.id ? '#' + t.el.id : '') +
            (t.el.className && typeof t.el.className === 'string'
               ? '.' + t.el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''),
      said: (t.el.textContent || t.el.value || t.el.getAttribute('aria-label') || '').trim().slice(0, 24),
    });
  }
  return {counted: live.length, bad: bad.slice(0, 8)};
}"""


# ---------------------------------------------------- 2.4.11, 2.4.7, 2.4.3 ----

WALK = """(limit) => {
  const SEL = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])';
  const order = [...document.querySelectorAll(SEL)].filter(el => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return box.width > 0 && box.height > 0 && style.visibility !== 'hidden';
  });

  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (el.className && typeof el.className === 'string'
       ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : '');

  const hidden = [], unreachable = [];
  for (const el of order.slice(0, limit)) {
    el.focus();
    if (document.activeElement !== el) { unreachable.push(name(el)); continue; }
    const box = el.getBoundingClientRect();
    if (box.bottom <= 0 || box.top >= innerHeight) continue;   // off screen, not obscured
    // Sample inside the part that is actually on the screen. A control half
    // off the bottom edge is not obscured by anything; it is off the edge,
    // and a real Tab would have scrolled it up before painting it.
    const seen = {left: Math.max(box.left, 0), top: Math.max(box.top, 0),
                  right: Math.min(box.right, innerWidth), bottom: Math.min(box.bottom, innerHeight)};
    const area = Math.max(0, seen.right - seen.left) * Math.max(0, seen.bottom - seen.top);
    if (area < box.width * box.height * 0.25) continue;
    // Ask the browser what is actually painted there, rather than comparing
    // rectangles: a sticky header is an ancestor of the links inside it, and
    // every one of those would otherwise read as buried under itself.
    //
    // A grid, not three points. The criterion's word is "entirely hidden",
    // and three points can all land in the covered half of a control whose
    // other half is in plain sight — which is how this check first accused
    // five languages of a fault none of them had.
    let showing = 0, sampled = 0, blocker = null;
    for (let i = 1; i <= 5; i++) {
      for (let j = 1; j <= 5; j++) {
        const x = seen.left + (seen.right - seen.left) * i / 6;
        const y = seen.top + (seen.bottom - seen.top) * j / 6;
        if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
        sampled++;
        const hit = document.elementFromPoint(x, y);
        if (!hit || hit === el || el.contains(hit) || hit.contains(el)) showing++;
        else if (!blocker) blocker = hit;
      }
    }
    if (sampled && showing === 0 && blocker) hidden.push({what: name(el), under: name(blocker)});
  }
  return {reachable: order.length, hidden: hidden.slice(0, 6), unreachable: unreachable.slice(0, 6)};
}"""


def look(page, route: str, lang: str, checks: list[str]) -> dict[str, list]:
    """Everything this page fails, by criterion."""
    out: dict[str, list] = defaultdict(list)
    where = f"{lang} {route}"

    if "reflow" in checks:
        # 320 by 256 css px is what the criterion asks for; "1280px wide at
        # 400% zoom" is the same measurement said the other way round, and
        # faking it with a zoom property measures the property.
        #
        # And then every width between a small phone and a desktop, because
        # this stylesheet has eighteen breakpoints and each one was put there
        # when something broke. Whether they are too many is a question about
        # the file; whether anything breaks between them is a question about
        # the reader, and only the second one can be answered by looking.
        for width, height in WIDTHS:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(260)
            found = page.evaluate(REFLOW)
            if found:
                out["1.4.10 Reflow"].append(
                    f"{where} at {width}×{height} css px: {found['over']}px of sideways scroll"
                    + (f" — widest is {found['worst']['what']}, {found['worst']['past']}px past"
                       if found.get("worst") else ""))

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)

    if "spacing" in checks:
        page.add_style_tag(content=TEXT_SPACING)
        page.wait_for_timeout(300)
        for bad in page.evaluate(CLIPPED):
            out["1.4.12 Text Spacing"].append(
                f"{where}: {bad['what']} cuts off {bad['cut']}px — “{bad['said']}”")
        spill = page.evaluate(REFLOW)
        if spill:
            out["1.4.12 Text Spacing"].append(
                f"{where}: {spill['over']}px of sideways scroll once spacing is forced")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(900)

    if "target" in checks:
        sized = page.evaluate(TARGETS)
        for bad in sized["bad"]:
            out["2.5.8 Target Size"].append(
                f"{where}: {bad['what']} is {bad['w']}×{bad['h']}px with {bad['gap']}px "
                f"to its neighbour" + (f" — “{bad['said']}”" if bad["said"] else ""))

    if "obscured" in checks or "order" in checks:
        # The page scrolls smoothly, which means focus() starts an animation
        # and the rectangle read a moment later is where the control used to
        # be. Every measurement in this walk was taken mid-flight until this
        # line existed, and it accused five languages of a fault none of them
        # had. What is being checked is the layout, not the animation.
        page.add_style_tag(content="html{scroll-behavior:auto !important}")
        walked = page.evaluate(WALK, 60)
        for bad in walked["hidden"]:
            out["2.4.11 Focus Not Obscured"].append(
                f"{where}: {bad['what']} sits under {bad['under']} when focused")
        for bad in walked["unreachable"]:
            out["2.4.3 Focus Order"].append(f"{where}: {bad} cannot take focus")

    if "visible" in checks:
        blank = page.screenshot()
        shown = page.evaluate(
            """() => { const el = document.querySelector('a[href],button:not([disabled])');
                       if (!el) return false; el.focus(); return true; }""")
        if shown and page.screenshot() == blank:
            out["2.4.7 Focus Visible"].append(f"{where}: focusing the first control changes nothing")
        page.evaluate("() => document.activeElement && document.activeElement.blur()")

    return out


def sweep(base: str, langs: list[str], checks: list[str]) -> dict[str, list]:
    from playwright.sync_api import sync_playwright

    found: dict[str, list] = defaultdict(list)
    pages = 0
    with sync_playwright() as play:
        browser = play.chromium.launch(**a_browser())
        for lang in langs:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            for route in ROUTES:
                try:
                    page.goto(f"{base}/?lang={lang}#{route}", wait_until="domcontentloaded")
                    page.wait_for_timeout(1300)
                    for rule, lines in look(page, route, lang, checks).items():
                        found[rule].extend(lines)
                except Exception as error:
                    found["__error__"].append(f"{lang} {route}: {type(error).__name__}: {error}")
                    continue
                pages += 1
            page.close()
        browser.close()
    found["__pages__"] = pages          # type: ignore[assignment]
    return found


def report(found: dict[str, list]) -> int:
    pages = found.pop("__pages__", 0)
    print(f"pages checked: {pages}")
    errors = found.pop("__error__", [])
    if not found:
        print("nothing failing")
    for rule in sorted(found):
        lines = found[rule]
        print(f"\n[{rule}] — {len(lines)}")
        for line in lines[:10]:
            print(f"   {line}")
        if len(lines) > 10:
            print(f"   … and {len(lines) - 10} more")
    if errors:
        print(f"\n[could not be checked] — {len(errors)}")
        for line in errors[:6]:
            print(f"   {line}")
    return 1 if found or errors else 0


def main() -> int:
    args = sys.argv[1:]
    base = next((a for a in args if a.startswith("http")), "http://127.0.0.1:8000")
    langs = LANGS if "--full" in args else ["en"]
    checks = CHECKS
    for arg in args:
        if arg.startswith("--only"):
            wanted = arg.split("=", 1)[-1] if "=" in arg else args[args.index(arg) + 1]
            checks = [c.strip() for c in wanted.split(",") if c.strip() in CHECKS]
    return report(sweep(base, langs, checks))


if __name__ == "__main__":
    raise SystemExit(main())
