"""
Verifies the Phase 1 interception layer (§03/§12 slice), now with all
THREE detectors wired in: schema conformance, param-vs-task divergence,
and permission escalation (session-level, includes the current call in
the evaluated footprint). Every call is logged to the session store
regardless of outcome. End-to-end against normal corpus and all three
attack corpora.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_injection_session,
    generate_param_tampering_missing_session,
    generate_param_tampering_unexpected_session,
    generate_permission_escalation_session,
)
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import build_default_schema_registry
from simulacrum.interception import (
    InMemorySessionStore,
    build_default_registry,
    intercept_and_call,
)
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session


@pytest.fixture
def registries():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    session_store = InMemorySessionStore()
    return tool_registry, schema_registry, session_store


@pytest.fixture
def embedder():
    return FakeSemanticEmbedder()


def _task_for(task_type: TaskType, embedder) -> TaskRepresentation:
    return TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
    )


def test_clean_call_is_allowed_and_actually_executes(registries, embedder):
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="read_inbox",
        params={"count": "5"},
        turn_index=0,
    )
    assert result.allowed is True
    assert result.schema_violation.is_violation is False
    assert result.divergence_result.is_divergent is False
    assert result.escalation_result.is_escalated is False
    assert result.tool_result is not None


def test_missing_params_call_is_blocked_before_execution(registries, embedder):
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={},
        turn_index=0,
    )
    assert result.allowed is False
    assert result.schema_violation.is_violation is True
    assert result.tool_result is None


def test_unexpected_param_call_is_blocked(registries, embedder):
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
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
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
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
    assert result.tool_result is None


def test_out_of_baseline_call_blocked_by_escalation_even_if_not_divergent(registries):
    """
    Isolates the escalation path specifically: use FakeTaskEmbedder
    (near-zero similarity for ANY distinct text — see finding 001 fix)
    so divergence would ALSO likely fire, so instead we verify via the
    escalation_result field directly that escalation independently
    flagged it, regardless of what divergence also found.
    """
    from simulacrum.attribution import FakeSemanticEmbedder

    tool_registry, schema_registry, session_store = registries
    embedder = FakeSemanticEmbedder()
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        task_representation=task,
        task_type=TaskType.INBOX_TRIAGE,
        session_id="s1",
        tool_name="modify_permissions",
        params={"user": "admin", "level": "root"},
        turn_index=0,
    )
    assert result.escalation_result.is_escalated is True
    assert "modify_permissions" in result.escalation_result.escalated_tools
    assert result.allowed is False


def test_blocked_call_is_still_logged_to_session_store(registries, embedder):
    """
    Critical behavior: a BLOCKED call must still appear in session
    history — it happened, even though the underlying tool never ran.
    """
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={},  # will be blocked (missing flight_id)
        turn_index=0,
    )
    calls = session_store.get_calls(session_id="s1")
    assert len(calls) == 1
    assert calls[0].tool_name == "book_flight"


def test_blocked_call_does_not_mutate_underlying_tool_state(registries, embedder):
    tool_registry, schema_registry, session_store = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        session_store=session_store,
        task_representation=task,
        task_type=TaskType.FLIGHT_BOOKING,
        session_id="s1",
        tool_name="book_flight",
        params={"wrong_field": "x"},
        turn_index=0,
    )
    assert result.tool_result is None


def test_full_normal_session_end_to_end_all_allowed():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for seed in range(20):
            session_store = InMemorySessionStore()  # fresh store per session
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = intercept_and_call(
                    tool_registry=tool_registry,
                    schema_registry=schema_registry,
                    session_store=session_store,
                    task_representation=task,
                    task_type=task_type,
                    session_id=session.session_id,
                    tool_name=call.tool_name,
                    params=call.params,
                    turn_index=call.turn_index,
                )
                assert result.allowed is True, f"False positive: {task_type}, seed {seed}, {call}"


def test_full_param_tampering_session_end_to_end_attack_call_blocked():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

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
                        schema_registry=schema_registry,
                        session_store=session_store,
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
                        assert result.allowed is True, (
                            f"False positive: {generator.__name__}, {task_type}, seed {seed}, call {i}"
                        )


def test_full_injection_session_end_to_end_attack_call_blocked():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

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
                        schema_registry=schema_registry,
                        session_store=session_store,
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
                        assert result.allowed is True, (
                            f"False positive: {task_type}, {tool_name}, seed {seed}, call {i}"
                        )


def test_full_permission_escalation_session_end_to_end_attack_call_blocked():
    """
    Closes the same gap as before, now for the THIRD detector:
    permission-escalation attacks proven blocked through the real
    interceptor end to end, not just at the detector-function level.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

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
                        schema_registry=schema_registry,
                        session_store=session_store,
                        task_representation=task,
                        task_type=task_type,
                        session_id=attack.session.session_id,
                        tool_name=call.tool_name,
                        params=call.params,
                        turn_index=call.turn_index,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False, (
                            f"Missed escalation: {task_type}, {tool_name}, seed {seed}"
                        )
                    else:
                        assert result.allowed is True, (
                            f"False positive: {task_type}, {tool_name}, seed {seed}, call {i}"
                        )
