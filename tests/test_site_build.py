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
