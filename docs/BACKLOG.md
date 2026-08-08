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

- ~~§10 trajectory sequence model decision~~ — RESOLVED. Formal
  decision record written (docs/decisions/001-llm-reasoning-vs-trajectory-sequence-model.md):
  LLM-based reasoning (GroqDriftDetector) is accepted as the current
  substitute for §10's literal spec, with explicit rationale (no real
  training data exists, extensively tested, genuinely interpretable,
  premature to build training infra now) AND explicit, real revisit
  conditions (production data volume, cost/latency at scale, or a
  regulatory determinism requirement) -- not a silent, permanent
  substitution.

## Open — Real, Lower Priority

- ~~Only 3 of §08's target 5-8 task types~~ — RESOLVED. Added
  file_sharing (list_files/share_file) and contact_update
  (search_contacts/update_contact), now 5 task types total, meeting
  §08's minimum target. Registered consistently across all 5 files
  that need it (task_sim, schema, fake_tools, call_text, task_text) --
  same discipline as the calendar_scheduling addition earlier this
  session. Real calibration work required (not just plumbing): the
  first-attempt call-topic template for list_files scored 0.2701 under
  real MiniLM, below the 0.303 threshold -- fixed via real wording-
  variant comparison (tested 5 phrasings, picked the one with genuine
  margin: 0.4123). Two stale hardcoded test totals (from the earlier
  3-task-type era) caught and fixed with computed formulas, same
  pattern as before.

- ~~Formal confidence calibration reporting (§05/§15)~~ — RESOLVED.
  Real Brier score + reliability diagram (docs/CALIBRATION_REPORT.md),
  computed against real ground-truth-verified AgentDojo data (n=980).
  Real, honest, sobering result: Brier score 0.2333, barely better
  than the 0.25 coin-flip baseline -- formally confirms, via a
  standard metric, what finding 010's investigation already found
  empirically. Two additional real findings: the detector never
  confidently predicts "attack" (zero samples above 0.6 predicted
  probability across the entire real dataset -- a structural property
  of min-aggregation, not a tuning issue), and a small-sample (n=3)
  inverted-confidence anomaly in the lowest bin, reported honestly
  rather than hidden. Explicitly scoped as single-detector, not
  system-level (5 other independent detectors exist and structurally
  catch cases divergence misses). ~~System-level calibration report~~
  — ATTEMPTED with a real, honest result: combining divergence +
  content-pattern (the only 2 detectors that are genuinely tool-
  vocabulary-agnostic and can evaluate AgentDojo's different tools at
  all) gave Brier score 0.4146 -- WORSE than divergence alone (0.2333).
  Real diagnosis: the two detectors' errors correlate (both agree even
  when wrong), and naive binary-flag combination discards each
  detector's own continuous confidence signal. A real, valuable,
  NOT-yet-attempted follow-up: preserve continuous confidence across
  detectors and/or model inter-detector correlation explicitly, rather
  than combining discrete flags.

- ~~CI import-order check (finding 003) never built~~ — RESOLVED.
  tests/check_import_order.py imports every subpackage in multiple
  real orderings (forward/reverse alphabetical), each in a fresh
  subprocess. Confirmed clean on the real current codebase.

- ~~CI needs a Redis service container~~ — RESOLVED. Real
  .github/workflows/ci.yml built: Redis service container, import-
  order check, full test suite, and a genuine fresh-venv
  reproducibility check as dedicated CI steps. Structural tests
  (test_ci_workflow.py) verify the workflow file itself against real
  project requirements. One real leftover-env-var contamination bug
  caught and fixed during verification (SIMULACRUM_USE_REAL_EMBEDDINGS
  left exported from earlier session work, unrelated to the actual
  code) -- confirms genuine CI (clean environment every run) avoids
  this class of local-shell-state issue entirely.

