"""The build that puts the page on the internet.

Two steps in it used to fail by carrying on. A missing esbuild printed one
line to stderr and published the page unminified -- 727 KB where 540 KB was
expected, on a product whose buyers are on mid range Android phones. A missing
obfuscator printed another and published the page unobfuscated, under a notice
at the top saying the code is protected. Nothing downstream checks either, so
the day an install step fails on the build host, the site goes out wrong and
nobody finds out.
"""

from __future__ import annotations

import importlib.util
import re
import pathlib

import pytest
from conftest import page_assembled, stylesheet

BUILD = pathlib.Path(__file__).resolve().parent.parent / "site" / "build.py"


@pytest.fixture
def build():
    """The build script, loaded from its path: it is a script, not a module."""
    spec = importlib.util.spec_from_file_location("clause_site_build", BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_missing_minifier_stops_the_build(build, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(build, "ESBUILD", tmp_path / "nowhere")
    monkeypatch.delenv("CLAUSE_BUILD_ALLOW_UNMINIFIED", raising=False)
    with pytest.raises(SystemExit, match="esbuild not found"):
        build.minify("var a = 1;", "js")


def test_it_can_be_skipped_on_purpose(build, monkeypatch, tmp_path, capsys) -> None:
    """Somebody building the page on their own machine without the tooling
    says so and gets the unminified page, with the reason in front of them."""
    monkeypatch.setattr(build, "ESBUILD", tmp_path / "nowhere")
    monkeypatch.setenv("CLAUSE_BUILD_ALLOW_UNMINIFIED", "1")
    assert build.minify("var a = 1;", "js") == "var a = 1;"
    assert "unminified" in capsys.readouterr().err


def test_obfuscation_is_off_unless_it_is_asked_for(build, monkeypatch) -> None:
    """It has never run in production: the tool was not in package.json, not
    in the lock file, and not on whatever built the live page. Measured on
    this page it costs 341 KB, taking 540 KB to 881 KB -- a trade to make on
    purpose rather than inherit from whether a binary happened to be there."""
    monkeypatch.delenv("CLAUSE_OBFUSCATE", raising=False)
    code = "var a = 1;"
    assert build.obfuscate(code) == code


def test_asking_for_obfuscation_without_the_tool_stops_the_build(
        build, monkeypatch, tmp_path) -> None:
    """Otherwise the page goes out unobfuscated under a notice saying the code
    is protected, which is the failure that looks like success."""
    monkeypatch.setenv("CLAUSE_OBFUSCATE", "1")
    monkeypatch.setattr(build, "OBFUSCATOR", tmp_path / "nowhere")
    with pytest.raises(SystemExit, match="not installed"):
        build.obfuscate("var a = 1;")


# ---------------------------------------------------------------------------
# The faces the page sets, and where they come from
# ---------------------------------------------------------------------------


def test_every_face_the_page_declares_is_a_file_that_exists() -> None:
    """A @font-face pointing at nothing is worse than no rule at all: the
    browser falls back silently and the page is set in whatever the system
    offered, which looks like a decision from the outside and is the absence
    of one."""
    import re
    from pathlib import Path

    site = Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    wanted = re.findall(r"src:url\(\.\./(fonts/[^)]+)\)", stylesheet())
    assert wanted, "the page declares no faces of its own"
    missing = [w for w in wanted if not (site / w).is_file()]
    assert not missing, f"declared but not shipped: {missing}"


def test_reading_the_page_asks_nothing_of_a_third_party() -> None:
    """The three Latin families used to come from fonts.googleapis.com, which
    costs every visitor two handshakes to somebody else before a word can be
    drawn in the right face, and hands that visitor's address over to read a
    page about their own insurance.

    Japanese is the one exception and is allowed: its cut is a CJK family
    served as a hundred-odd slices keyed by unicode-range, and carrying it
    here would mean shipping megabytes to everybody for the readers of one
    language. It is fetched on demand, after first paint, by them alone.
    """
    from pathlib import Path

    import re

    page = page_assembled()
    head = page[:page.index("</head>")]
    # A reference, not a mention: prose about why the fonts moved is not a
    # request, and this test failed on its own explanation the first time.
    fetched = re.findall(r'(?:href|src)=["\']([^"\']+)|url\((https?://[^)]+)\)', head)
    reached = [u for pair in fetched for u in pair
               if u and ("fonts.googleapis.com" in u or "fonts.gstatic.com" in u)]
    assert not reached, f"still on the critical path: {reached}"
    # What remains is the Japanese loader, which builds its URL from script
    # after first paint and only for readers of Japanese.
    assert "SCRIPT_FONTS" in page and "IBM+Plex+Sans+JP" in page


def test_the_build_publishes_the_faces() -> None:
    """Left out of the copy list, the published site would reference woff2
    files that are not there."""
    from pathlib import Path

    build = (Path(__file__).resolve().parent.parent / "site" / "build.py").read_text(encoding="utf-8")
    line = [l for l in build.splitlines() if "netlify.toml" in l and "for name_" in l]
    assert line, "could not find the build's copy list"
    assert '"fonts"' in line[0], f"fonts is not published: {line[0].strip()}"


# ---------------------------------------------------------------------------
# What survives minification
# ---------------------------------------------------------------------------


def test_the_palette_reaches_the_published_page_intact(build) -> None:
    """Everything that measures this palette reads the readable source.

    So nothing would notice a minifier that dropped a theme block, renamed a
    custom property or rounded a colour: the contrast tests would keep passing
    against a file nobody is served. The light theme is written twice, once for
    the explicit choice and once for the device preference, and a build that
    kept one of them would give the same reader a different page depending on
    how they arrived at it.

    This asks the minifier the question directly, which is cheap, rather than
    running a whole build.
    """
    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text(encoding="utf-8")
    style = stylesheet()

    def palettes(text):
        """Every block that defines the ink, by what it contains rather than by
        what it is called: the minifier rewrites selectors."""
        return [dict(re.findall(r"--([a-z0-9-]+):\s*([^;}]+)", block))
                for block in re.findall(r"\{([^{}]*--ink:[^{}]*)\}", text)]

    source = palettes(style)
    assert len(source) == 3, f"expected one dark and two light blocks, found {len(source)}"

    published = build.minify(style, "css")
    # A minifier that was skipped hands back the stylesheet it was given, and
    # then every assertion below compares the source with itself and passes.
    # That is how this test gets "fixed" by whoever meets it failing on a
    # machine without the tooling: CLAUSE_BUILD_ALLOW_UNMINIFIED=1 turns it
    # green while it checks nothing. It has to have run to have answered.
    assert len(published) < len(style) and published != style, (
        "the minifier did not run, so this test compared the source with itself")

    minified = palettes(published)
    assert len(minified) == len(source), (
        f"minification published {len(minified)} palettes where the source has {len(source)}")

    for i, (before, after) in enumerate(zip(source, minified)):
        for token in ("ink", "ink-2", "ink-3", "ground", "panel", "raised", "sunk",
                      "art-line", "signal", "signal-ink", "signal-fill"):
            if token not in before:
                continue
            assert token in after, f"palette {i}: --{token} did not survive minification"
            assert before[token].strip().lower() == after[token].strip().lower(), (
                f"palette {i}: --{token} was {before[token].strip()} and is "
                f"published as {after[token].strip()}")


def test_the_two_light_palettes_are_the_same_palette(build) -> None:
    """One for the explicit choice, one for the device preference. A correction
    applied to one of them makes the same page legible or not depending on how
    the reader arrived at it, and that is exactly the kind of fault that hides:
    whoever is testing has a preference set, and sees the half that works."""
    import re
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text(encoding="utf-8")
    style = stylesheet()
    blocks = [dict(re.findall(r"--([a-z0-9-]+):\s*([^;}]+)", b))
              for b in re.findall(r"\{([^{}]*--ink:[^{}]*)\}", style)]
    light = [b for b in blocks if int(b["ink"].strip().lstrip("#")[:2], 16) < 128]
    assert len(light) == 2, f"expected two light palettes, found {len(light)}"
    first, second = light
    differing = {k for k in set(first) | set(second)
                 if first.get(k, "").strip().lower() != second.get(k, "").strip().lower()}
    assert not differing, f"the two light palettes disagree about {sorted(differing)}"


def test_the_runner_that_gates_the_deployment_can_run_the_minifier() -> None:
    """The test above can only be asked where esbuild is.

    It was asked nowhere that mattered. The binary lives in the Privy bundle's
    node_modules, the deployment's own runner installs Python and nothing else,
    and so the test failed there on every push for three releases -- 1.23.1,
    1.24.0 and 1.25.0 never reached the server -- while the page it checks was
    correct the whole time. A check that cannot run where it is relied upon is
    not a check, and the way out that suggests itself is the worse one:
    CLAUSE_BUILD_ALLOW_UNMINIFIED makes minify hand back what it was given, so
    the palette test would compare the stylesheet with itself and pass.
    """
    import re
    from pathlib import Path

    workflow = (Path(__file__).resolve().parent.parent
                / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    job = workflow[workflow.index("  test:"):workflow.index("  deploy:")]

    assert "setup-node" in job, "the runner has no node, so it can have no esbuild"
    assert "npm install -g" in job and "esbuild@" in job, "esbuild is not installed"
    assert "CLAUSE_ESBUILD=" in job, "the build would still look only in privy-bundle"
    assert "pytest" in job, "this is not the job that runs the tests"
    # And the version is read from the lock file rather than written out again,
    # because a second copy of a version is a version that drifts.
    assert "package-lock.json" in job, "the version is pinned in two places"

    # And never the other way out, in any of its forms: an env: entry, an
    # inline assignment, an export. What the job does, not what it says about
    # itself -- the comment explaining why the variable is not used names the
    # variable, and prose is not a setting.
    doing = "\n".join(l for l in job.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"CLAUSE_BUILD_ALLOW_UNMINIFIED\s*[:=]", doing), (
        "the runner skips minification, so the palette test passes without asking")


def test_the_stylesheet_is_put_back_together_in_the_order_it_is_linked(build) -> None:
    """Nine files in the source, one inlined block in what is published.

    Split so the visual system can be worked on as a thing of its own. A
    reader should not pay for that: nine stylesheets are nine requests, and a
    stylesheet fetched at all blocks the first paint on a round trip the page
    used to not need. So the build puts them back where they were written.

    Order is the whole risk. A cascade read out of order is a different
    stylesheet, and the failure is silent: rules still apply, just the wrong
    ones win. The numbers in the file names carry the order and the page's
    link order is what the build follows.
    """
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    linked = re.findall(r'<link rel="stylesheet" href="(styles/[^"]+)">', page)

    assert linked, "the page links no stylesheet"
    assert linked == sorted(linked), f"the parts are not linked in name order: {linked}"
    assert len(set(linked)) == len(linked), "a part is linked twice"
    on_disk = sorted("styles/" + p.name for p in (site / "styles").glob("*.css"))
    assert on_disk == sorted(linked), (
        f"styles/ and the page disagree about which parts exist: {set(on_disk) ^ set(linked)}"
    )

    gathered = build.gather_styles(page)
    assert 'href="styles/' not in gathered, "a part is still fetched by the published page"
    assert gathered.count("<style>") == 1, "the parts did not come back as one block"
    inlined = gathered[gathered.index("<style>") + len("<style>") : gathered.index("</style>")]
    want = "".join((site / p).read_text(encoding="utf-8") for p in linked)
    assert inlined == re.sub(r"url\(\.\./", "url(", want).lstrip(), (
        "the inlined stylesheet is not the parts, in order"
    )

    # A path in a part is written from styles/; a path in the page is written
    # from the page. Every one of them points at something.
    for ref in re.findall(r"url\(([^)'\"]+)\)", want):
        if ref.startswith("data:"):
            continue
        assert ref.startswith("../"), f"{ref} is read from styles/ and does not say so"
        assert (site / "styles" / ref).resolve().is_file(), f"{ref} is not there"


def test_a_part_the_page_does_not_link_stops_the_build(build, tmp_path) -> None:
    """Silence is the failure mode this whole arrangement invites."""
    page = '<html><head><link rel="stylesheet" href="styles/no-such-file.css"></head></html>'
    with pytest.raises(SystemExit, match="no-such-file.css"):
        build.gather_styles(page)


def test_the_script_is_joined_in_the_order_the_page_lists_it(build) -> None:
    """Twenty-three parts of one closure, and not one of them is a program.

    The whole script is the inside of a single `(function(){ ... })()`, so a
    part cut out of it opens braces it never closes. Cut into files and fetched
    as files, the first one stops the browser on "Unexpected end of input" and
    the page is blank. They are therefore listed by the page and joined by the
    build, never fetched, and the attribute they are listed with is not one a
    browser acts on.

    Order carries twice as much here as it does for the styles. Joined, the
    whole thing hoists and any order of declarations would work; what does not
    survive reordering is the code that runs as it is read. The numbers in the
    names carry the order and this holds the page to them.
    """
    site = pathlib.Path(__file__).resolve().parent.parent / "site"
    page = (site / "index.html").read_text(encoding="utf-8")
    # As the build reads them, other attributes and all: the desk's part is
    # marked data-desk, and a pattern that stops at the quote silently finds
    # one part fewer. That is exactly how the marker broke the build, which
    # now refuses rather than shipping a page short of a screen.
    listed = re.findall(r'<script data-part="(app/[^"]+)"[^>]*></script>', page)

    assert listed, "the page lists no script part"
    assert listed == sorted(listed), f"the parts are not listed in name order: {listed}"
    assert len(set(listed)) == len(listed), "a part is listed twice"
    on_disk = sorted("app/" + p.name for p in (site / "app").glob("*.js"))
    assert on_disk == sorted(listed), (
        f"app/ and the page disagree about which parts exist: {set(on_disk) ^ set(listed)}"
    )
    assert 'src="app/' not in page, (
        "a part is given to the browser to fetch; not one of them is a program on its own"
    )

    joined = build.gather_scripts(page)
    assert "data-part=" not in joined, "a part is still listed in the joined page"
    assert joined.count("<script>") == 2, (
        "the page should hold the one it always had and the one the parts came back as"
    )
    inside = joined[joined.rindex("<script>") + len("<script>") : joined.rindex("</script>")]
    want = "".join((site / p).read_text(encoding="utf-8") for p in listed)
    assert inside == want, "the joined script is not the parts, in order"

    # The closure the parts are the inside of: opened in the first, closed in
    # the last, and nowhere else is either of them a whole thing.
    first = (site / listed[0]).read_text(encoding="utf-8")
    last = (site / listed[-1]).read_text(encoding="utf-8")
    assert first.lstrip().startswith('"use strict";'), "the first part does not open the script"
    assert last.rstrip().endswith("})();"), "the last part does not close the closure"


def test_a_part_the_page_does_not_list_stops_the_build(build) -> None:
    page = '<html><body><script data-part="app/no-such-file.js"></script></body></html>'
    with pytest.raises(SystemExit, match="no-such-file.js"):
        build.gather_scripts(page)
