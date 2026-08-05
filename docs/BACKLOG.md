# Simulacrum — Tracked Backlog

Deferred items, logged at the point of deferral with the reasoning for
deferring and where they belong. Updated as items are picked up or new
ones get deferred. Nothing here is "forgotten" — it's explicitly
scheduled for later, not silently dropped.

## Open

- **Feature-schema hash/versioning** (§11 table, Palimpsest bug #2
  guard). Deferred at Phase 0 close: no calibration manifest format
  exists yet to hash. Belongs alongside real calibration work
  (Phase 2, §15) when the manifest shape is actually decided.

- **Redis client / session store** (§03, §06). `config.Settings`
  validates `SIMULACRUM_REDIS_URL` but no code actually connects yet.
  Needed for: session-level detectors (permission escalation,
  exfiltration — both require tool-category footprint tracked across
  a session, not per-call), trajectory model, circuit-breaker state.
  Triggered by: starting the first session-level detector.

- **Real MiniLM embedding model** (§09, §12, §20, gap 10). Currently
  using FakeTaskEmbedder (hash-based) and FakeSemanticEmbedder
  (bag-of-words) — both explicitly documented as logic-proving, not
  production-quality. Triggered by: real threshold calibration work
  (§15) against a labeled corpus, Phase 2.

- **Threshold calibration, both boundary and divergence** (§06, §09,
  §15). `DEFAULT_BOUNDARY_THRESHOLD = 0.5` and
  `DEFAULT_DIVERGENCE_THRESHOLD = 0.15` are placeholders, anchored to
  real-but-fake-embedder similarity numbers (see chat log / commit
  d29afce), not real calibration. Requires: real MiniLM + labeled
  corpus + `MIN_CALIBRATION_SAMPLES` met. Belongs in Phase 2.

- **Remaining attack classes** (§04, 4 of 6 not yet built):
  permission escalation, exfiltration, goal drift, resource-abuse/
  runaway loops (with retry-vs-evasion split, §09 gap 5). Permission
  escalation and exfiltration are session-level — blocked on the
  session store above. Goal drift is explicitly the trajectory
  model's job (§10) — blocked on Phase 2 model work. Resource-abuse
  loop-rate is buildable per-call/session once session store exists.

- **Tier engine proper** (§13): flag/require-approval/block gradation
  beyond today's binary allow/block, approval queue, timeout-deny
  policy (30 min default, §13 v2). Current interceptor only does
  binary allow/block on detector findings. Needs both detectors wired
  in first (this step) before it's meaningful to gate on.

- **Circuit breaker** (§12): wraps every model/detector call,
  risk-tiered fail-open/closed on guardrail unavailability — distinct
  from today's "block on detected violation" logic. Not yet started.

- **Attack-target tools have no registered schema** (send_payment,
  set_forwarding_rule, delete_data, modify_permissions). Intentional
  — they're not part of any legitimate task template, so schema
  conformance correctly cannot evaluate them (raises
  UnregisteredSchemaError, proven in test_injection.py). Worth
  revisiting only if a future attack class needs to test malformed
  calls to these specific tools too.

## Resolved

- ~~LabeledAttackSession naming collision~~ — RESOLVED. Shared
  dataclass moved to attack_suite/common.py, both param_tampering.py
  and injection.py import it, alias removed from __init__.py.
  injected_tool_name is optional (None default) since not every
  attack class substitutes a whole tool.


- ~~Divergence detector not wired into interceptor~~ — RESOLVED.
  intercept_and_call() now runs both schema conformance and
  param-vs-task divergence on every call; either flagging blocks.
  Proven end-to-end against normal corpus + both attack corpora
  (param_tampering, injection). See test_interceptor.py.

- ~~Injection/escalation detectors proven but not wired into
  interceptor~~ — RESOLVED. intercept_and_call() now runs schema,
  divergence, AND permission escalation (against footprint including
  the current call) on every call; any flagging blocks. Every call
  logged to session store regardless of outcome. Proven end-to-end
  against normal corpus + all three attack corpora. See
  test_interceptor.py.

- ~~Loop-rate detector proven but not wired into interceptor~~ —
  RESOLVED. intercept_and_call() now runs schema, divergence,
  escalation, AND loop-rate (retry-vs-evasion split) on every call.
  Call outcome (ALLOWED/BLOCKED) logged via append_attempt so future
  retries are correctly classified. Proven end-to-end via
  test_evasion_retry_blocked_by_loop_rate_through_real_interceptor.
  NOTE: benign-retry (TOOL_ERROR outcome) path still not exercised
  end-to-end — no stub tool simulates a TOOL_ERROR response yet. Real
  fix needs at least one stub tool with a simulated failure mode.

- **CI import-order check** (finding 003). No current check catches
  circular imports that happen to work under the test suite's actual
  import order. Candidate: a CI step importing every package in
  reverse-alphabetical order too, to surface latent cycles early.

