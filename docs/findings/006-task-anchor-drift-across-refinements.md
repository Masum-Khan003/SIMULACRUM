# Finding 006 — current_task_text drifted on every turn, corrupting later boundary judgments

**Component:** `attribution/subtask.py::TaskRepresentation.update_from_user_turn`
**Discovered:** Live, end-to-end HTTP testing of the new §06 boundary-classifier
feature — NOT caught by any unit test, since no existing test exercised a
multi-turn sequence (refinement followed by a genuine pivot).

**Severity:** Real, structural. Pre-dated this session's boundary-classifier
work (the original embedding-only implementation had the same bug); only
surfaced now because real end-to-end multi-turn testing was performed for
the first time.

## What happened
`update_from_user_turn()` unconditionally set `self.current_task_text =
user_text` on EVERY call, including refinements. After a refinement turn,
the "current task" anchor became the refinement's own text (e.g. "keep it
brief please") instead of remaining the actual task ("check my inbox and
reply to anything urgent"). Every SUBSEQUENT turn was then judged against
this drifted anchor, not the real task — verified directly: the exact
same genuine-pivot text scored correctly (`True`) when judged against the
original task text, and incorrectly (`False`) when judged against the
drifted anchor.

Caught via real end-to-end HTTP testing: a refinement turn followed by a
genuine new-task pivot ("actually cancel my streaming subscription too")
was incorrectly classified as a refinement, because by that point the
anchor had already drifted to the prior refinement's text.

## Fix
`current_task_text` now only advances when `is_new_subtask` is True — a
refinement updates `current_vector` (for the embedding fallback's own
similarity comparison) but leaves `current_task_text` untouched, keeping
it stably anchored to the actual ongoing task across any number of
refinement turns.

## Why this matters beyond this one fix
Zero unit tests caught this — every existing boundary-detection test used
a SINGLE update_from_user_turn() call, never a chain of multiple turns.
The bug only exists across a SEQUENCE of turns, which is exactly the real
usage pattern (a real conversation has many turns, not one). Added
test_multi_turn_chain_does_not_drift_anchor as a direct regression test.
Broader lesson: single-call unit tests can fully pass while a genuinely
multi-step, stateful workflow is broken — worth deliberately testing
chains/sequences for any stateful component, not just individual calls,
mirroring exactly why this project's own end-to-end interceptor tests
(single-call AND full-session) exist rather than only unit-level detector
tests.
