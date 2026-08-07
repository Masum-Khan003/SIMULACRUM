"""
CI import-order check (finding 003): a passing test suite does NOT
prove an import graph is acyclic -- it only proves the import orders
actually exercised happen not to trip a circular import. Finding 003
(detectors <-> interception circular import) sat latent for many
commits before a NEW test file's import order finally exposed it.

This script imports every top-level simulacrum subpackage in several
DIFFERENT orders, each in a fresh subprocess (so no module-caching
from a prior import can mask a real problem), and fails loudly if any
ordering raises an ImportError. Run in CI as a dedicated step, not
folded into pytest itself, since its whole point is testing raw
import behavior outside any test-runner's own import machinery.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _discover_subpackages() -> list[str]:
    src_dir = Path(__file__).parent.parent / "src" / "simulacrum"
    subpackages = []
    for item in sorted(src_dir.iterdir()):
        if item.is_dir() and (item / "__init__.py").exists() and item.name != "__pycache__":
            subpackages.append(f"simulacrum.{item.name}")
    return subpackages


def _try_import_order(*, modules: list[str]) -> tuple[bool, str]:
    """Runs a fresh subprocess importing each module in the given
    order, one `import X` statement per line. Returns (success, output)."""
    import_lines = "\n".join(f"import {m}" for m in modules)
    result = subprocess.run(
        [sys.executable, "-c", import_lines],
        capture_output=True,
        text=True,
        timeout=30,
    )
    success = result.returncode == 0
    return success, result.stderr


def main() -> int:
    modules = _discover_subpackages()
    if not modules:
        print("ERROR: no simulacrum subpackages discovered -- check discovery logic")
        return 1

    print(f"Discovered {len(modules)} subpackages: {modules}")
    print()

    orderings = {
        "forward alphabetical": sorted(modules),
        "reverse alphabetical": sorted(modules, reverse=True),
    }

    all_passed = True
    for name, ordered_modules in orderings.items():
        success, stderr = _try_import_order(modules=ordered_modules)
        status = "PASS" if success else "FAIL"
        print(f"[{status}] {name}: {ordered_modules}")
        if not success:
            all_passed = False
            print(f"  Error output:\n{stderr}")
        print()

    if all_passed:
        print("All import orderings succeeded -- no latent circular imports detected.")
        return 0
    else:
        print("FAILED: at least one import ordering raised an error -- real circular import risk.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
