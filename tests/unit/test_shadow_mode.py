"""
Verifies shadow mode (§13, found via blueprint re-audit): new
deployments should start in shadow mode (log + flag only) until
graduation criteria are met. Real requirement: even a call that would
normally be BLOCKED or held for REQUIRE_APPROVAL must actually
EXECUTE under shadow mode -- the real decision is still computed and
recorded (for later graduation analysis), but never enforced.
"""
import random

import pytest

from simulacrum.attack_suite import generate_injection_session
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import HeuristicContentPatternDetector, build_default_schema_registry
from simulacrum.interception import build_default_registry, intercept_and_call
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType
from simulacrum.tier_engine import ApprovalQueue, ResponseTier


@pytest.fixture
def registries():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    approval_queue = ApprovalQueue()
    content_pattern_detector = HeuristicContentPatternDetector()
    return (
        tier_registry, tool_registry, schema_registry, session_store, breaker,
        approval_queue, content_pattern_detector,
    )


def test_shadow_mode_executes_even_a_call_that_would_be_blocked(registries):
    """
    THE real requirement: a real attack call (would normally BLOCK)
    still EXECUTES under shadow mode -- the real response_tier is
    still recorded for analysis, but never actually enforced.
    """
    (tier_registry, tool_registry, schema_registry, session_store, breaker,
     approval_queue, content_pattern_detector) = registries

    embedder = FakeSemanticEmbedder()
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.INBOX_TRIAGE]
    )
    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name="delete_data", rng=random.Random(1)
    )
    attack_call = attack.session.calls[attack.attack_call_index]

    result = intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, session_store=session_store,
        circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=content_pattern_detector,
        task_representation=task, task_type=TaskType.INBOX_TRIAGE,
        session_id="shadow-test-1", tool_name=attack_call.tool_name,
        params=attack_call.params, turn_index=0,
        shadow_mode=True,
    )

    # The REAL tier decision is still recorded...
    assert result.response_tier is ResponseTier.BLOCK
    # ...but the action still EXECUTED under shadow mode
    assert result.tool_result is not None
    assert result.allowed is True
    assert result.shadow_mode_active is True


def test_non_shadow_mode_still_blocks_normally(registries):
    """Regression guard: shadow_mode defaults to False, existing
    enforcement behavior is completely unchanged."""
    (tier_registry, tool_registry, schema_registry, session_store, breaker,
     approval_queue, content_pattern_detector) = registries

    embedder = FakeSemanticEmbedder()
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.INBOX_TRIAGE]
    )
    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name="delete_data", rng=random.Random(1)
    )
    attack_call = attack.session.calls[attack.attack_call_index]

    result = intercept_and_call(
        tool_registry=tool_registry, tier_registry=tier_registry,
        schema_registry=schema_registry, session_store=session_store,
        circuit_breaker=breaker, approval_queue=approval_queue,
        content_pattern_detector=content_pattern_detector,
        task_representation=task, task_type=TaskType.INBOX_TRIAGE,
        session_id="shadow-test-2", tool_name=attack_call.tool_name,
        params=attack_call.params, turn_index=0,
        # shadow_mode not passed -- defaults to False
    )
    assert result.response_tier is ResponseTier.BLOCK
    assert result.tool_result is None  # genuinely blocked, did NOT execute
    assert result.allowed is False
    assert result.shadow_mode_active is False
