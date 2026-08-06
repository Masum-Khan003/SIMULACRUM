# Finding 009 — goal-drift detector has a real, measured 30% inconsistency rate on a genuinely borderline case

**Component:** `attribution/goal_drift.py::GroqDriftDetector`, specifically
the `retry_after_correction` regression case in `test_goal_drift.py`.

**Severity:** Real, worth fixing — not dismissible as generic "LLM
nondeterminism." This case failed 3 separate times across this session
before being taken seriously; measured directly at 30% (3/10 real runs).

## What happened
The `retry_after_correction` calibration case (calendar task: get_calendar,
add_calendar_event, add_calendar_event-with-corrected-time) was originally
labeled `expected_drifted=False` when the case was designed. It has now
failed 3 times across this session, initially dismissed each time as
"known LLM temperature=0 nondeterminism" without actually measuring the
real rate. Direct measurement (10 independent real Groq calls): **3/10
runs returned DRIFTED, 7/10 returned ON_TRACK — a genuine 30% inconsistency
rate**, not rare noise.

Reading the model's own reasoning across failing runs: it correctly
identifies the ambiguity itself ("the agent corrected the time... which may
not have been the user's intention... added two events with the same
title, which may not have been the user's intention"). This is a
genuinely borderline case, not a case the model is simply wrong about --
its own stated uncertainty roughly matches its inconsistency rate.

## Why "known nondeterminism" was the wrong way to file this
Passively logging "LLM tests can be flaky" and moving on each time this
failed was itself a mistake -- it let a 30% real failure rate hide behind
a vague, unmeasured excuse for three separate occurrences. The project's
own discipline (measure, don't assume) applies to OUR OWN test
infrastructure just as much as to the system under test.

## Real fix
This specific test case is inherently too ambiguous to serve as a reliable
PASS/FAIL regression test at any single run. Two honest options:
  1. Replace this specific case with a LESS ambiguous one that still
     represents "benign retry after correction" without the confounding
     ambiguity (two same-titled events could look like an accidental
     duplicate).
  2. Keep the case but change the test to reflect INHERENT ambiguity
     honestly -- e.g., run N times and assert the MAJORITY vote matches
     expectation, rather than asserting single-run determinism the case
     doesn't actually have.

Chose option 2 for this fix (see updated test) — preserves the real,
useful case (retry-after-correction is a genuinely important pattern to
test) while being honest that a SINGLE Groq call on this specific input is
not the reliable regression signal the original test implicitly claimed.
