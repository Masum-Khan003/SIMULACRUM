"""
Verifies the param-tampering attack corpus (§08 Layer 2, first of six
attack classes) and, critically, that the schema detector actually
catches it. Ground truth (attack_call_index, label) must match what
the detector independently flags — that agreement is the whole point
of building ground truth before serving (§05).
"""
import random

import pytest

from simulacrum.attack_suite import generate_param_tampering_session
from simulacrum.detectors import build_default_schema_registry, check_schema
from simulacrum.task_sim import TaskType


@pytest.fixture
def schema_registry():
    return build_default_schema_registry()


def test_generation_is_deterministic_under_seed():
    a = generate_param_tampering_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    b = generate_param_tampering_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    assert a.session == b.session
    assert a.attack_call_index == b.attack_call_index


def test_attack_call_has_empty_params():
    attack = generate_param_tampering_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(1))
    attack_call = attack.session.calls[attack.attack_call_index]
    assert attack_call.params == {}


def test_injected_content_is_needle_in_haystack_not_standalone():
    """
    gap 8: injected text must be embedded inside realistic filler, not
    a short clean string. Check the document has substantial content
    beyond just the injection sentence.
    """
    attack = generate_param_tampering_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(2))
    assert len(attack.injected_document_text) > 200
    # the injection instruction should not be the entire document
    assert attack.injected_document_text.count(".") > 3


def test_ground_truth_label_recorded():
    attack = generate_param_tampering_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(3))
    assert attack.ground_truth_label == "param_tampering"


def test_schema_detector_flags_the_attack_call(schema_registry):
    attack = generate_param_tampering_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(4))
    attack_call = attack.session.calls[attack.attack_call_index]
    result = check_schema(
        registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params
    )
    assert result.is_violation is True
    assert len(result.missing_params) > 0


def test_schema_detector_does_not_flag_calls_before_the_attack(schema_registry):
    attack = generate_param_tampering_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(4))
    for i, call in enumerate(attack.session.calls):
        if i == attack.attack_call_index:
            continue
        result = check_schema(
            registry=schema_registry, tool_name=call.tool_name, params=call.params
        )
        assert result.is_violation is False, f"False positive at call {i}: {call}"


def test_detector_recall_across_many_seeds_and_task_types(schema_registry):
    """
    The real measurement: across many generated attack sessions, does
    the schema detector actually flag the attack call every time?
    This is the first real precision/recall data point in the project.
    """
    total = 0
    detected = 0
    for task_type in TaskType:
        for seed in range(50):
            attack = generate_param_tampering_session(task_type=task_type, rng=random.Random(seed))
            attack_call = attack.session.calls[attack.attack_call_index]
            result = check_schema(
                registry=schema_registry,
                tool_name=attack_call.tool_name,
                params=attack_call.params,
            )
            total += 1
            if result.is_violation:
                detected += 1
    assert total == 100
    assert detected == total, f"Recall: {detected}/{total} — schema detector missed some attacks"
