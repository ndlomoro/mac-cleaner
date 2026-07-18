"""py2app manifest must list every top-level package (phase-1 regression: 'core' was missing)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _setup_packages() -> set[str]:
    text = (ROOT / "setup.py").read_text()
    match = re.search(r"[\"']packages[\"']\s*:\s*(\[[^\]]*\])", text)
    assert match, "packages list not found in setup.py"
    return set(ast.literal_eval(match.group(1)))


def test_setup_packages_covers_all_top_level_packages():
    on_disk = {
        p.parent.name
        for p in ROOT.glob("*/__init__.py")
        if p.parent.name not in {"tests", "dist", "build"}
    }
    missing = on_disk - _setup_packages()
    assert not missing, f"setup.py packages missing: {missing}"
