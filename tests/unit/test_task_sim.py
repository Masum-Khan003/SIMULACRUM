"""
Verifies task_sim as THE single shared session generator (§08, resolves
finding 011): determinism under a seeded RNG, no default RNG, correct
per-task-type call structure.
"""
import random

import pytest

from simulacrum.task_sim import TaskType, generate_session


def test_generate_session_requires_rng_kwarg():
    with pytest.raises(TypeError):
        generate_session(task_type=TaskType.INBOX_TRIAGE)  # missing rng


def test_same_seed_produces_identical_session():
    s1 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(42))
    s2 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(42))
    assert s1 == s2


def test_different_seed_produces_different_session():
    s1 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(1))
    s2 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(2))
    assert s1 != s2


def test_inbox_triage_structure():
    session = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(7))
    assert session.task_type is TaskType.INBOX_TRIAGE
    assert [c.tool_name for c in session.calls] == ["read_inbox", "reply_to_email"]
    assert session.calls[0].turn_index == 0
    assert session.calls[1].turn_index == 1


def test_flight_booking_structure():
    session = generate_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(7))
    assert session.task_type is TaskType.FLIGHT_BOOKING
    assert [c.tool_name for c in session.calls] == ["search_flights", "book_flight"]


def test_params_vary_across_calls_with_different_rng():
    seen_origins = {
        generate_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(seed))
        .calls[0]
        .params["origin"]
        for seed in range(20)
    }
    assert len(seen_origins) > 1


def test_session_id_deterministic_under_same_seed():
    s1 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(99))
    s2 = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(99))
    assert s1.session_id == s2.session_id
