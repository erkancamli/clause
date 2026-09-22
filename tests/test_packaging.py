"""The install is part of the protocol, and it broke in the one way tests miss.

A clean server found `cryptography` missing from requirements.txt. Nothing
caught it because every machine the code had run on already had the package, so
the import succeeded everywhere it was tried. That is the shape of a packaging
bug: invisible until the first machine that has nothing.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "clause"


# The model build runs offline, on a machine with the catalogue, and needs
# numpy. The server only reads what it wrote. These modules are declared in
# requirements-build.txt, and the server is tested below never to import them.
BUILD_ONLY = {"build.py", "validate.py", "sources.py"}


def declared(file: str = "requirements.txt") -> set[str]:
    names = set()
    for line in (ROOT / file).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-r"):
            names.add(line.split(">=")[0].split("==")[0].split("[")[0].strip())
    return names


def _is_build(path: pathlib.Path) -> bool:
    return path.parent.name == "hazard" and path.name in BUILD_ONLY


def imported(build: bool = False) -> set[str]:
    names: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        if _is_build(path) != build:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_every_package_the_code_imports_is_declared() -> None:
    """Otherwise the service starts on the machine it was written on and
    nowhere else."""
    third_party = {
        name for name in imported()
        if name not in sys.stdlib_module_names and name != "clause"
    }
    missing = third_party - declared()
    assert not missing, (
        f"imported but not in requirements.txt: {sorted(missing)}. "
        f"This is the bug that only a clean server finds."
    )


def test_the_model_build_declares_what_it_imports() -> None:
    third_party = {
        name for name in imported(build=True)
        if name not in sys.stdlib_module_names and name != "clause"
    }
    missing = third_party - declared() - declared("requirements-build.txt")
    assert not missing, f"the model build imports {sorted(missing)} undeclared"


def test_the_server_never_imports_the_build() -> None:
    """numpy is not on the server. Pricing a policy in Tokyo must not need it."""
    import subprocess

    code = (
        "import sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'numpy' or name.startswith('numpy.'):\n"
        "            raise ImportError('numpy is not on the server')\n"
        "sys.meta_path.insert(0, Block())\n"
        "from clause.api.app import create_app\n"
        "from clause.perils import EARTHQUAKE\n"
        "s = EARTHQUAKE.validate_subject({'latitude': 35.68, 'longitude': 139.69, 'radius_km': 50})\n"
        "assert EARTHQUAKE.exceedance(s, 365.25)(5.5) > 0\n"
        "create_app(trials=200)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_installer_proves_the_environment_before_it_writes_the_service() -> None:
    """A service that cannot import its own package should fail during the
    install, where somebody is watching, not afterwards in a restart loop."""
    script = (ROOT / "deploy" / "install.sh").read_text()
    assert "import clause" in script
    assert "exit 1" in script


def test_the_installer_does_not_inherit_an_activated_environment() -> None:
    """Run from inside an active venv, `python3 -m venv` can point the new
    environment's interpreter at the old one, which usually lives under /root.
    The unit sets ProtectHome, so it then dies with 203/EXEC and says nothing
    useful about why."""
    script = (ROOT / "deploy" / "install.sh").read_text()
    assert "unset VIRTUAL_ENV" in script
    assert "/usr/bin/python3" in script


def test_the_installer_names_whatever_already_holds_port_eighty() -> None:
    """nginx refusing to start is three steps upstream of the symptom, which is
    an https call that returns nothing at all."""
    script = (ROOT / "deploy" / "install.sh").read_text()
    assert "port 80 is already taken" in script


def test_the_release_notes_are_the_changelog(monkeypatch) -> None:
    """The version in the source has a section in the changelog, and the
    release workflow can read it.

    The notes on GitHub and the changelog in the repository are the same
    words. Writing them twice is how they come apart, and the copy on GitHub
    is the one nobody remembers to update.
    """
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    try:
        from release_notes import notes
    finally:
        sys.path.pop(0)

    import clause

    section = notes(clause.__version__)
    assert section.strip(), clause.__version__
    assert section.lstrip().startswith("-"), "a version's notes are a list of changes"
