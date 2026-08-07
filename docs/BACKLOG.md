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

- **Real async/background drift scheduling not built.** §03/§12 specify
  drift checks should run "off-path, async, on a rolling interval."
  What exists: a tested trigger-interval RULE (`should_check_drift()`)
  and an ON-DEMAND synchronous HTTP endpoint
  (`POST /sessions/{id}/check-drift`). No actual scheduler/background
  job exists — a caller must explicitly hit the endpoint.

- **Heuristic content-pattern fallback has a real evasion gap.** When
  GroqContentPatternDetector is unavailable, HeuristicContentPatternDetector
  misses obfuscated-format attacks (spelled-out digit substitution,
  @ /. character replacement) that the LLM-based primary catches — 2/5
  in the adaptive-evasion test. This is the safety margin during a
  Groq outage specifically, not normal-operation behavior.

- **§17 drift/re-baselining pipeline not built.** PSI-based statistical
  drift detection + champion/challenger promotion gate for the
  EXPLICIT detectors (distinct from goal-drift's LLM-based trajectory
  judgment, which IS built). Not started.

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
