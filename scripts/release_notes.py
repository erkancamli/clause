"""The section of the changelog that belongs to one version.

The release notes and the changelog are the same words. Writing them twice is
how they come apart, and the one on GitHub is the one nobody remembers to
update, so it is read from the file rather than retyped.

    python scripts/release_notes.py 1.16.1
"""

from __future__ import annotations

import pathlib
import re
import sys

CHANGELOG = pathlib.Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def notes(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    start = re.search(rf"^## {re.escape(version)}, .*$", text, re.M)
    if start is None:
        raise SystemExit(f"no section for {version} in CHANGELOG.md")
    rest = text[start.end():]
    following = re.search(r"^## \d", rest, re.M)
    return rest[: following.start()].strip() if following else rest.strip()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: release_notes.py <version>")
    print(notes(sys.argv[1]))
