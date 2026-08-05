# Finding 003 — Circular import between detectors and interception

**Component:** `detectors/loop_rate.py` <-> `interception/interceptor.py`
**Discovered:** Phase 1, adding `detectors/exfiltration.py` and its
test — `test_exfiltration.py` was the first test file to import
`simulacrum.detectors` before anything imports `simulacrum.interception`,
which exposed a pre-existing circular dependency that had been silently
"working" only by accident of import order in every prior test file.

**Severity:** Structural. Was not caught by 130 passing tests before
this — a real gap in what "green" meant, worth being honest about.

## What happened
`loop_rate.py` (a detector) imported `SessionStore`/`CallOutcome` from
`interception.session_store`. `interception.interceptor` imports
check functions from `simulacrum.detectors`. That's `detectors` -> 
`interception` -> `detectors`, a genuine cycle.

Python's circular-import handling depends on which module is imported
FIRST: if `interception` finishes initializing before `detectors`
needs it, the partially-built module already has what's needed and it
silently works. Every prior test file happened to import in an order
that avoided tripping it. `test_exfiltration.py` imported
`simulacrum.detectors` as its very first import, tripping the cycle
for the first time and raising `ImportError: cannot import name
'LoopRateResult' from partially initialized module`.

## Fix
Moved `SessionStore`/`CallOutcome`/`CallAttempt`/`InMemorySessionStore`
out of `interception` entirely into a new top-level `simulacrum.session`
package with zero dependency on either `detectors` or `interception`.
Both packages now depend on `session` (a leaf), and `interception`
depends on `detectors` (one direction only) — the cycle is structurally
impossible now, not just avoided by import ordering.
`interception/__init__.py` re-exports the session types for backward
compatibility with existing `from simulacrum.interception import
InMemorySessionStore`-style imports.

## Why this matters beyond this one fix
A passing test suite does not prove an import graph is acyclic — it
only proves the import ORDERS actually exercised happen not to trip
the cycle. This is the same category of "green checkmark isn't the
whole story" lesson as findings 001/002, just at the module-dependency
level instead of the logic level. Worth a standing habit: when adding
a new module to an existing package, check what it imports FROM
other packages in this project, not just whether pytest currently
passes — a cycle can sit latent for many commits before the "wrong"
import order in a new file finally exposes it.

## Process improvement worth considering
A CI step that imports every package's `__init__.py` in multiple
different orders (or alphabetically reversed vs. forward) would catch
this class of bug immediately rather than waiting for it to surface
by chance. Not built yet — candidate for docs/BACKLOG.md.
