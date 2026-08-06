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

- ~~pyproject.toml missing runtime dependencies~~ — RESOLVED.
  redis/fastapi/uvicorn/prometheus-client declared as real
  dependencies, pytest/httpx as dev extras. Verified via genuine
  fresh-venv install (not the session'''s existing .venv) — 177/177
  passing using ONLY pyproject.toml-declared deps, per §22's
  fresh-clone-verification discipline.

- ~~Only 2 task types~~ — RESOLVED. Added TaskType.CALENDAR_SCHEDULING
  (get_calendar/add_calendar_event), also closing a real gap where no
  stub tool exercised RiskTier.REVERSIBLE_WRITE. Surfaced two real
  issues in the process: (1) missing schema registration for the new
  tools (fixed immediately), (2) finding 005 — FakeSemanticEmbedder
  bucket collisions causing real detection misses, root-caused to
  insufficient hash dimensionality (fixed empirically, dim 64->256),
  and (3) test_interceptor.py's attack-corpus assertions had baked in
  an incorrect assumption (every task tool is IRREVERSIBLE_*) that a
  REVERSIBLE_WRITE tool correctly violated — fixed to assert the real
  invariant (flagged by >=1 detector) instead of a specific tier
  outcome. Still only 3 of §08's target 5-8 task types — remains
  open, smaller gap than before.

- ~~SessionStore has no PENDING call-outcome~~ — RESOLVED. Added
  CallOutcome.PENDING_APPROVAL, distinct from BLOCKED. interceptor.py
  now logs REQUIRE_APPROVAL calls with this outcome. loop_rate.py's
  evasion classification explicitly excludes PENDING_APPROVAL from
  both evasion and benign-retry categories (neither applies — it'''s
  a distinct, expected situation). Proven via
  test_retry_after_pending_approval_not_classified_as_evasion_or_benign
  and test_require_approval_call_logged_as_pending_not_blocked (real
  end-to-end through the interceptor, not just the isolated detector).

- ~~Real POST /intercept endpoint~~ — RESOLVED. Full HTTP API: POST
  /sessions (start), POST /sessions/{id}/intercept (real interception
  through the complete 5-detector + circuit-breaker + tier-engine
  pipeline, using REAL RedisSessionStore not in-memory), GET/POST
  /approvals/{id} for the human-approval flow. All discovered error
  cases (unregistered tool, unknown session, invalid task_type,
  double-decide) return clean structured 4xx, not raw 500s — the
  unregistered-tool case was caught manually as a real unhandled
  exception before being fixed, not assumed correct. 10 new API tests,
  full round-trip including approval decide/re-decide conflict.

- ~~Explainability layer (§14) not built~~ — RESOLVED. Explainer
  Protocol with two implementations: TemplateExplainer (deterministic,
  dependency-free, the required §20 fallback) and GroqExplainer (real
  LLM-generated explanation via Groq's free-tier API, fails open to
  the template on ANY exception). Both success and failure paths
  proven with REAL network calls (a genuinely invalid key for the
  fail-open test, a real key for the success test) — not mocked.
  Wired into the API: non-ALLOW decisions now return a real natural-
  language explanation referencing actual detector findings, honestly
  hedged on intent per §06's correlational-not-certain discipline.
  groq_api_key added to Settings as a DELIBERATE, documented exception
  to the no-default rule (absence is valid config, not misconfig,
  since the whole feature is optional by design).

