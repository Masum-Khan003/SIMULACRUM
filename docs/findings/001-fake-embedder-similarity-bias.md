# Finding 001 — FakeTaskEmbedder cosine similarity bias toward false positives

**Component:** `attribution/embedding.py::FakeTaskEmbedder`
**Discovered:** Phase 0, writing tests for sub-task boundary logic (§06)
**Severity:** Would have silently invalidated any test asserting boundary
behavior — logic was correct, test fixture was not.

## What happened
`FakeTaskEmbedder.embed()` originally mapped SHA256 digest bytes to
`[0.0, 1.0]` — an all-positive vector space. Cosine similarity between
two random all-positive vectors is structurally biased high (no negative
components can cancel the dot product toward zero). Result: two
semantically unrelated instructions ("book a flight to London" vs.
"cancel my streaming subscription") scored above the 0.5 boundary
threshold as if they were the same task.

`test_unrelated_instruction_opens_new_subtask` and
`test_multiple_boundaries_increment_index` failed — correctly. The
sub-task boundary LOGIC (`TaskRepresentation.update_from_user_turn`)
was doing exactly what it was told; the fixture feeding it was unfit
for the job.

## Fix
Mapped digest bytes to `[-1.0, 1.0]` (zero-centered) instead. Unrelated
random vectors now average toward cosine similarity ~0, matching the
geometry a real embedding model would produce for unrelated inputs.

## Why this matters beyond this one fix
Same category as Palimpsest finding 011: a test/fixture-generation
assumption silently diverged from what the code-under-test actually
needed, and it looked like a logic bug until inspected. Direct lesson
applied going forward: when a fake/stub stands in for a real ML
component (embeddings now; will recur for the trajectory model), audit
the fake's OWN statistical properties before trusting its test results
— a fake that's merely deterministic is not automatically a fake that's
unbiased.
