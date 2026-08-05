"""
Verifies the prompt-injection attack corpus (§04/§08): the substituted
off-task call is schema-VALID (schema detector stays quiet — this is
exactly the gap that motivated building param-vs-task divergence at
all) but semantically divergent (divergence detector catches it).

This is the project's first proof that the two detectors are genuinely
complementary, not redundant — each catches what the other structurally
cannot.
"""
import random

import pytest

from simulacrum.attack_suite import generate_injection_session
from simulacrum.attribution import FakeSemanticEmbedder, TaskRepresentation
from simulacrum.detectors import (
    build_default_schema_registry,
    check_param_divergence,
    check_schema,
)
from simulacrum.task_sim import TASK_INITIAL_USER_TEXT, TaskType

ATTACK_TOOLS = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]


@pytest.fixture
def schema_registry():
    return build_default_schema_registry()


@pytest.fixture
def embedder():
    return FakeSemanticEmbedder()


def test_unknown_injected_tool_raises():
    with pytest.raises(ValueError, match="Unknown injected_tool_name"):
        generate_injection_session(
            task_type=TaskType.INBOX_TRIAGE,
            injected_tool_name="not_a_real_tool",
            rng=random.Random(1),
        )


def test_generation_is_deterministic_under_seed():
    a = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name="send_payment", rng=random.Random(5)
    )
    b = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name="send_payment", rng=random.Random(5)
    )
    assert a.session == b.session


def test_attack_call_is_appended_after_legitimate_calls():
    attack = generate_injection_session(
        task_type=TaskType.FLIGHT_BOOKING, injected_tool_name="delete_data", rng=random.Random(1)
    )
    normal_call_count = 2  # search_flights, book_flight
    assert attack.attack_call_index == normal_call_count
    assert len(attack.session.calls) == normal_call_count + 1
    assert attack.session.calls[attack.attack_call_index].tool_name == "delete_data"


def test_ground_truth_label_and_tool_recorded():
    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE,
        injected_tool_name="modify_permissions",
        rng=random.Random(2),
    )
    assert attack.ground_truth_label == "prompt_injection_tool_output"
    assert attack.injected_tool_name == "modify_permissions"


def test_injected_content_is_needle_in_haystack():
    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name="send_payment", rng=random.Random(3)
    )
    assert len(attack.injected_document_text) > 200
    assert attack.injected_document_text.count(".") > 3


@pytest.mark.parametrize("tool_name", ATTACK_TOOLS)
def test_schema_detector_does_not_flag_the_injected_call(schema_registry, tool_name):
    """
    THE key gap this attack class exposes: the injected call is
    schema-valid (well-formed params). Schema conformance has no
    registered schema for attack-target tools at all — checking it
    would raise UnregisteredSchemaError, not silently pass, which is
    itself informative: schema conformance structurally cannot even
    evaluate calls to tools outside its known vocabulary.
    """
    from simulacrum.detectors import UnregisteredSchemaError

    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name=tool_name, rng=random.Random(4)
    )
    attack_call = attack.session.calls[attack.attack_call_index]
    with pytest.raises(UnregisteredSchemaError):
        check_schema(registry=schema_registry, tool_name=attack_call.tool_name, params=attack_call.params)


@pytest.mark.parametrize("tool_name", ATTACK_TOOLS)
def test_divergence_detector_flags_the_injected_call(embedder, tool_name):
    """
    The real catch: param-vs-task divergence DOES have the structural
    signal to flag this, because it compares call semantics to task
    semantics rather than checking a fixed per-tool schema.
    """
    attack = generate_injection_session(
        task_type=TaskType.INBOX_TRIAGE, injected_tool_name=tool_name, rng=random.Random(4)
    )
    attack_call = attack.session.calls[attack.attack_call_index]
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.INBOX_TRIAGE]
    )
    result = check_param_divergence(
        task_representation=task, tool_name=attack_call.tool_name, params=attack_call.params
    )
    assert result.is_divergent is True, f"Missed injection: {tool_name}, sim={result.similarity}"


def test_divergence_recall_across_many_seeds_and_task_types(embedder):
    """
    Real measurement: across many seeds, task types, and all four
    attack-target tools, does divergence actually catch every
    injected call? First honest recall number for this attack class.
    """
    total = detected = 0
    for task_type in TaskType:
        for tool_name in ATTACK_TOOLS:
            for seed in range(25):
                attack = generate_injection_session(
                    task_type=task_type, injected_tool_name=tool_name, rng=random.Random(seed)
                )
                attack_call = attack.session.calls[attack.attack_call_index]
                task = TaskRepresentation.start(
                    embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[task_type]
                )
                result = check_param_divergence(
                    task_representation=task,
                    tool_name=attack_call.tool_name,
                    params=attack_call.params,
                )
                total += 1
                if result.is_divergent:
                    detected += 1
    assert total == len(TaskType) * len(ATTACK_TOOLS) * 25  # computed, not hardcoded — survives task_type count changes
    print(f"\nInjection detection recall: {detected}/{total} ({100*detected/total:.1f}%)")
    assert detected == total, f"Recall: {detected}/{total} — divergence detector missed some injections"


def test_legitimate_calls_in_attack_session_stay_non_divergent(embedder):
    """
    Precision check: the LEGITIMATE calls in an attack session (before
    the injected one) must NOT be flagged — false positives here would
    undermine the whole detector's usability.
    """
    attack = generate_injection_session(
        task_type=TaskType.FLIGHT_BOOKING, injected_tool_name="send_payment", rng=random.Random(7)
    )
    task = TaskRepresentation.start(
        embedder=embedder, initial_user_text=TASK_INITIAL_USER_TEXT[TaskType.FLIGHT_BOOKING]
    )
    for i, call in enumerate(attack.session.calls):
        if i == attack.attack_call_index:
            continue
        result = check_param_divergence(task_representation=task, tool_name=call.tool_name, params=call.params)
        assert result.is_divergent is False, f"False positive at call {i}: {call}"
