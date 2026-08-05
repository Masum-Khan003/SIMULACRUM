"""
Verifies the permission-escalation detector (§04/§09 session-level)
and its attack corpus: baseline footprints derived from task_sim
directly, escalated tools correctly flagged, normal sessions never
false-positive, and — the key distinction from injection.py — this
detects via SESSION FOOTPRINT, independent of per-call semantics.
"""
import random

import pytest

from simulacrum.attack_suite import generate_permission_escalation_session
from simulacrum.detectors import check_permission_escalation
from simulacrum.interception import InMemorySessionStore
from simulacrum.task_sim import TaskType, generate_session

ESCALATION_TOOLS = ["send_payment", "set_forwarding_rule", "delete_data", "modify_permissions"]


def test_unknown_escalated_tool_raises():
    with pytest.raises(ValueError, match="Unknown escalated_tool_name"):
        generate_permission_escalation_session(
            task_type=TaskType.INBOX_TRIAGE,
            escalated_tool_name="not_real",
            rng=random.Random(1),
        )


def test_generation_is_deterministic_under_seed():
    a = generate_permission_escalation_session(
        task_type=TaskType.INBOX_TRIAGE, escalated_tool_name="delete_data", rng=random.Random(5)
    )
    b = generate_permission_escalation_session(
        task_type=TaskType.INBOX_TRIAGE, escalated_tool_name="delete_data", rng=random.Random(5)
    )
    assert a.session == b.session


def test_normal_session_footprint_not_escalated():
    session = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(1))
    footprint = frozenset(c.tool_name for c in session.calls)
    result = check_permission_escalation(task_type=TaskType.INBOX_TRIAGE, session_footprint=footprint)
    assert result.is_escalated is False


@pytest.mark.parametrize("tool_name", ESCALATION_TOOLS)
def test_escalated_session_footprint_flagged(tool_name):
    attack = generate_permission_escalation_session(
        task_type=TaskType.FLIGHT_BOOKING, escalated_tool_name=tool_name, rng=random.Random(2)
    )
    footprint = frozenset(c.tool_name for c in attack.session.calls)
    result = check_permission_escalation(task_type=TaskType.FLIGHT_BOOKING, session_footprint=footprint)
    assert result.is_escalated is True
    assert result.escalated_tools == frozenset({tool_name})


def test_recall_across_many_seeds_and_task_types():
    total = detected = 0
    for task_type in TaskType:
        for tool_name in ESCALATION_TOOLS:
            for seed in range(25):
                attack = generate_permission_escalation_session(
                    task_type=task_type, escalated_tool_name=tool_name, rng=random.Random(seed)
                )
                footprint = frozenset(c.tool_name for c in attack.session.calls)
                result = check_permission_escalation(task_type=task_type, session_footprint=footprint)
                total += 1
                if result.is_escalated:
                    detected += 1
    assert total == len(TaskType) * len(ESCALATION_TOOLS) * 25
    assert detected == total, f"Recall: {detected}/{total}"


def test_false_positive_rate_on_normal_sessions():
    """
    Precision check across many normal sessions: baseline-derived
    footprint checking must never flag a session task_sim actually
    generates.
    """
    false_positives = []
    for task_type in TaskType:
        for seed in range(50):
            session = generate_session(task_type=task_type, rng=random.Random(seed))
            footprint = frozenset(c.tool_name for c in session.calls)
            result = check_permission_escalation(task_type=task_type, session_footprint=footprint)
            if result.is_escalated:
                false_positives.append((task_type, seed))
    assert false_positives == [], f"False positives: {false_positives}"


def test_integration_with_session_store():
    """
    End-to-end through the real SessionStore interface, not just a
    manually-built footprint set — proves the store's
    get_tool_footprint() output is exactly what this detector needs.
    """
    store = InMemorySessionStore()
    attack = generate_permission_escalation_session(
        task_type=TaskType.INBOX_TRIAGE, escalated_tool_name="modify_permissions", rng=random.Random(3)
    )
    for call in attack.session.calls:
        store.append_call(session_id=attack.session.session_id, call=call)

    footprint = store.get_tool_footprint(session_id=attack.session.session_id)
    result = check_permission_escalation(task_type=TaskType.INBOX_TRIAGE, session_footprint=footprint)
    assert result.is_escalated is True
    assert "modify_permissions" in result.escalated_tools
