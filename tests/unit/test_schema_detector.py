"""
Verifies schema conformance detector (§09/§14): missing/unexpected
param detection, and — critically — zero false positives against
task_sim's own normal-session generator. A detector that flags its
own normal corpus is broken before it ever sees an attack.
"""
import random

import pytest

from simulacrum.detectors import (
    SchemaRegistry,
    ToolSchema,
    UnregisteredSchemaError,
    build_default_schema_registry,
    check_schema,
)
from simulacrum.task_sim import TaskType, generate_session


@pytest.fixture
def registry():
    return build_default_schema_registry()


def test_unregistered_tool_raises(registry):
    with pytest.raises(UnregisteredSchemaError):
        check_schema(registry=registry, tool_name="nonexistent_tool", params={})


def test_valid_call_no_violation(registry):
    result = check_schema(
        registry=registry, tool_name="read_inbox", params={"count": "5"}
    )
    assert result.is_violation is False


def test_missing_required_param_detected(registry):
    result = check_schema(
        registry=registry, tool_name="reply_to_email", params={"email_id": "1"}
    )
    assert result.is_violation is True
    assert result.missing_params == frozenset({"body"})
    assert result.unexpected_params == frozenset()


def test_unexpected_param_detected(registry):
    result = check_schema(
        registry=registry,
        tool_name="read_inbox",
        params={"count": "5", "unexpected_field": "x"},
    )
    assert result.is_violation is True
    assert result.unexpected_params == frozenset({"unexpected_field"})


def test_both_missing_and_unexpected_detected(registry):
    result = check_schema(
        registry=registry,
        tool_name="book_flight",
        params={"totally_wrong_field": "x"},
    )
    assert result.is_violation is True
    assert result.missing_params == frozenset({"flight_id"})
    assert result.unexpected_params == frozenset({"totally_wrong_field"})


def test_optional_params_do_not_trigger_violation():
    registry = SchemaRegistry()
    registry.register(
        schema=ToolSchema(
            tool_name="test_tool",
            required_params=frozenset({"req"}),
            optional_params=frozenset({"opt"}),
        )
    )
    result = check_schema(
        registry=registry, tool_name="test_tool", params={"req": "x", "opt": "y"}
    )
    assert result.is_violation is False


def test_task_sim_normal_sessions_never_violate_schema(registry):
    """
    Integration check: every call task_sim's generate_session() can
    produce, across many seeds, must pass schema conformance cleanly.
    A single false positive here means the detector and the corpus
    generator have silently diverged on what 'normal' params look like.
    """
    violations = []
    for task_type in TaskType:
        for seed in range(50):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            for call in session.calls:
                result = check_schema(
                    registry=registry, tool_name=call.tool_name, params=call.params
                )
                if result.is_violation:
                    violations.append((task_type, seed, call))
    assert violations == [], f"False positives on normal corpus: {violations}"
