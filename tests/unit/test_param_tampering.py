"""
Verifies the param-tampering attack corpus (§08 Layer 2, first of six
attack classes) and, critically, that the schema detector actually
catches both variants. Ground truth (attack_call_index, label) must
match what the detector independently flags — that agreement is the
whole point of building ground truth before serving (§05).

Two variants, isolated: "missing" exercises missing_params only,
"unexpected" exercises unexpected_params only.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_param_tampering_missing_session,
    generate_param_tampering_unexpected_session,
)
from simulacrum.detectors import build_default_schema_registry, check_schema
from simulacrum.task_sim import TaskType


@pytest.fixture
def schema_registry():
    return build_default_schema_registry()


# --- missing-params variant ---

def test_missing_generation_is_deterministic_under_seed():
    a = generate_param_tampering_missing_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    b = generate_param_tampering_missing_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    assert a.session == b.session
    assert a.attack_call_index == b.attack_call_index


def test_missing_attack_call_has_empty_params():
    attack = generate_param_tampering_missing_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(1))
    attack_call = attack.session.calls[attack.attack_call_index]
    assert attack_call.params == {}


def test_missing_ground_truth_label_recorded():
    attack = generate_param_tampering_missing_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(3))
    assert attack.ground_truth_label == "param_tampering_missing"


def test_missing_schema_detector_flags_the_attack_call(schema_registry):
    attack = generate_param_tampering_missing_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(4))
    attack_call = attack.session.calls[attack.attack_call_index]
    result = check_schema(
        registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params
    )
    assert result.is_violation is True
    assert len(result.missing_params) > 0
    assert len(result.unexpected_params) == 0


def test_missing_recall_across_many_seeds_and_task_types(schema_registry):
    total = detected = 0
    for task_type in TaskType:
        for seed in range(50):
            attack = generate_param_tampering_missing_session(task_type=task_type, rng=random.Random(seed))
            attack_call = attack.session.calls[attack.attack_call_index]
            result = check_schema(
                registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params
            )
            total += 1
            if result.is_violation:
                detected += 1
    assert total == 100
    assert detected == total, f"Recall: {detected}/{total}"


# --- unexpected-params variant ---

def test_unexpected_generation_is_deterministic_under_seed():
    a = generate_param_tampering_unexpected_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    b = generate_param_tampering_unexpected_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    assert a.session == b.session
    assert a.attack_call_index == b.attack_call_index


def test_unexpected_attack_call_retains_original_valid_params():
    """
    Critical isolation check: the attack must NOT also break
    missing_params — original required params must still all be
    present, only an extra field added.
    """
    attack = generate_param_tampering_unexpected_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(1))
    attack_call = attack.session.calls[attack.attack_call_index]
    assert "debug_override" in attack_call.params
    assert attack_call.params["debug_override"] == "true"
    # must still contain the tool's normal required params
    assert "flight_id" in attack_call.params or "origin" in attack_call.params


def test_unexpected_ground_truth_label_recorded():
    attack = generate_param_tampering_unexpected_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(3))
    assert attack.ground_truth_label == "param_tampering_unexpected"


def test_unexpected_schema_detector_flags_the_attack_call(schema_registry):
    attack = generate_param_tampering_unexpected_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(4))
    attack_call = attack.session.calls[attack.attack_call_index]
    result = check_schema(
        registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params
    )
    assert result.is_violation is True
    assert result.unexpected_params == frozenset({"debug_override"})
    assert len(result.missing_params) == 0  # isolation: missing_params untouched


def test_unexpected_recall_across_many_seeds_and_task_types(schema_registry):
    total = detected = 0
    for task_type in TaskType:
        for seed in range(50):
            attack = generate_param_tampering_unexpected_session(task_type=task_type, rng=random.Random(seed))
            attack_call = attack.session.calls[attack.attack_call_index]
            result = check_schema(
                registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params
            )
            total += 1
            if result.is_violation:
                detected += 1
    assert total == 100
    assert detected == total, f"Recall: {detected}/{total}"


# --- shared: calls before the attack index stay clean, both variants ---

@pytest.mark.parametrize(
    "generator",
    [generate_param_tampering_missing_session, generate_param_tampering_unexpected_session],
)
def test_calls_before_attack_index_stay_clean(schema_registry, generator):
    attack = generator(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(4))
    for i, call in enumerate(attack.session.calls):
        if i == attack.attack_call_index:
            continue
        result = check_schema(registry=schema_registry, tool_name=call.tool_name, params=call.params)
        assert result.is_violation is False, f"False positive at call {i}: {call}"
