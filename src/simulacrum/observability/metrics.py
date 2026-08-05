"""
Prometheus metrics (§18): action volume by tier, per-detector flag
counts, circuit-breaker state, approval-queue depth. Registered on
the default CollectorRegistry so a simple /metrics endpoint (added
when the API layer exists) can expose them via
prometheus_client.generate_latest().

Metric names verified against real usage in tests before being
considered done — same discipline §18 itself calls out as the exact
thing that caught a real empty-panel bug in Palimpsest's own
observability work.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge

# Action volume by response tier (allow/flag/require_approval/block)
ACTIONS_TOTAL = Counter(
    "simulacrum_actions_total",
    "Total intercepted tool calls by response tier",
    ["response_tier"],
)

# Per-detector flag counts — which detector fired, independent of
# final response tier (a call can have multiple detectors flag it)
DETECTOR_FLAGS_TOTAL = Counter(
    "simulacrum_detector_flags_total",
    "Total times each detector flagged a call",
    ["detector_name"],
)

# Circuit breaker state, per breaker instance label (only one breaker
# exists today — "detector_scoring" — but labeled for future per-
# detector breakers per docs/BACKLOG.md)
CIRCUIT_BREAKER_STATE = Gauge(
    "simulacrum_circuit_breaker_state",
    "Circuit breaker state: 0=closed, 1=open",
    ["breaker_name"],
)

CIRCUIT_BREAKER_TRIPS_TOTAL = Counter(
    "simulacrum_circuit_breaker_trips_total",
    "Total times a circuit breaker has tripped open",
    ["breaker_name"],
)

# Approval queue
APPROVAL_QUEUE_DEPTH = Gauge(
    "simulacrum_approval_queue_pending",
    "Current count of PENDING approval requests",
)

APPROVAL_OUTCOMES_TOTAL = Counter(
    "simulacrum_approval_outcomes_total",
    "Total approval requests resolved, by outcome",
    ["outcome"],
)


def record_action(*, response_tier: str) -> None:
    ACTIONS_TOTAL.labels(response_tier=response_tier).inc()


def record_detector_flag(*, detector_name: str) -> None:
    DETECTOR_FLAGS_TOTAL.labels(detector_name=detector_name).inc()


def record_circuit_breaker_state(*, breaker_name: str, is_open: bool) -> None:
    CIRCUIT_BREAKER_STATE.labels(breaker_name=breaker_name).set(1 if is_open else 0)


def record_circuit_breaker_trip(*, breaker_name: str) -> None:
    CIRCUIT_BREAKER_TRIPS_TOTAL.labels(breaker_name=breaker_name).inc()


def record_approval_outcome(*, outcome: str) -> None:
    APPROVAL_OUTCOMES_TOTAL.labels(outcome=outcome).inc()


def set_approval_queue_depth(*, depth: int) -> None:
    APPROVAL_QUEUE_DEPTH.set(depth)