- ~~Exfiltration detector proven but not wired into interceptor~~ —
  RESOLVED. All 5 Phase-1 detectors (schema, divergence, escalation,
  loop-rate, exfiltration) now run on every call through
  intercept_and_call(). Frequency-variant attack corpus proven blocked
  end-to-end. See test_interceptor.py.

- ~~Circuit breaker not built~~ — RESOLVED. CircuitBreaker wraps the
  full 5-detector scoring path as ONE unit (documented simplification
  vs. per-detector breakers — see circuit_breaker.py). On open circuit,
  fallback is decided per §07 tool risk tier: READ_ONLY/REVERSIBLE_WRITE
  fail open, IRREVERSIBLE_* fail closed, unregistered tool defaults to
  fail closed. guardrail_bypassed field distinguishes this from a
  normal scored decision. Proven via
  test_open_circuit_fails_open_for_read_only_tool and
  test_open_circuit_fails_closed_for_irreversible_tool.

- **Per-detector circuit breakers** (deferred scope decision, see
  circuit_breaker.py docstring). Current breaker trips on ANY scoring
  failure across all 5 detectors as one unit. A broken embedding
  model, for instance, currently trips the SAME breaker as a broken
  schema registry, even though only one detector is actually affected.
  Revisit if this coarseness proves too blunt in practice.

- ~~Tier engine not wired into interceptor~~ — RESOLVED.
  intercept_and_call() now decides full ALLOW/FLAG/REQUIRE_APPROVAL/
  BLOCK via decide_response_tier (detector-flag-count severity proxy).
  REQUIRE_APPROVAL submits to ApprovalQueue, does NOT execute — a
  separate explicit step (caller checks decided outcome, then calls
  tool_registry directly) triggers execution post-approval, keeping
  ApprovalQueue dependency-free. Proven via
  test_require_approval_call_does_not_execute_until_approved.

- **SessionStore has no PENDING call-outcome.** REQUIRE_APPROVAL calls
  are currently logged as CallOutcome.BLOCKED (call did not execute)
  since SessionStore's CallOutcome enum only has ALLOWED/BLOCKED/
  TOOL_ERROR. This conflates "held pending human decision" with
  "actively blocked by a detector" in session history/loop-rate
  classification. Real fix: add CallOutcome.PENDING_APPROVAL, distinct
  from BLOCKED, and update loop_rate.py's evasion classification to
  treat retries after PENDING differently than retries after an
  actual BLOCKED finding. Not done here to avoid scope creep in an
  already-large wiring step.

- ~~Real Redis wiring~~ — RESOLVED. RedisSessionStore implements the
  exact same SessionStore protocol as InMemorySessionStore, proving
  the Phase-1 abstraction actually pays off. Docker Compose service
  added (docker-compose.yml). Real round-trip proven for outcome
  enums and special-character params through JSON serialization.

- **CI needs a Redis service container** (§22 implication of the item
  above). test_redis_session_store.py requires `docker compose up -d`
  to pass — CI must start the Redis service before running the test
  suite, or this file needs to be excluded/marked and run separately.
  Not yet reflected in any CI config since no .github/workflows file
  exists yet (§22 is itself still backlog). Flag when CI is built.

- ~~Observability metrics not wired in~~ — RESOLVED. Prometheus
  metrics (action volume by tier, per-detector flags, breaker state/
  trips, approval queue depth/outcomes) recorded on every real
  decision in intercept_and_call() and ApprovalQueue. Verified against
  REAL scraped values, not just "doesn't crash" (§18's own stated
  discipline). Finding 004 (shared global gauge test-isolation bug)
  found and fixed in the same step.

- **APPROVAL_QUEUE_DEPTH remains a single unlabeled global gauge**
  (finding 004, option (b) chosen over (a)). Correct for current
  single-conceptual-queue architecture; would need per-queue labeling
  if §23's Phase-3 ops/security-approver role ever introduces genuinely
  separate concurrent approval queues.

- ~~Docker Compose full stack (Redis + API + Prometheus + Grafana)~~ —
  RESOLVED. Dockerfile + expanded docker-compose.yml, Prometheus
  scraping the API's real /metrics endpoint (confirmed "health": "up"),
  Grafana provisioned with dashboard-as-code JSON (5 panels matching
  §18's metric list), not clicked together manually. Verified end-to-
  end: metric family registration -> API exposure -> Prometheus
  scrape -> queryable data, for both labeled and unlabeled metrics.

- **Real POST /intercept endpoint** (deliberately deferred this step).
  Current API only exposes /health and /metrics; nothing yet drives
  real interception traffic through the containerized service itself
  (all real traffic so far is from pytest, a separate process).
  Building this is legitimate future work — needs its own design pass
  for request/response schema and session lifecycle across HTTP
  requests, not bolted on as a side effect of a metrics-visibility fix.

- **Labeled metrics show no series until first use** (documented
  behavior, not a bug). simulacrum_circuit_breaker_state and
  simulacrum_detector_flags_total won't appear in Prometheus queries
  until intercept_and_call() actually runs at least once with real
  label values. Grafana panels for these will show "No data" on a
  freshly-started stack until real traffic occurs — expected, not
  broken.
