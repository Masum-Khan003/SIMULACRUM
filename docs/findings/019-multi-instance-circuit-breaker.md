# Finding 019: multi-instance circuit-breaker state (Phase 3, §12 v2 gap 7) — real, Redis-backed, verified across replicas

**Status:** Resolved. Phase 3 item 1 of 3 (per the approved production plan: multi-instance breaker → approver role → investigation report).

## Background

§12's original scope explicitly named the limitation directly rather than silently inheriting it: MVP circuit-breaker state is in-memory, correct only for single-instance deployment. A real multi-replica production deployment needs circuit-breaker state shared via Redis so all replicas observe the same open/closed state — named as Phase 3, §23.

## Real design

Built `RedisCircuitBreaker` (`src/simulacrum/interception/redis_circuit_breaker.py`) as a genuine, structural drop-in for the existing in-memory `CircuitBreaker` — same real pattern as `SessionStore`'s protocol/`InMemorySessionStore`/`RedisSessionStore` split (not a new pattern invented for this).

- `CircuitBreakerProtocol`: structural interface both breakers satisfy (`state`, `call()`)
- `intercept_and_call()`'s type hint changed from the concrete `CircuitBreaker` class to the protocol — non-breaking, verified by the full suite passing unchanged before any new code was added
- Real, atomic Redis operations: `INCR` for failure count (atomic at the server level, so concurrent replica failures never race-lose an increment), real wall-clock `opened_at` timestamp stored in Redis (not `time.monotonic()`, which is only valid within one process — a real, deliberate difference from the in-memory breaker, called out explicitly in the code)
- Same "no default resource URL, ever" rule (§00b): `redis_url` and `breaker_name` are both required, keyword-only, no default

## Real, explicit wiring — opt-in, non-breaking

`AppState` (the real API's process-wide singleton) gains an explicit opt-in: `SIMULACRUM_MULTI_INSTANCE_BREAKER=1` — same pattern as the existing `SIMULACRUM_USE_REAL_EMBEDDINGS` opt-in. Reuses `settings.redis_url` (no new required config). Default, unset behavior is unchanged: the original in-memory `CircuitBreaker`, correct for the still-common single-instance deployment case.

## Real verification

**Multi-instance property, proven directly** (not asserted from design alone): two independent `RedisCircuitBreaker` instances sharing the same `redis_url` + `breaker_name`, simulating two real replicas —

1. Replica A fails twice (crosses `failure_threshold=2`), trips OPEN.
2. Replica B — which never called the failing function itself — observes OPEN state and correctly short-circuits.
3. After `recovery_timeout_seconds` elapses, both replicas independently observe CLOSED (half-open trial state) without any explicit coordination beyond shared Redis keys.
4. A real successful call on one replica clears failure state, observed by the other replica immediately.

4 real, permanent tests in `tests/unit/test_redis_circuit_breaker.py`, all passing, all requiring real Redis (same dependency class as `test_redis_session_store.py`).

**Real end-to-end verification via `AppState` itself** (not just the unit-level class): confirmed the opt-in flag produces `RedisCircuitBreaker` and the default produces the original `CircuitBreaker`, both booting correctly against the real running Redis instance.

## Real, unrelated finding caught during this work

While running the full suite after wiring this in, `test_retry_after_correction_majority_vote` (finding 009's own documented borderline case, real ~30% measured LLM non-determinism rate) failed once (7/10 vs. its statistical margin of ≤6/10), then passed cleanly on immediate re-run. Confirmed unrelated to this work — real, expected variance the test was specifically designed to sometimes catch, per finding 009's own writeup. No action taken; this is the system working as documented, not a regression.

## Real result

Full suite: 322/322 passing (up from 318), 4 new tests, zero regressions, non-breaking type-hint change verified before any new code was written.

## Reproducing this result

```bash
set -a && source .env && set +a
python3 -m pytest tests/unit/test_redis_circuit_breaker.py -v

export SIMULACRUM_REDIS_URL="redis://localhost:6379/0"
export SIMULACRUM_MULTI_INSTANCE_BREAKER=1
python3 -c "
from simulacrum.api.state import AppState
state = AppState()
print(type(state.circuit_breaker).__name__)
"
```
