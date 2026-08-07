# Simulacrum — Backlog

Live, accurate list of genuinely open work, verified against the actual
codebase (not aspirational or historical — that detail lives in
docs/findings/*.md and git history). Rewritten from scratch after an
audit found the previous version had accumulated stale, contradictory
entries (append-only history without removing superseded text).

## Open — Priority

- **Finding 010: param-vs-task divergence generalization gap on real
  external data.** Verified-correct numbers (after 2 rounds of
  ground-truth correction, both documented in docs/findings/010-*.md):
  MiniLM 78.4% recall / 74.7% FP rate on real AgentDojo attacks vs
  resisted trajectories; fake embedder 90.0% / 85.2%. A real, tested
  partial fix exists (exclude low-param calls from trajectory
  aggregation: MiniLM FP 74.7%->59.7%, fake FP 85.2%->76.2%) but is
  NOT ported to the production `check_param_divergence` detector
  (currently single-call, not trajectory-level — porting needs real
  design work, not a drop-in change). Single most important open item.

- ~~Real async/background drift scheduling not built~~ — RESOLVED.
  DriftScheduler runs a genuine asyncio background loop (started/
  stopped via FastAPI lifespan events), tracking calls-since-last-check
  per session and caching a standing decision (§12'''s own language).
  Real, timing-correct end-to-end proof: real FastAPI lifespan startup,
  real calls through a session, real time.sleep, background loop picks
  it up UNATTENDED — nobody calls the on-demand endpoint. New
  GET /sessions/{id}/drift-status retrieves the standing decision
  without triggering a new check (distinct from the existing POST
  .../check-drift, which still does synchronous on-demand checks).
  One real bug caught and fixed along the way: a keyword-argument name
  mismatch (calls_since_last vs calls_since_last_check) against the
  existing tested drift_trigger.py function.

- ~~Heuristic content-pattern fallback has a real evasion gap~~ —
  PARTIALLY RESOLVED. Added real, tested regex patterns for word-
  based @/. substitution and spelled-out digit sequences, verified
  against §16'''s adaptive-evasion ladder: fallback now catches 4/5
  attempts (up from 3/5) — genuinely closes the format-obfuscation
  gap. ONE case remains, HONESTLY UNCLOSEABLE by a stateless
  heuristic: data-free contextual references ("same fields as
  always") carry no matchable content at all — closing this
  structurally requires reasoning about conversation history, which
  is exactly why GroqContentPatternDetector remains the PRIMARY
  mechanism, not a nice-to-have. This residual gap is the real,
  irreducible safety-margin cost of a Groq outage, now precisely
  characterized rather than vaguely stated.

- ~~§17 drift/re-baselining pipeline not built~~ — RESOLVED. Three
  real, tested components: compute_psi() (verified both directions
  against real MiniLM distributions -- 0.0035 for same distribution,
  10.95 for genuinely shifted), VersionTracker (event-driven
  immediate-recalibration trigger, §17 v2), evaluate_promotion()
  (champion/challenger gate). REAL, meaningful insight from testing
  the gate against this session'''s own finding-010 fix: the gate
  correctly REJECTS the min-param-exclusion fix, because it has a
  genuine recall regression (78.4%->73.1%) despite a real FP
  improvement (74.7%->59.7%) -- exactly the kind of appealing-looking
  tradeoff a human might wave through without a strict, automated
  gate. This directly informs the still-open finding-010 production-
  port decision: the fix as currently tuned should NOT be auto-
  promoted; either the threshold needs joint recalibration (not just
  the aggregation change) or a human must explicitly accept the
  recall tradeoff, not silently inherit it.

- **§10 trajectory sequence model — LLM reasoning used instead, not a
  literal sequence model.** Goal-drift detection is real and working
  (GroqDriftDetector), but §10 specifically describes a sequence model
  over (tool, param-embedding, timestamp, ...) tuples. Worth a
  deliberate decision: is LLM-based reasoning a legitimate substitute
  for §10's literal spec, or should both exist? Not decided.

## Open — Real, Lower Priority

- **Only 3 of §08's target 5-8 task types.** More task-type diversity
  is one candidate direction for narrowing finding 010's gap, not yet
  attempted.

- **Formal confidence calibration reporting (§05/§15) not built as a
  standalone artifact.** Real calibration evidence exists throughout
  (percentile derivation, real similarity distributions measured) but
  no formal Brier-score/reliability-diagram deliverable exists.

- **CI import-order check (finding 003) never built.** No automated
  check catches circular imports that happen to work under the test
  suite's actual import order (the exact bug finding 003 documented).

- **CI needs a Redis service container.** test_redis_session_store.py
  and test_api.py require live Redis — no .github/workflows exists yet
  to provision this for CI (§22 itself is still backlog).

- **Per-detector circuit breakers** (deferred scope decision, stated
  directly in circuit_breaker.py's docstring). Current breaker wraps
  all 6 detectors as ONE unit — a broken embedding model trips the
  same breaker as a broken schema registry.

- **APPROVAL_QUEUE_DEPTH is a single unlabeled global Prometheus
  gauge** (finding 004's resolved scope). Correct for the current
  single-conceptual-queue architecture; would need per-queue labeling
  if a future ops/security-approver role introduces genuinely separate
  concurrent queues.

- **Feature-schema hash/versioning (§11, Palimpsest bug #2 guard) not
  built.** No calibration-manifest format exists yet to hash against.

- **HF_TOKEN not configured** (minor). MiniLM downloads show
  "unauthenticated requests" warnings — functionally fine for a public
  model, worth setting for higher rate limits if used heavily.

- **Attack-target tools (send_payment, etc.) have no registered
  schema** (intentional — they're not part of any legitimate task
  template, so schema conformance correctly cannot evaluate them,
  proven in test_injection.py). Revisit only if a future attack class
  needs malformed-call testing against these specific tools.

## Phase 3 / Stretch (correctly out of MVP scope per blueprint §23)

- Multi-instance circuit-breaker state (Redis-backed)
- Independent ops/security-approver role, separate from the
  task-initiating user
- Second agent-framework integration
- Exportable per-session investigation report
- Lightweight human-approval web UI (explicitly out of scope — a
  functional CLI/API is in scope, a polished web UI is not, per §02)

## External, not code issues

- AgentDojo's own `--max-workers` multiprocessing path has a real,
  reproducible bug (`AttributeError: 'str' object has no attribute
  'name'` inside their own `benchmark_suite` function) — worked around
  by running sequentially, not something to fix in our own codebase.
