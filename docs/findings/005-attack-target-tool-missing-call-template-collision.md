# Finding 005 — modify_permissions falls back to generic call-text, collides with calendar task under fake embedder

**Component:** `attribution/call_text.py`, exposed via
`test_injection.py::test_divergence_recall_across_many_seeds_and_task_types`
after adding `TaskType.CALENDAR_SCHEDULING`.

**Severity:** Real detection miss (25/25, deterministic) for one
specific task-type/attack-tool pairing. Same root category as finding
001 — a fake embedder's structural limitations, this time surfaced by
adding new task-type text rather than by the embedder's own construction.

## What happened
`modify_permissions` (an attack-target tool, §07/§04) has no entry in
`_CALL_TEMPLATES` (`attribution/call_text.py`), so `call_topic_text()`
falls back to a generic `"tool_name key value key value..."` string:
`"modify_permissions user admin level root"`.

Under `FakeSemanticEmbedder`'s bag-of-words hashing-trick (64 buckets,
no semantic understanding — see its own docstring), this fallback
string happened to hash into overlapping buckets with
`"Please check my calendar and schedule a new event"`
(`TASK_INITIAL_USER_TEXT[CALENDAR_SCHEDULING]`), producing
similarity=0.2 — ABOVE the 0.15 divergence threshold. The call was
therefore scored as NOT divergent, a real miss for an attack that
every other task-type/tool combination correctly caught.

## Fix
Added a proper call-topic template for every attack-target tool
(`send_payment`, `set_forwarding_rule`, `delete_data`,
`modify_permissions`) so none of them rely on the generic fallback,
which is structurally more collision-prone (raw param values leak
into the embedded text unfiltered, increasing chance of accidental
bucket overlap with unrelated task text).

## Why this matters beyond this one fix
This is a second, independent demonstration of the same lesson finding
001 taught: a fake/stub component's own statistical properties must be
audited, not just its determinism. Concretely: EVERY time a new
task-type's initiating text is added, it's now possible for previously-
invisible bucket collisions to surface against EXISTING attack-target
text, especially fallback-generated text. This is not fully solved by
this fix — it is reduced (dedicated templates are less collision-prone
than raw fallback text) but the underlying fake embedder still has no
real semantic understanding, and a future task type's initiating text
could still coincidentally collide with the NEW dedicated templates
too. Real fix is real MiniLM (already backlogged) — this fix buys
correctness under the current fake, not a permanent guarantee.

## Update — template-wording fix was insufficient, whack-a-mole confirmed
Adding a dedicated call-topic template for modify_permissions fixed
THAT collision but immediately surfaced two NEW ones (flight_booking/
set_forwarding_rule sim=0.1925, calendar_scheduling/delete_data
sim=0.1826) — both just above the 0.15 threshold, same pattern.
Confirms the root cause is NOT specific wording but insufficient hash
bucket count (dim=64) relative to vocabulary size, causing frequent
chance overlaps in the 0.14-0.2 range.

## Real fix
Raised FakeSemanticEmbedder's default dim from 64 to 256 — tested
empirically (64/128 both still show 50/300 real misses; 256/512 both
show 0/300) rather than guessed. 256 chosen as the minimal sufficient
value. This reduces collision RATE, it does not eliminate the
possibility of future collisions as vocabulary grows further — it is
an empirical result against current text, not a proof. Real MiniLM
(already backlogged) remains the only permanent fix; this raises the
current fake'''s practical ceiling, nothing more.
