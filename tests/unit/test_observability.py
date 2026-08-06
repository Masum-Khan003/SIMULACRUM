"""
Verifies metrics are ACTUALLY recorded with correct values (§18's own
stated discipline — a Palimpsest empty-panel bug was caught only by
verifying real metric values against real usage, not by assuming a
Counter.inc() call means the dashboard will show the right number).

Reads real values from the Prometheus REGISTRY, not just checking
that record_*() functions don't raise.
"""
import random

import pytest

from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import build_default_schema_registry
from simulacrum.detectors import HeuristicContentPatternDetector
from simulacrum.interception import build_default_registry, intercept_and_call
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.observability import (
    ACTIONS_TOTAL,
    APPROVAL_OUTCOMES_TOTAL,
    APPROVAL_QUEUE_DEPTH,
    DETECTOR_FLAGS_TOTAL,
)
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType
from simulacrum.tier_engine import ApprovalQueue


def _get_counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def _get_gauge_value(gauge) -> float:
    return gauge._value.get()


@pytest.fixture
def full_stack():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    approval_queue = ApprovalQueue()
    embedder = FakeSemanticEmbedder()
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.INBOX_TRIAGE]
    )
    return tier_registry, tool_registry, schema_registry, session_store, breaker, approval_queue, task


def test_allow_action_increments_actions_total(full_stack):
    tier_registry, tool_registry, schema_registry, session_store, breaker, approval_queue, task = full_stack
    before = _get_counter_value(ACTIONS_TOTAL, response_tier="allow")

    intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, session_store=session_store,
        circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=HeuristicContentPatternDetector(),
        task_representation=task, task_type=TaskType.INBOX_TRIAGE,
        session_id="metrics-test-1", tool_name="read_inbox", params={"count": "5"}, turn_index=0,
    )

    after = _get_counter_value(ACTIONS_TOTAL, response_tier="allow")
    assert after == before + 1


def test_blocked_call_increments_correct_detector_flag(full_stack):
    tier_registry, tool_registry, schema_registry, session_store, breaker, approval_queue, task = full_stack
    before = _get_counter_value(DETECTOR_FLAGS_TOTAL, detector_name="schema")

    intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, session_store=session_store,
        circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=HeuristicContentPatternDetector(),
        task_representation=task, task_type=TaskType.FLIGHT_BOOKING,
        session_id="metrics-test-2", tool_name="book_flight", params={}, turn_index=0,
    )

    after = _get_counter_value(DETECTOR_FLAGS_TOTAL, detector_name="schema")
    assert after == before + 1


def test_require_approval_action_recorded(full_stack):
    tier_registry, tool_registry, schema_registry, session_store, breaker, approval_queue, task = full_stack
    before = _get_counter_value(ACTIONS_TOTAL, response_tier="require_approval")

    intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, session_store=session_store,
        circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=HeuristicContentPatternDetector(),
        task_representation=task, task_type=TaskType.FLIGHT_BOOKING,
        session_id="metrics-test-3", tool_name="book_flight", params={}, turn_index=0,
    )

    after = _get_counter_value(ACTIONS_TOTAL, response_tier="require_approval")
    assert after == before + 1


def test_approval_queue_depth_reflects_real_pending_count():
    """
    APPROVAL_QUEUE_DEPTH is a process-global, unlabeled Gauge (finding
    004) — its ABSOLUTE value depends on every ApprovalQueue instance
    across the whole test process, not just this test's own queue.
    Explicitly reset it to a known 0 baseline here rather than trusting
    whatever value earlier tests left behind.
    """
    APPROVAL_QUEUE_DEPTH.set(0)
    queue = ApprovalQueue()

    r1 = queue.submit(session_id="s1", tool_name="send_payment", params={})
    assert _get_gauge_value(APPROVAL_QUEUE_DEPTH) == 1

    r2 = queue.submit(session_id="s1", tool_name="delete_data", params={})
    assert _get_gauge_value(APPROVAL_QUEUE_DEPTH) == 2

    queue.decide(request_id=r1.request_id, approved=True)
    assert _get_gauge_value(APPROVAL_QUEUE_DEPTH) == 1  # one resolved, one still pending


def test_approval_outcome_recorded_distinctly_for_expired_vs_denied():
    """
    Confirms §13 v2's core requirement at the METRICS level too: an
    expired request and a denied request increment DIFFERENT label
    values, never conflated into one counter.
    """
    import time

    class FakeClock:
        def __init__(self):
            self.now = 0.0
        def __call__(self):
            return self.now
        def advance(self, s):
            self.now += s

    clock = FakeClock()
    queue = ApprovalQueue(timeout_seconds=10, clock=clock)

    before_denied = _get_counter_value(APPROVAL_OUTCOMES_TOTAL, outcome="denied")
    before_expired = _get_counter_value(APPROVAL_OUTCOMES_TOTAL, outcome="expired")

    r1 = queue.submit(session_id="s1", tool_name="send_payment", params={})
    queue.decide(request_id=r1.request_id, approved=False)

    r2 = queue.submit(session_id="s1", tool_name="send_payment", params={})
    clock.advance(20)
    queue.get(request_id=r2.request_id)  # triggers expiry

    after_denied = _get_counter_value(APPROVAL_OUTCOMES_TOTAL, outcome="denied")
    after_expired = _get_counter_value(APPROVAL_OUTCOMES_TOTAL, outcome="expired")

    assert after_denied == before_denied + 1
    assert after_expired == before_expired + 1
