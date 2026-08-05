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