- ~~Real MiniLM embedding model~~ — RESOLVED. MiniLMEmbedder
  (sentence-transformers, all-MiniLM-L6-v2, CPU) implements the same
  TaskEmbedder protocol as the fakes — zero changes needed elsewhere.
  Gated as an optional `ml` extra (NOT a core dependency) + opt-in via
  SIMULACRUM_USE_REAL_EMBEDDINGS=1, deliberately, to preserve the
  lightweight fresh-venv install verified earlier this session (torch
  is a heavy dependency most test paths don't need). Real calibration
  data: on-topic similarity 0.30-0.71 (mean 0.51, n=120), off-topic
  -0.03-0.15 (mean 0.04, n=240), ZERO overlap across 360 real samples
  — cleared MIN_CALIBRATION_SAMPLES. Retires the root cause behind
  findings 001 and 005 (fake embedder collision fragility) — proven
  by re-running the EXACT calendar_scheduling/modify_permissions
  pairing that exposed finding 005, now correctly caught via real
  HTTP + real MiniLM.

- **Two separate divergence thresholds, not one shared constant** —
  real bug found and fixed in this same step: FakeSemanticEmbedder and
  MiniLM have fundamentally different similarity distributions, so
  FAKE_DIVERGENCE_THRESHOLD (0.15) and MINILM_DIVERGENCE_THRESHOLD
  (0.20) are now separate calibrated constants, threaded through
  intercept_and_call()'s new divergence_threshold parameter and
  AppState's embedder-dependent selection. Discovered by raising the
  shared threshold and immediately breaking legitimate
  FakeSemanticEmbedder-based calls in the existing test suite —
  caught before commit, not after.

- **HF_TOKEN not configured** (minor). MiniLM model downloads show
  "unauthenticated requests" warnings — functionally fine (public
  model, no auth required), but worth a HF_TOKEN env var for higher
  rate limits if this is used heavily. Not urgent.

- ~~Sub-task boundary detection: embedding-only signal too weak~~ —
  RESOLVED via architectural upgrade, not recalibration. Real MiniLM
  calibration showed genuine, measured overlap (up to 240 samples,
  multiple phrasing styles) between refinement and new-task
  similarity distributions — root-caused to this being a REASONING
  task, not a pure similarity task. Built GroqBoundaryClassifier
  (real LLM reasoning, primary) + EmbeddingBoundaryClassifier
  (deterministic fallback, demoted from primary). 8/8 correct on
  clear cases; ambiguous edge cases produce defensible, inspectable
  reasoning rather than a confident-but-wrong number. New
  POST /sessions/{id}/turn endpoint wired end-to-end.

- ~~Finding 006: current_task_text drift across refinement turns~~ —
  RESOLVED. Real structural bug (predated this session, only surfaced
  by first-ever multi-turn end-to-end test) — current_task_text now
  only advances on an actual new-sub-task verdict, not every turn.

- ~~Goal drift (6th of 6 attack classes, §04/§10)~~ — RESOLVED for the
  ON-DEMAND case. GroqDriftDetector (real trajectory reasoning) +
  NullDriftDetector (fails open to not-flagged, the correct
  conservative default for this least-certain detector). Found and
  fixed a REAL, serious bug during calibration: a forced one-word
  verdict (no reasoning room) gave WRONG answers on 2/6 real test
  cases (a plain flight-booking sequence, a calendar retry-after-
  correction — both flagged DRIFTED incorrectly). Allowing 1-2
  sentences of reasoning before the verdict fixed all 6/6 cases,
  including the hardest one (slow, subtle escalation). All 6 encoded
  as permanent regression tests (test_goal_drift.py) so a future
  "optimization" that reintroduces the forced-verdict bug gets caught
  automatically. POST /sessions/{id}/check-drift wired end-to-end
  against REAL session call history from real Redis.

- **True async/background drift scheduling NOT built** (honest gap,
  stated directly — this is NOT done, despite goal drift itself being
  marked resolved above). §03/§12 specify drift checks should run
  "off-path, async, on a rolling interval," with a "standing per-
  session risk decision cached in the session store." What exists
  today is a pure, tested trigger-interval RULE
  (should_check_drift()) plus an ON-DEMAND synchronous HTTP endpoint
  — usable right now, but not automatic. Real background scheduling
  (a scheduler process/job queue, periodic execution without a caller
  explicitly hitting the endpoint, cached standing risk state) is
  separate, larger infrastructure — genuinely bigger than a mechanical
  follow-up, deserves its own design pass before building.

- **PRIORITY — real, complete blind spot found via §16 adversarial
  testing (finding 007 update)**: an in-baseline tool with a
  semantically-camouflaged but short payload evades ALL THREE relevant
  detectors (divergence: camouflage reads as task-relevant; escalation:
  structurally can't see in-baseline misuse; exfiltration: content
  check is crude character-length, doesn't catch short camouflaged
  payloads). Real fix needed: a dedicated content-pattern/data-shape
  detector (does this text resemble exported records/credentials/bulk
  PII, semantically, not just \"is it long\") — genuine new detector
  work, not a threshold tweak. This is the most consequential open
  item in the backlog; found by deliberately trying to camouflage an
  attack rather than assuming coverage.

- ~~PRIORITY: real, complete blind spot (finding 007)~~ — RESOLVED.
  Built GroqContentPatternDetector (real LLM content-reasoning,
  primary) + HeuristicContentPatternDetector (regex/keyword fallback)
  as a 6th detector, closing the gap where an in-baseline tool with
  camouflaged content evaded divergence/escalation/exfiltration.
  Calibrated against real cases: correctly catches the exact gap
  case + a subtle contact-list exfiltration attempt with no obvious
  keywords; correctly stays quiet on 3/4 benign cases (one false
  positive on a legitimate password-reset notification, judged an
  acceptable tradeoff given false-positive cost is much lower than
  false-negative cost for this specific detector). Wired into
  intercept_and_call() as a required (no-default) 6th detector.

- **Real regression caught and fixed during finding-007 wiring**: 
  rewriting interceptor.py from a mental model (not diffed against
  the actual prior version) silently DROPPED all Prometheus metrics
  instrumentation (record_action, record_detector_flag,
  record_circuit_breaker_state/trip) that had been correctly wired in
  a much earlier commit. Caught by test_observability.py'''s real-
  value assertions — exactly the discipline §18 exists to enforce.
  Root cause: reconstructing a file from memory instead of diffing
  against git history. Lesson: when rewriting an existing file for a
  new feature, diff against the actual current version (git show/git
  diff), never reconstruct from assumption, even when the change
  feels additive.

- **Heuristic content-pattern fallback has a real evasion gap** (found
  via §16 adaptive-evasion test). Missed 2/5 obfuscated-format attempts
  that the real Groq-backed detector caught (spelled-out digit
  substitution, data-free contextual reference). This is the SAFETY
  MARGIN during a Groq outage, not a flaw in normal operation — but a
  real, worth-considering gap. Candidate fix: expand
  HeuristicContentPatternDetector'''s pattern set to catch common
  obfuscation techniques (digit-word substitution, at/dot replacement),
  weighed against added complexity for a fallback path that's meant to
  stay simple and dependency-free.

- **LLM-backed regression tests exhibit real, occasional non-
  determinism** (observed directly this session: test_real_calibration_case
  [retry_after_correction] failed once, passed on immediate re-run,
  same input, same temperature=0). This is expected behavior for
  hosted LLM APIs, not a bug in our code — but worth flagging
  honestly: a single CI run failing on one of the Groq-backed
  regression tests (goal_drift, boundary_classifier,
  content_pattern, adaptive_evasion) should prompt a re-run before
  treating it as a real regression, not an automatic red flag.
  Consider: retry-once-on-failure for these specific tests, or
  accepting occasional flakiness as a known property, documented
  here rather than chased as a phantom bug.

- **PRIORITY — finding 008: min-margin calibration vulnerable to
  single-sample poisoning, percentile mitigation validated but NOT
  adopted**. A single poisoned calibration sample fully degrades
  detection (5/6 -> 3/6 real attacks, real measured data), REGARDLESS
  of total sample size (confirmed at n=200, meeting
  MIN_CALIBRATION_SAMPLES) -- structural flaw in min(), not a
  volume-dependent attack. derive_threshold_percentile() (5th
  percentile) validated as ~80x more poisoning-resistant at realistic
  scale, real evidence not theory. NOT yet wired into production
  thresholds (FAKE_DIVERGENCE_THRESHOLD, MINILM_DIVERGENCE_THRESHOLD
  still min-margin-derived) -- real follow-up: full recalibration
  pass using percentile methodology, same rigor as original MiniLM
  calibration. Should also review whether OTHER thresholds in this
  system (boundary, rate, content-size) use min/max-derived
  calibration with the same vulnerability.

- ~~PRIORITY: finding 008 mitigation not adopted~~ — RESOLVED.
  MINILM_DIVERGENCE_THRESHOLD recalibrated from min-margin (0.20,
  vulnerable) to 1st-percentile (0.3030) against 420 REAL MiniLM
  samples. Evidence-based percentile choice (not a default): swept
  1/2/3/5/8th percentiles, 1st achieved full attack coverage (6/6)
  at the lowest false-positive cost (0.71% vs 4.76% at 5th) while
  still ~65x more poisoning-resistant than the old threshold.
  INCIDENTAL discovery: the higher threshold also closed finding
  007's camouflage-margin AND complete-blind-spot cases via
  divergence alone (unplanned defense-in-depth, not redundant with
  the content-pattern detector — see finding 007's update). Tests
  updated to reflect real current behavior, not left stale.

- **FAKE_DIVERGENCE_THRESHOLD not yet reviewed for finding 008's
  vulnerability** (real remaining gap). Only MINILM_DIVERGENCE_THRESHOLD
  was recalibrated. The fake-embedder threshold (0.15) is still
  min-margin-style (a fixed placeholder, not literally derived via
  min() from real data, but never checked against percentile-style
  poisoning resistance either). Lower priority since FakeSemanticEmbedder
  is a fallback/dev-only path, not the primary production embedder,
  but should be reviewed for completeness.
