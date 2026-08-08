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
    """
    Real, structural invariant (finding 014: task_sim now generates
    variable-length sessions via repeatable step groups, so an exact
    hardcoded call list is stale by construction) -- read_inbox calls
    must all come before reply_to_email calls (group ORDER is fixed,
    only REPEAT COUNT varies), and turn_index must be a real, gapless
    0..N-1 sequence matching call order.
    """
    session = generate_session(task_type=TaskType.INBOX_TRIAGE, rng=random.Random(7))
    assert session.task_type is TaskType.INBOX_TRIAGE
    tool_names = [c.tool_name for c in session.calls]
    assert set(tool_names) == {"read_inbox", "reply_to_email"}
    last_read_index = max(i for i, t in enumerate(tool_names) if t == "read_inbox")
    first_reply_index = min(i for i, t in enumerate(tool_names) if t == "reply_to_email")
    assert last_read_index < first_reply_index, "read_inbox group must come before reply_to_email group"
    assert [c.turn_index for c in session.calls] == list(range(len(session.calls)))


def test_flight_booking_structure():
    """Same real, structural invariant as inbox_triage above."""
    session = generate_session(task_type=TaskType.FLIGHT_BOOKING, rng=random.Random(7))
    assert session.task_type is TaskType.FLIGHT_BOOKING
    tool_names = [c.tool_name for c in session.calls]
    assert set(tool_names) == {"search_flights", "book_flight"}
    last_search_index = max(i for i, t in enumerate(tool_names) if t == "search_flights")
    first_book_index = min(i for i, t in enumerate(tool_names) if t == "book_flight")
    assert last_search_index < first_book_index, "search_flights group must come before book_flight group"


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
