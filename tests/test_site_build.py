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
import pathlib

import pytest

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
    wanted = re.findall(r"src:url\((fonts/[^)]+)\)", page)
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

    page = (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text(encoding="utf-8")
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