- **Per-detector circuit breakers** (deferred scope decision, stated
  directly in circuit_breaker.py's docstring). Current breaker wraps
  all 6 detectors as ONE unit — a broken embedding model trips the
  same breaker as a broken schema registry.

- **APPROVAL_QUEUE_DEPTH is a single unlabeled global Prometheus
  gauge** (finding 004's resolved scope). Correct for the current
  single-conceptual-queue architecture; would need per-queue labeling
  if a future ops/security-approver role introduces genuinely separate
  concurrent queues.

- ~~Feature-schema hash/versioning (§11, Palimpsest bug #2 guard)~~
  — RESOLVED. Real calibration manifest (evaluation/calibration_manifest.py)
  built from THIS project's actual documented findings (005/008/010),
  not placeholder data -- records threshold values, calibration
  method, sample size, and real measured recall/FP per detector.
  verify_current_config() checks the manifest against the ACTUAL
  live-imported threshold constants, catching drift between
  documented calibration and running configuration (exactly Palimpsest
  bug #2's failure mode). Proven both directions: zero drift against
  our real current config, AND correctly detects a simulated mismatch.
  Runs automatically in CI via the existing pytest step -- real,
  live enforcement, not a standalone script nobody runs.

- ~~HF_TOKEN not configured~~ — RESOLVED. Added to Settings
  (same optional-config pattern as GROQ_API_KEY), threaded through
  MiniLMEmbedder's constructor to SentenceTransformer's own token
  parameter for higher Hugging Face Hub rate limits when set.

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

- ~~Preserve continuous confidence across detectors (calibration
  follow-up)~~ — ATTEMPTED. Added a genuine, ADDITIVE confidence field
  to GroqContentPatternDetector (existing is_suspicious logic
  completely untouched, proven via a real regression test using the
  same adaptive-evasion ladder). Real result: continuous-confidence
  averaged combination gave Brier score 0.2673 -- substantial
  improvement over the binary-flag combination (0.4146, confirming
  discretization was a real factor), but STILL slightly worse than
  divergence alone (0.2333). Honest conclusion: simple averaging is
  also not the right combination rule. Genuinely open follow-up (not
  attempted, stated honestly): a smarter, non-naive combination rule
  (weighted by confidence, or using content-pattern specifically to
  break ties near divergence's own threshold) might do better than
  either single-detector or naive combination.

- ~~§19 sensitive-parameter redaction — never built~~ — RESOLVED.
  Found via a real audit re-reading the original blueprint against
  what's actually built (explicitly called "a day-one requirement" in
  §19, extending Palimpsest's own §17 IP-hashing discipline). Real,
  current exposure identified and closed: LLM-generated reasoning
  (GroqExplainer, GroqDriftDetector) naturally quotes back real param
  content it analyzes (emails, SSNs, credentials) -- this flowed
  completely unredacted into HTTP API responses. Built
  redaction/redactor.py (reuses content_pattern.py's real, tested
  structured-data patterns, kept as a deliberate separate copy since
  detection and redaction have different failure costs), wired into
  both API reasoning/explanation fields, proven end-to-end with real
  sensitive content sent through the actual HTTP API and confirmed
  absent from the response (permanent regression test in test_api.py).

- **Cross-agent/multi-agent injection propagation — correctly NOT
  built, now explicitly documented rather than silently absent.**
  Found via the same blueprint re-audit: explicitly scoped in the
  original document as "a Phase 2 stretch goal... not MVP," requiring
  genuine multi-agent orchestration infrastructure this project has
  never built (consistent with Phase 3's "second agent-framework
  integration," which is also untouched by design). This is a real,
  legitimate gap for a genuinely comprehensive system, correctly
  deferred pending a real architectural decision about multi-agent
  support, not something to build without first choosing that
  direction deliberately.

- ~~§19 content-handling — session data persisted indefinitely with
  no expiry~~ — RESOLVED. Found via the same blueprint re-audit
  (same "used transiently... then discarded" requirement redaction
  addressed). Verified via direct code inspection: RedisSessionStore
  had zero TTL mechanism -- rpush with no expire call at all. Added a
  real, configurable TTL (default 24h), refreshed on every write so
  actively-used sessions never expire mid-session. Proven directly
  against real Redis: TTL genuinely set (not None/-1) and genuinely
  refreshes on subsequent writes (not decaying toward zero). Real,
  honest scope note: applies ONE uniform TTL regardless of flagged
  status -- the blueprint's finer-grained "longer retention for
  audit-relevant flagged sessions" policy is NOT implemented,
  tracked as real follow-up.
