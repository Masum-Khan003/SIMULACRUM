"""
Verifies the Phase 1 interception layer (§03/§12 slice): schema
violations block the call before the underlying tool ever executes;
clean calls pass through and actually run. End-to-end check against
both the normal corpus (task_sim) and the attack corpus
(param_tampering) — the first fully-wired path in the project.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_param_tampering_missing_session,
    generate_param_tampering_unexpected_session,
)
from simulacrum.detectors import build_default_schema_registry
from simulacrum.interception import (
    build_default_registry,
    intercept_and_call,
)
from simulacrum.risk_tiers import ToolRegistry
from simulacrum.task_sim import TaskType, generate_session


@pytest.fixture
def registries():
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    return tool_registry, schema_registry


def test_clean_call_is_allowed_and_actually_executes(registries):
    tool_registry, schema_registry = registries
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        tool_name="read_inbox",
        params={"count": "5"},
    )
    assert result.allowed is True
    assert result.violation.is_violation is False
    assert result.tool_result is not None  # the underlying tool actually ran


def test_missing_params_call_is_blocked_before_execution(registries):
    tool_registry, schema_registry = registries
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        tool_name="book_flight",
        params={},
    )
    assert result.allowed is False
    assert result.violation.is_violation is True
    assert result.tool_result is None  # underlying tool never called


def test_unexpected_param_call_is_blocked(registries):
    tool_registry, schema_registry = registries
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        tool_name="read_inbox",
        params={"count": "5", "debug_override": "true"},
    )
    assert result.allowed is False
    assert result.violation.unexpected_params == frozenset({"debug_override"})


def test_blocked_call_does_not_mutate_underlying_tool_state():
    """
    Distinguishes 'blocked before execution' from 'executed then
    discarded' — book_flight's stub is stateless so we can't observe
    mutation directly, but we CAN verify tool_result is None, which is
    the only way intercept_and_call reports that the underlying
    function body never ran.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()
    result = intercept_and_call(
        tool_registry=tool_registry,
        schema_registry=schema_registry,
        tool_name="book_flight",
        params={"wrong_field": "x"},
    )
    assert result.tool_result is None


def test_full_normal_session_end_to_end_all_allowed():
    """
    Every call in a normal task_sim session, run through the real
    interceptor end to end, must be allowed — the same zero-false-
    positive guarantee as the schema detector's own test, now proven
    through the full call path, not just check_schema() directly.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()

    for task_type in TaskType:
        for seed in range(20):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = intercept_and_call(
                    tool_registry=tool_registry,
                    schema_registry=schema_registry,
                    tool_name=call.tool_name,
                    params=call.params,
                )
                assert result.allowed is True, f"False positive: {task_type}, seed {seed}, {call}"


def test_full_attack_session_end_to_end_attack_call_blocked():
    """
    Every attack session (both variants), run through the real
    interceptor end to end: the attack call must be blocked, every
    other call in the same session must be allowed. This is the
    project's first genuine end-to-end precision+recall proof, not
    just a detector-level one.
    """
    tier_registry = ToolRegistry()
    tool_registry = build_default_registry(tier_registry=tier_registry)
    schema_registry = build_default_schema_registry()

    generators = [
        generate_param_tampering_missing_session,
        generate_param_tampering_unexpected_session,
    ]
    for generator in generators:
        for task_type in TaskType:
            for seed in range(20):
                attack = generator(task_type=task_type, rng=random.Random(seed))
                for i, call in enumerate(attack.session.calls):
                    result = intercept_and_call(
                        tool_registry=tool_registry,
                        schema_registry=schema_registry,
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
