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
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
ESBUILD = HERE.parent / "privy-bundle" / "node_modules" / ".bin" / "esbuild"
OBFUSCATOR = HERE.parent / "privy-bundle" / "node_modules" / ".bin" / "javascript-obfuscator"
NOTICE = ("/* Clause, clause.insure. Copyright (c) 2026 Erkan Çamlı. All rights reserved. "
          "Unauthorised copying, redistribution or reuse is prohibited. */")


def minify(code: str, loader: str) -> str:
    """One esbuild pass over a script or a stylesheet; the source on failure."""
    if not ESBUILD.exists():
        print(f"esbuild not found at {ESBUILD}; publishing the page unminified", file=sys.stderr)
        return code
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
    control flow left alone (it would slow the page for nothing). Someone
    determined can still read it; nobody can lift a function out of it and
    use it as it is."""
    if not OBFUSCATOR.exists():
        print("javascript-obfuscator not found; publishing minified only", file=sys.stderr)
        return code
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


def build_page(source: str) -> str:
    """Minify every inline <script> and <style>, leave the markup itself."""
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


def stamp(page: str) -> tuple[str, str]:
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
    """
    name = hashlib.sha256(page.encode("utf-8")).hexdigest()[:12]
    return page.replace("__CLAUSE_BUILD__", name), name


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    page, name = stamp(build_page((HERE / "index.html").read_text(encoding="utf-8")))
    (DIST / "index.html").write_text(page, encoding="utf-8")
    # Forty bytes, fetched by an open tab now and then. It is deliberately not
    # the page itself: asking for the page to find out whether the page changed
    # costs seven hundred kilobytes to answer a question worth one line.
    (DIST / "version.json").write_text(
        json.dumps({"build": name}, separators=(",", ":")) + "\n", encoding="utf-8")
    for name_ in ("netlify.toml", "i18n", "privy", "vendor"):
        src = HERE / name_
        if src.is_dir():
            shutil.copytree(src, DIST / name_)
        elif src.is_file():
            shutil.copy2(src, DIST / name_)
    before = (HERE / "index.html").stat().st_size
    after = (DIST / "index.html").stat().st_size
    print(f"site/dist/index.html: {after:,} bytes (source {before:,}), build {name}")


if __name__ == "__main__":
    main()
