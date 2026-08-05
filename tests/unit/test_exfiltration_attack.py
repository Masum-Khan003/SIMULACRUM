"""
Verifies exfiltration attack corpus (§04, both variants) against the
real detector, using a real session store populated call-by-call —
proving ground truth agrees with check_exfiltration's independent
frequency/content signals.
"""
import random

import pytest

from simulacrum.attack_suite import (
    generate_exfiltration_content_session,
    generate_exfiltration_frequency_session,
)
from simulacrum.detectors import check_exfiltration
from simulacrum.session import InMemorySessionStore
from simulacrum.task_sim import TaskType


def _replay_through_detector(session, up_to_index):
    """Replays a session's calls into a fresh store, checking exfiltration
    at each step, up to and including up_to_index. Returns the result
    at up_to_index."""
    store = InMemorySessionStore()
    result = None
    for i, call in enumerate(session.calls):
        result = check_exfiltration(
            session_store=store, session_id=session.session_id,
            tool_name=call.tool_name, params=call.params,
        )
        store.append_call(session_id=session.session_id, call=call)
        if i == up_to_index:
            return result
    return result


def test_generation_deterministic_under_seed():
    a = generate_exfiltration_frequency_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    b = generate_exfiltration_frequency_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(5))
    assert a.session == b.session


def test_frequency_variant_flags_via_frequency_not_content():
    attack = generate_exfiltration_frequency_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(1))
    result = _replay_through_detector(attack.session, attack.attack_call_index)
    assert result.is_frequency_exceeded is True
    assert result.is_content_anomalous is False
    assert result.is_flagged is True


def test_content_variant_flags_via_content_not_frequency():
    attack = generate_exfiltration_content_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(2))
    result = _replay_through_detector(attack.session, attack.attack_call_index)
    assert result.is_content_anomalous is True
    assert result.is_frequency_exceeded is False
    assert result.is_flagged is True


def test_frequency_recall_across_many_seeds():
    total = detected = 0
    for task_type in TaskType:
        for seed in range(30):
            attack = generate_exfiltration_frequency_session(task_type=task_type, rng=random.Random(seed))
            result = _replay_through_detector(attack.session, attack.attack_call_index)
            total += 1
            if result.is_flagged:
                detected += 1
    assert total == 60
    assert detected == total, f"Recall: {detected}/{total}"


def test_content_recall_across_many_seeds():
    total = detected = 0
    for task_type in TaskType:
        for seed in range(30):
            attack = generate_exfiltration_content_session(task_type=task_type, rng=random.Random(seed))
            result = _replay_through_detector(attack.session, attack.attack_call_index)
            total += 1
            if result.is_flagged:
                detected += 1
    assert total == 60
    assert detected == total, f"Recall: {detected}/{total}"
