"""
Pytest-integrated wrapper around tests/check_import_order.py (finding
003). Runs the real subprocess-based check as part of the normal
suite, so it's caught by routine `pytest` runs, not just a separately-
remembered CI step.
"""
import subprocess
import sys
from pathlib import Path


def test_no_circular_imports_in_any_discovered_order():
    script = Path(__file__).parent.parent / "check_import_order.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Import-order check failed (finding 003 regression risk):\n{result.stdout}\n{result.stderr}"
    )
