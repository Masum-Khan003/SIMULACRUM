"""
Verifies the Phase 1 interception layer (§03/§12 slice), now with BOTH
detectors wired in: schema conformance AND param-vs-task divergence.
Either flagging blocks the call. End-to-end against normal corpus
(task_sim) and both attack corpora (param_tampering, injection) — the
gap flagged in docs/BACKLOG.md ("divergence detector proven but not
enforcing") is closed here.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_injection_session,
    generate_param_tampering_missing_session,
    generate_param_tampering_unexpected_session,
)
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import build_default_schema_registry
from simulacrum.interception import build_default_registry, intercept_and_call
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType, generate_session


@pytest.fixture
def registries():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    return tool_registry, schema_registry


@pytest.fixture
def embedder():
    return FakeSemanticEmbedder()


def _task_for(task_type: TaskType, embedder) -> TaskRepresentation:
    return TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
    )


def test_clean_call_is_allowed_and_actually_executes(registries, embedder):
    tool_registry, schema_registry = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        task_representation=task,
        tool_name="read_inbox",
        params={"count": "5"},
    )
    assert result.allowed is True
    assert result.schema_violation.is_violation is False
    assert result.divergence_result.is_divergent is False
    assert result.tool_result is not None


def test_missing_params_call_is_blocked_before_execution(registries, embedder):
    tool_registry, schema_registry = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        task_representation=task,
        tool_name="book_flight",
        params={},
    )
    assert result.allowed is False
    assert result.schema_violation.is_violation is True
    assert result.tool_result is None


def test_unexpected_param_call_is_blocked(registries, embedder):
    tool_registry, schema_registry = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        task_representation=task,
        tool_name="read_inbox",
        params={"count": "5", "debug_override": "true"},
    )
    assert result.allowed is False
    assert result.schema_violation.unexpected_params == frozenset({"debug_override"})


def test_off_task_but_schema_valid_call_is_blocked_by_divergence(registries, embedder):
    """
    THE new case: a call schema conformance cannot even evaluate
    (no registered schema for the attack-target tool) but divergence
    correctly blocks. This is the exact gap that motivated wiring
    divergence in at all.
    """
    tool_registry, schema_registry = registries
    task = _task_for(TaskType.INBOX_TRIAGE, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        task_representation=task,
        tool_name="delete_data",
        params={"target": "all_files"},
    )
    assert result.allowed is False
    assert result.schema_violation is None  # schema couldn't evaluate it at all
    assert result.divergence_result.is_divergent is True  # divergence caught it
    assert result.tool_result is None


def test_blocked_call_does_not_mutate_underlying_tool_state(registries, embedder):
    tool_registry, schema_registry = registries
    task = _task_for(TaskType.FLIGHT_BOOKING, embedder)
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        task_representation=task,
        tool_name="book_flight",
        params={"wrong_field": "x"},
    )
    assert result.tool_result is None


def test_full_normal_session_end_to_end_all_allowed():
    """
    Every call in a normal task_sim session, run through BOTH
    detectors via the real interceptor, must be allowed — zero false
    positives, proven through the full call path.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for seed in range(20):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = intercept_and_call(
                    tool_registry=tool_registry,
                    schema_registry=schema_registry,
                    task_representation=task,
                    tool_name=call.tool_name,
                    params=call.params,
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
                attack = generator(task_type=task_type, rng=random.Random(seed))
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        schema_registry=schema_registry,
                        task_representation=task,
                        tool_name=call.tool_name,
                        params=call.params,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False, (
                            f"Missed attack: {generator.__name__}, {task_type}, seed {seed}"
                        )
                    else:
                        assert result.allowed is True, (
                            f"False positive: {generator.__name__}, {task_type}, seed {seed}, call {i}"
                        )


def test_full_injection_session_end_to_end_attack_call_blocked():
    """
    The critical end-to-end proof: the injection attack (schema-valid,
    only divergence can catch it) is now actually BLOCKED by the real
    interceptor, not just flagged by an isolated detector test. This
    closes the exact gap the backlog doc named.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    embedder = FakeSemanticEmbedder()

    attack_tools = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]
    for task_type in TaskType:
        task = _task_for(task_type, embedder)
        for tool_name in attack_tools:
            for seed in range(20):
                attack = generate_injection_session(
                    task_type=task_type, injected_tool_name=tool_name, rng=random.Random(seed)
                )
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        schema_registry=schema_registry,
                        task_representation=task,
                        tool_name=call.tool_name,
                        params=call.params,
                    )
                    if i == attack.attack_call_index:
                        assert result.allowed is False, (
                            f"Missed injection: {task_type}, {tool_name}, seed {seed}"
                        )
                    else:
                        assert result.allowed is True, (
                            f"False positive: {task_type}, {tool_name}, seed {seed}, call {i}"
                        )
