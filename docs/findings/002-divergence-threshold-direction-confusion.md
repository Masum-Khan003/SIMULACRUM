# Finding 002 — Inverted threshold direction in test, not detector

**Component:** `tests/unit/test_param_divergence.py::test_custom_threshold_respected`
**Discovered:** Phase 1, writing tests for param-vs-task divergence detector (§09/§04)
**Severity:** Test-only. Detector logic (`check_param_divergence`,
`is_divergent = similarity < threshold`) was correct throughout.

## What happened
Wrote a test asserting `threshold=0.0` was "impossibly strict — nothing
should pass," expecting an unrelated call to be flagged as divergent.
Got `is_divergent=False` for a case with `similarity=0.0`.

Root cause: `is_divergent = similarity < threshold`. A LOW threshold is
PERMISSIVE (only similarity strictly below it gets flagged); a HIGH
threshold is STRICT (more similarities fall below it, more gets
flagged). `threshold=0.0` is therefore the most lenient possible
setting, not the strictest — I had the direction backwards when writing
the test's docstring and assertion.

## Fix
Rewrote the test to use `threshold=0.99` (stricter than any measured
on-topic similarity) against a genuinely on-topic call, proving the
override actually takes effect in the correct direction.

## Why this matters beyond this one fix
Same root cause category as finding 001: a fixture/test assumption
(here, about threshold semantics) diverging from what the code under
test actually does, surfacing as a confusing failure rather than an
obvious one. Direction-of-inequality bugs in threshold logic are easy
to get backwards when writing tests quickly — worth double-checking
threshold direction explicitly in any future detector that uses a
"below X is bad" or "above X is bad" pattern, since both directions
appear in this system (schema violations are boolean; divergence and
future statistical detectors are threshold-based in *both* directions
depending on what they measure).
