# Finding 004 — Shared global Prometheus gauge breaks test isolation

**Component:** `observability/metrics.py::APPROVAL_QUEUE_DEPTH`,
`tests/unit/test_observability.py::test_approval_queue_depth_reflects_real_pending_count`

**Discovered:** Phase 1, writing metric-verification tests — same
"verify real values, don't trust prometheus_client calls not to crash"
discipline §18 itself calls for, which is exactly what caught this.

**Severity:** Test-only, but revealed a real design gap in how the
metric itself will behave in a genuine multi-queue deployment.

## What happened
`APPROVAL_QUEUE_DEPTH` is a single, unlabeled, process-global
Prometheus Gauge — set via `.set(depth)` by ANY `ApprovalQueue`
instance's `_pending_count()`. The test captured `initial_depth` at
its own start, assuming that was a safe local baseline, then asserted
deltas relative to it. That works when the test runs alone
(`pytest test_observability.py::test_approval_queue_depth... ` in
isolation: PASSED) but fails when other tests in the same process ran
first and left the SAME global gauge at a different absolute value
from THEIR OWN queue instances (e.g. test_require_approval_action_recorded,
earlier in the same file, submits to its own queue without ever
resolving the request).

## Fix, not yet applied
Two real options, not yet chosen:
  (a) Label APPROVAL_QUEUE_DEPTH by a queue/session identifier, so
      each ApprovalQueue instance's depth is independently readable.
  (b) Accept ONE global approval queue is the actual real-deployment
      shape (§13 doesn't describe per-session approval queues), and
      fix the TEST instead to not assume delta-safety across a shared
      Gauge when other tests in the same process also mutate it —
      e.g. by resetting/unregistering the metric in a fixture, or
      running this specific test file with `pytest -p no:randomly`
      and accepting cross-test ordering dependency as documented,
      or clearing the registry between tests.

Not resolved in this session — tracked in docs/BACKLOG.md. Current
test suite passes because pytest happens to run files in an order
where this doesn't currently trip (same "worked by accident of order"
shape as finding 003), which is itself the concerning part.
