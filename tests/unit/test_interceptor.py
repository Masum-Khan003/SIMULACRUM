"""
Verifies the Phase 1 interception layer (§03/§12), now with all 5
detectors run as ONE unit inside a circuit breaker, and §07's
per-tier fail-open/fail-closed fallback proven when the breaker is
open. End-to-end against normal corpus and all attack corpora, plus
dedicated guardrail-unavailable scenarios.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_exfiltration_frequency_session,
    generate_injection_session,
    generate_param_tampering_missing_session,
    generate_param_tampering_unexpected_session,
    generate_permission_escalation_session,
)
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import build_default_schema_registry
from simulacrum.interception import build_default_registry, intercept_and_call
from simulacrum.interception.circuit_breaker import CircuitBreaker
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session


@pytest.fixture
def registries():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    return tier_registry, tool_registry, schema_registry, session_store, breaker


@pytest.fixture
def embedder():
    return FakeSemanticEmbedder()


def _task_for(task_type: TaskType, embedder) -> TaskRepresentation:
    return TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
    )


def test_clean_call_is_allowed_and_actually_executes(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="read_inbox",
        params={"count": "5"},
        turn_index=0,
    )
    assert result.allowed is True
    assert result.guardrail_bypassed is False
    assert result.tool_result is not None


def test_missing_params_call_is_blocked_before_execution(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={},
        turn_index=0,
    )
    assert result.allowed is False
    assert result.schema_violation.is_violation is True


def test_unexpected_param_call_is_blocked(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="read_inbox",
        params={"count": "5", "debug_override": "true"},
        turn_index=0,
    )
    assert result.allowed is False
    assert result.schema_violation.unexpected_params == frozenset({"debug_override"})


def test_off_task_but_schema_valid_call_is_blocked_by_divergence(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="delete_data",
        params={"target": "all_files"},
        turn_index=0,
    )
    assert result.allowed is False
    assert result.schema_violation is None
    assert result.divergence_result.is_divergent is True


def test_out_of_baseline_call_blocked_by_escalation(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="modify_permissions",
        params={"user": "admin", "level": "root"},
        turn_index=0,
    )
    assert result.escalation_result.is_escalated is True
    assert result.allowed is False


def test_blocked_call_is_still_logged_to_session_store(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={},
        turn_index=0,
    )
    calls = session_store.get_calls(session_id="s1")
    assert len(calls) == 1


def test_blocked_call_does_not_mutate_underlying_tool_state(registries, embedder):
    tier_registry, tool_registry, schema_registry, session_store, breaker = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={"wrong_field": "x"},
        turn_index=0,
    )
    assert result.tool_result is None


# --- Circuit breaker: guardrail-unavailable fallback (§07/§12) ---

def test_open_circuit_fails_open_for_read_only_tool(embedder):
    """§07: READ_ONLY -> fail OPEN when guardrail unavailable."""
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker(failure_threshold=1)
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)

    # Force the breaker open by breaking schema_registry so scoring raises.
    broken_schema_registry = None  # will cause AttributeError inside scoring
    with pytest.raises(Exception):
        intercept_and_call(
            tool_registry=tool_registry,
            tier_registry=tier_registry,
            schema_registry=broken_schema_registry,
            session_store=session_store,
            circuit_breaker=breaker,
            task_representation=task,
            task_type=TaskType.INBOX_TRIAGE,
            session_id="s1",
            tool_name="read_inbox",
            params={"count": "5"},
            turn_index=0,
        )
    # breaker should now be open (threshold=1)
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,  # real one now, but breaker is open, won't be called
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="read_inbox",  # READ_ONLY tier
        params={"count": "5"},
        turn_index=1,
    )
    assert result.guardrail_bypassed is True
    assert result.guardrail_bypass_reason == "circuit_open_fail_open"
    assert result.allowed is True
    assert result.tool_result is not None  # proceeded unscored


def test_open_circuit_fails_closed_for_irreversible_tool(embedder):
    """§07: IRREVERSIBLE_LOW_VALUE/HIGH_VALUE -> fail CLOSED when guardrail unavailable."""
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker(failure_threshold=1)
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)

    broken_schema_registry = None
    with pytest.raises(Exception):
        intercept_and_call(
            tool_registry=tool_registry,
            tier_registry=tier_registry,
            schema_registry=broken_schema_registry,
            session_store=session_store,
            circuit_breaker=breaker,
            task_representation=task,
            task_type=TaskType.FLIGHT_BOOKING,
            session_id="s1",
            tool_name="book_flight",
            params={"flight_id": "FL1"},
            turn_index=0,
        )
    result = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",  # IRREVERSIBLE_LOW_VALUE tier
        params={"flight_id": "FL1"},
        turn_index=1,
    )
    assert result.guardrail_bypassed is True
    assert result.guardrail_bypass_reason == "circuit_open_fail_closed"
    assert result.allowed is False
    assert result.tool_result is None  # blocked, never executed


# --- Full end-to-end normal + attack corpora, all through real breaker ---

def test_full_normal_session_end_to_end_all_allowed():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()
    breaker = CircuitBreaker()

    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for seed in range(20):
            session_store = InMemorySessionStore()
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = intercept_and_call(
                    tool_registry=tool_registry,
                    tier_registry=tier_registry,
                    schema_registry=schema_registry,
                    session_store=session_store,
                    circuit_breaker=breaker,
                    task_representation=task,
                    task_type=task_type,
                    session_id=session.session_id,
                    tool_name=call.tool_name,
                    params=call.params,
                    turn_index=call.turn_index,
                )
                assert result.allowed is True, f"False positive: {task_type}, seed {seed}, {call}"
                assert result.guardrail_bypassed is False


def test_full_param_tampering_session_end_to_end_attack_call_blocked():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()
    breaker = CircuitBreaker()

    generators = [
        generate_param_tampering_missing_session,
        generate_param_tampering_unexpected_session,
    ]
    for generator in generators:
        for task_type in TaskType:
            task = _task_for(task_type, embedder)
            for seed in range(20):
                session_store = InMemorySessionStore()
                attack = generator(task_type=task_type, rng=random.Random(seed))
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        tier_registry=tier_registry,
                        schema_registry=schema_registry,
                        session_store=session_store,
                        circuit_breaker=breaker,
                        task_representation=task,
                        task_type=task_type,
                        session_id=attack.session.session_id,
                        tool_name=call.tool_name,
                        params=call.params,
                        turn_index=call.turn_index,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False
                    else:
                        assert result.allowed is True


def test_full_injection_session_end_to_end_attack_call_blocked():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()
    breaker = CircuitBreaker()

    attack_tools = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]
    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for tool_name in attack_tools:
            for seed in range(20):
                session_store = InMemorySessionStore()
                attack = generate_injection_session(
                    task_type=task_type, injected_tool_name=tool_name, rng=random.Random(seed)
                )
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        tier_registry=tier_registry,
                        schema_registry=schema_registry,
                        session_store=session_store,
                        circuit_breaker=breaker,
                        task_representation=task,
                        task_type=task_type,
                        session_id=attack.session.session_id,
                        tool_name=call.tool_name,
                        params=call.params,
                        turn_index=call.turn_index,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False
                    else:
                        assert result.allowed is True


def test_full_permission_escalation_session_end_to_end_attack_call_blocked():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()
    breaker = CircuitBreaker()

    escalation_tools = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]
    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for tool_name in escalation_tools:
            for seed in range(20):
                session_store = InMemorySessionStore()
                attack = generate_permission_escalation_session(
                    task_type=task_type, escalated_tool_name=tool_name, rng=random.Random(seed)
                )
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        tier_registry=tier_registry,
                        schema_registry=schema_registry,
                        session_store=session_store,
                        circuit_breaker=breaker,
                        task_representation=task,
                        task_type=task_type,
                        session_id=attack.session.session_id,
                        tool_name=call.tool_name,
                        params=call.params,
                        turn_index=call.turn_index,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False
                    else:
                        assert result.allowed is True


def test_evasion_retry_blocked_by_loop_rate_through_real_interceptor():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    embedder = FakeSemanticEmbedder()
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)

    first = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="evasion-test",
        tool_name="send_payment",
        params={"amount": "5000"},
        turn_index=0,
    )
    assert first.allowed is False

    retry = intercept_and_call(
        tool_registry=tool_registry,
        tier_registry=tier_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        circuit_breaker=breaker,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="evasion-test",
        tool_name="send_payment",
        params={"amount": "4999"},
        turn_index=1,
    )
    assert retry.loop_rate_result.is_evasion_retry is True
    assert retry.allowed is False


def test_exfiltration_attack_blocked_through_real_interceptor():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    breaker = CircuitBreaker()
    embedder = FakeSemanticEmbedder()
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)

    attack = generate_exfiltration_frequency_session(
        task_type=TaskType.INBOX_TRIAGE, rng=random.Random(1)
    )
    last_result = None
    for call in attack.session.calls:
        last_result = intercept_and_call(
            tool_registry=tool_registry,
            tier_registry=tier_registry,
            schema_registry=schema_registry,
            session_store=session_store,
            circuit_breaker=breaker,
            task_representation=task,
            task_type=TaskType.INBOX_TRIAGE,
            session_id=attack.session.session_id,
            tool_name=call.tool_name,
            params=call.params,
            turn_index=call.turn_index,
        )
    assert last_result.allowed is False
    assert last_result.exfiltration_result.is_frequency_exceeded is True
