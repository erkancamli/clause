"""Build the site for publishing: the readable page becomes a minified one.

    python3 site/build.py            writes site/dist/

What is published is what a browser needs and no more: the page with its
scripts and styles minified (esbuild, from the Privy bundle's toolchain),
the translations, the Leaflet and Privy files as they are. Comments, the
names of local variables and the layout of the source are not published.
This does not make the front end secret, nothing served to a browser is,
but it makes copying it a job rather than a right click, and the
copyright notice at the top of the page states the terms.

The readable source stays in site/index.html, which ships only in the
server package, never to Netlify.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
# The bundled binary, or whichever one CLAUSE_ESBUILD names. The minifier is
# not the Privy bundle's property, and hardcoding a sibling project's
# node_modules meant the build could only be asked whether it minifies
# correctly on a machine where that bundle had been installed: the build host
# has it, the runner that gates the deployment did not, and so the test that
# asks failed there for three releases while the page it checks was fine.
ESBUILD = Path(os.environ.get("CLAUSE_ESBUILD")
               or HERE.parent / "privy-bundle" / "node_modules" / ".bin" / "esbuild")
OBFUSCATOR = HERE.parent / "privy-bundle" / "node_modules" / ".bin" / "javascript-obfuscator"
NOTICE = ("/* Clause, clause.insure. Copyright (c) 2026 Erkan Çamlı. All rights reserved. "
          "Unauthorised copying, redistribution or reuse is prohibited. */")


def minify(code: str, loader: str) -> str:
    """One esbuild pass over a script or a stylesheet.

    A missing esbuild used to print a line to stderr and publish the page
    unminified: 727 KB of source where 540 KB was expected, on a product whose
    buyers are on mid range Android phones in Türkiye, Indonesia and the
    Philippines. Nothing downstream checks the weight, so the day an install
    step fails on the build host the site goes out at a third again its size
    and nobody finds out.

    So it stops. Somebody building the page on their own machine without the
    tooling installed can say so and get the unminified page, deliberately,
    with the reason in front of them.
    """
    if not ESBUILD.exists():
        if os.environ.get("CLAUSE_BUILD_ALLOW_UNMINIFIED") == "1":
            print(f"esbuild not found at {ESBUILD}; publishing the page "
                  f"unminified because CLAUSE_BUILD_ALLOW_UNMINIFIED=1",
                  file=sys.stderr)
            return code
        raise SystemExit(
            f"esbuild not found at {ESBUILD}. The page would be published "
            f"unminified, which is a third again its size. Install it with "
            f"`npm install` in privy-bundle, point CLAUSE_ESBUILD at a binary "
            f"you already have, or set CLAUSE_BUILD_ALLOW_UNMINIFIED=1 if you "
            f"meant to.")
    done = subprocess.run(
        [str(ESBUILD), f"--loader={loader}", "--minify", "--target=es2017", "--charset=utf8", "--legal-comments=none"],
        input=code.encode("utf-8"), capture_output=True,
    )
    if done.returncode != 0:
        print(done.stderr.decode("utf-8", "replace"), file=sys.stderr)
        raise SystemExit("minification failed; the page is not published broken")
    return done.stdout.decode("utf-8")


def obfuscate(code: str) -> str:
    """After minifying: names flattened, strings pulled into an encoded table,
    control flow left alone (it would slow the page for nothing).

    Off unless asked for, and measured when it is. This step has never run in
    production: the tool was not declared in package.json, was not in the lock
    file, and was not installed on whatever built the live page -- so for as
    long as this function has existed the build has printed one line to stderr
    and skipped it. Measured on this page it costs 341 KB, taking 540 KB to
    881 KB, a little over half again.

    That is a trade somebody should make on purpose rather than inherit from
    whether a binary happened to be on the build host. Set CLAUSE_OBFUSCATE=1
    and it runs; ask for it without the tool and the build stops rather than
    quietly publishing a page that is not obfuscated while the notice at the
    top of it says the code is protected.

    What it buys is worth saying plainly too: someone determined can still
    read the page, as they can read any page. It raises the cost of lifting a
    function out and using it as it is. The copyright notice is what makes
    that unlawful; this only makes it tedious.
    """
    if os.environ.get("CLAUSE_OBFUSCATE") != "1":
        return code
    if not OBFUSCATOR.exists():
        raise SystemExit(
            "CLAUSE_OBFUSCATE=1 but javascript-obfuscator is not installed at "
            f"{OBFUSCATOR}. Install it in privy-bundle, or unset the variable.")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.js"
        out = Path(tmp) / "out.js"
        src.write_text(code, encoding="utf-8")
        done = subprocess.run([
            str(OBFUSCATOR), str(src), "--output", str(out),
            "--compact", "true", "--identifier-names-generator", "hexadecimal",
            "--rename-globals", "false", "--string-array", "true", "--string-array-threshold", "0.6",
            "--string-array-encoding", "base64", "--string-array-rotate", "true",
            "--string-array-shuffle", "true", "--split-strings", "false",
            "--unicode-escape-sequence", "false", "--self-defending", "false",
            "--control-flow-flattening", "false", "--dead-code-injection", "false",
            "--target", "browser", "--seed", "20260919",
        ], capture_output=True)
        if done.returncode != 0:
            print(done.stderr.decode("utf-8", "replace"), file=sys.stderr)
            raise SystemExit("obfuscation failed; the page is not published broken")
        return out.read_text(encoding="utf-8")


def gather_styles(source: str) -> str:
    """Put the stylesheet back together as one inlined <style>.

    The visual system is nine files in the source so it can be worked on as a
    thing of its own. A reader should not pay nine requests for that, and a
    stylesheet fetched separately blocks the first paint on a second round
    trip, so the published page carries it inlined exactly as it did when it
    was one block. The run of <link> tags is replaced in place, so the styles
    land where they were written and in the order they were written; the order
    is load-bearing and the numbers in the file names carry it.
    """
    links = list(re.finditer(r'[ \t]*<link rel="stylesheet" href="(styles/[^"]+)">\n?', source))
    if not links:
        return source
    joined = ""
    for link in links:
        part = HERE / link.group(1)
        if not part.is_file():
            raise SystemExit(f"{link.group(1)} is linked by the page and is not there")
        joined += part.read_text(encoding="utf-8")
    at = links[0].start()
    # Take the note above them with them. It is removed from what is published
    # either way, and swallowing it here leaves the page byte for byte what it
    # was when the stylesheet was written inline, which is what proves this
    # split changed nothing a browser can see.
    while at and source[at - 1] in " \t\n":
        at -= 1
    if source[:at].endswith("-->"):
        at = source.rindex("<!--", 0, at)
        while at and source[at - 1] in " \t":
            at -= 1
    # A relative path in a stylesheet is read from where the stylesheet is.
    # In the source that is site/styles/, so the parts say ../fonts/; inlined
    # they are read from where the page is, so the ../ comes off. Without
    # this the two halves of the arrangement disagree and one of them is
    # always wrong: the fonts 404ed in the source before it was written.
    joined = re.sub(r"url\(\.\./", "url(", joined)
    return source[:at] + f"<style>{joined.lstrip()}</style>\n" + source[links[-1].end() :]


def gather_scripts(source: str) -> str:
    """Put the script back together as one inlined block, where it was.

    Same arrangement as the styles and for the same reasons: worked on as
    parts, served as one. A part fetched separately is a request the page did
    not used to make, and twenty-three of them on a mid range phone is the
    whole first second.

    Order matters more here than it does for the styles. Separate files do not
    hoist across one another, so a part that runs something at load time can
    only run what a part before it declared. Inlining hides that: concatenated,
    everything hoists and a wrong order still works. The order is therefore
    held by a test against the parts as the page links them, not against what
    the build makes of them.
    """
    tags = list(re.finditer(r'[ \t]*<script data-part="(app/[^"]+)"[^>]*></script>\n?', source))
    if not tags:
        return source
    # A part the pattern does not recognise is dropped without a word, and the
    # page still builds, still runs, and is missing a screen. That happened:
    # marking the desk's part with an attribute put something between the path
    # and the closing bracket, the pattern stopped matching, and both pages
    # came out 89,268 B lighter and short a company desk. The pattern takes
    # other attributes now, and the count is checked, so the next thing that
    # confuses it stops the build instead of shipping.
    listed = len(re.findall(r'<script data-part="app/', source))
    if len(tags) != listed:
        raise SystemExit(f"the page lists {listed} script parts and the build "
                         f"recognised {len(tags)}: one of them is written in a "
                         f"way the build does not read")
    joined = ""
    for tag in tags:
        part = HERE / tag.group(1)
        if not part.is_file():
            raise SystemExit(f"{tag.group(1)} is linked by the page and is not there")
        joined += part.read_text(encoding="utf-8")
    at = tags[0].start()
    while at and source[at - 1] in " \t\n":
        at -= 1
    if source[:at].endswith("-->"):
        at = source.rindex("<!--", 0, at)
        while at and source[at - 1] in " \t":
            at -= 1
    return source[:at] + f"<script>{joined}</script>" + source[tags[-1].end() :]


def build_page(source: str) -> str:
    """Minify every inline <script> and <style>, leave the markup itself."""
    source = assemble(source)

    def script(match: re.Match) -> str:
        attrs, body = match.group(1), match.group(2)
        if "src=" in attrs or "type=\"application/ld+json\"" in attrs or not body.strip():
            return match.group(0)
        return f"<script{attrs}>{NOTICE}\n{obfuscate(minify(body, 'js'))}</script>"

    def style(match: re.Match) -> str:
        attrs, body = match.group(1), match.group(2)
        return f"<style{attrs}>{minify(body, 'css')}</style>" if body.strip() else match.group(0)

    page = re.sub(r"<script([^>]*)>(.*?)</script>", script, source, flags=re.S)
    page = re.sub(r"<style([^>]*)>(.*?)</style>", style, page, flags=re.S)
    # HTML comments other than the notice at the top carry nothing a browser needs.
    head, rest = page.split("\n", 2)[0], page.split("\n", 2)[1:]
    body = "\n".join(rest)
    body = re.sub(r"<!--(?!\[if).*?-->", "", body, flags=re.S)
    return head + "\n" + body


def stamp(page: str, called: str | None = None) -> tuple[str, str]:
    """Give the page a name for this build, and publish that name beside it.

    A single page application is only downloaded once. After that a person
    moves around it by changing the part of the address after the hash, which
    never fetches the document again, so a tab left open on Monday is still
    running Monday's page on Friday however correct the cache headers are. The
    page therefore has to be able to notice that it has been replaced, and to
    do that it has to know which version it is.

    The name is the digest of the built page, so it changes when and only when
    something a browser would load has changed. Rebuilding with no edits
    produces the same name and no reader is disturbed.

    A name may be given instead of taken, for the second page of the same
    build: the desk is the same source with nothing removed, and a tab open on
    it asks the same version.json as a tab open on the buyer's page. Two names
    for one build would have one of those two tabs reloading itself forever.
    """
    name = called or hashlib.sha256(page.encode("utf-8")).hexdigest()[:12]
    return page.replace("__CLAUSE_BUILD__", name), name


def assemble(source: str) -> str:
    """The page with its parts joined and nothing else done to it.

    What `site/index.html` holds is not a page a browser can run: the styles
    and the script are listed there, not written there, and the script's parts
    are the inside of one closure cut into pieces, so not one of them is a
    program on its own. Joining them is the build's first step either way. This
    is that step with the minifier and the obfuscator left out, so the page can
    be read and stepped through while it is being worked on, and what is looked
    at is what is published rather than a second arrangement that drifts.
    """
    return gather_styles(gather_scripts(source))


def without_the_desk(source: str) -> str:
    """The same page with the company desk taken out of it.

    Three of the fifteen screens are the desk an insurer runs its book on:
    the company view, the operator view and the register of insurers. A buyer
    never opens one, and on the page a buyer downloads they were 89,268 B of
    script and 14,148 B of markup, measured by building the page both ways.

    They are not deferred inside the closure. The whole script is one closure
    and the desk's part reads fifty-one names out of it; those fifty-one pull
    in five hundred and sixty-three declarations between them, 77% of the
    script, so a self-contained desk chunk would be the whole thing twice.
    Handing the fifty-one across a boundary instead would leave a list to keep
    by hand, and the day someone adds a fifty-second the desk breaks on the
    route an insurer uses to run their book, with nothing to say so until
    somebody goes there.

    So the desk is a second page, built from these same parts with nothing
    taken out. An insurer downloads what they download now. A buyer stops
    downloading a screen they cannot open.
    """
    at = source.find(" data-desk")
    while at != -1:
        open_tag = source.rfind("<", 0, at)
        # A script part is one tag; a view is a section with sections inside it.
        if source.startswith("<script", open_tag):
            shut = source.index("</script>", at) + len("</script>")
            while shut < len(source) and source[shut] == "\n":
                shut += 1
        else:
            depth, cut = 0, open_tag
            while True:
                nxt = re.search(r"</?section\b", source[cut:])
                if not nxt:
                    raise SystemExit("a data-desk section is never closed")
                cut += nxt.start()
                depth += -1 if source[cut:cut + 2] == "</" else 1
                cut += 2
                if depth == 0:
                    break
            shut = source.index(">", cut) + 1
        source = source[:open_tag] + source[shut:]
        at = source.find(" data-desk")
    return source


def main() -> None:
    if "--dev" in sys.argv:
        # Beside index.html, so fonts/, i18n/, vendor/ and app/ resolve as they
        # do for the published page. It is ignored by git: it is a build.
        source = (HERE / "index.html").read_text(encoding="utf-8")
        desk = assemble(source).replace("__CLAUSE_BUILD__", "development")
        page = assemble(without_the_desk(source)).replace("__CLAUSE_BUILD__", "development")
        (HERE / "dev.html").write_text(page, encoding="utf-8")
        # Named as the published one is, so the link from the buyer's page to
        # the desk is the same relative link in development and in production.
        (HERE / "desk.html").write_text(desk, encoding="utf-8")
        # The open tab asks this for the name of the build it is running. In
        # development the answer is always the same one, so the page never
        # decides it has been replaced, and it is written rather than left to
        # 404 because a page that is being checked for console errors should
        # have none of its own making.
        (HERE / "version.json").write_text(
            json.dumps({"build": "development"}, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"site/dev.html: {len(page.encode()):,} bytes, assembled and not minified")
        print(f"site/desk.html: {len(desk.encode()):,} bytes, with the desk")
        return

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    source = (HERE / "index.html").read_text(encoding="utf-8")
    page, name = stamp(build_page(without_the_desk(source)))
    (DIST / "index.html").write_text(page, encoding="utf-8")
    # The same build name, because it is one build of one source: a tab open on
    # the desk asks the same version.json as a tab open on the buyer's page.
    desk, _ = stamp(build_page(source), name)
    (DIST / "desk.html").write_text(desk, encoding="utf-8")
    # Forty bytes, fetched by an open tab now and then. It is deliberately not
    # the page itself: asking for the page to find out whether the page changed
    # costs seven hundred kilobytes to answer a question worth one line.
    (DIST / "version.json").write_text(
        json.dumps({"build": name}, separators=(",", ":")) + "\n", encoding="utf-8")
    # fonts/ joins the list because the page now serves its own faces. Left out,
    # the published site would reference woff2 files that are not there and
    # every visitor would read it in whatever the system offered -- which looks
    # like a design decision from the outside and is the absence of one.
    for name_ in ("netlify.toml", "i18n", "privy", "vendor", "fonts"):
        src = HERE / name_
        if src.is_dir():
            shutil.copytree(src, DIST / name_)
        elif src.is_file():
            shutil.copy2(src, DIST / name_)
    before = (HERE / "index.html").stat().st_size
    after = (DIST / "index.html").stat().st_size
    print(f"site/dist/index.html: {after:,} bytes (source {before:,}), build {name}")
    print(f"site/dist/desk.html: {(DIST / 'desk.html').stat().st_size:,} bytes, with the desk")


if __name__ == "__main__":
    main()
