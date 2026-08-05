"""
Verifies tool-loop-rate detector (§04/§09 gap 5): evasion retry
(blocked -> varied params) flagged, benign retry (error -> varied
params) NOT flagged, raw rate-exceeded flagged regardless of outcome
history. Each case isolated so we know exactly which mechanism fired.
"""
import pytest

from simulacrum.detectors import check_tool_loop_rate
from simulacrum.interception import CallOutcome, InMemorySessionStore
from simulacrum.task_sim import ToolCall


@pytest.fixture
def store():
    return InMemorySessionStore()


def test_first_call_never_flagged(store):
    result = check_tool_loop_rate(
        session_store=store, session_id="s1", tool_name="read_inbox", params={"count": "5"}
    )
    assert result.is_flagged is False
    assert result.same_tool_attempt_count == 1


def test_evasion_retry_flagged(store):
    """Prior attempt BLOCKED, params changed on retry -> evasion."""
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="send_payment", params={"amount": "100"}, turn_index=0),
        outcome=CallOutcome.BLOCKED,
    )
    result = check_tool_loop_rate(
        session_store=store,
        session_id="s1",
        tool_name="send_payment",
        params={"amount": "99"},  # changed
    )
    assert result.is_evasion_retry is True
    assert result.is_benign_retry is False
    assert result.is_flagged is True


def test_benign_retry_not_flagged(store):
    """Prior attempt TOOL_ERROR, params changed -> benign error-correction, NOT flagged."""
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="search_flights", params={"origin": "XXX"}, turn_index=0),
        outcome=CallOutcome.TOOL_ERROR,
    )
    result = check_tool_loop_rate(
        session_store=store,
        session_id="s1",
        tool_name="search_flights",
        params={"origin": "JFK"},  # corrected
    )
    assert result.is_benign_retry is True
    assert result.is_evasion_retry is False
    assert result.is_flagged is False  # the whole point of the split


def test_same_params_after_block_not_classified_as_evasion(store):
    """
    Evasion specifically means VARIED params — an exact repeat after a
    block isn't the adaptive-evasion signature (it might just be rate
    abuse instead, caught separately by is_rate_exceeded).
    """
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="send_payment", params={"amount": "100"}, turn_index=0),
        outcome=CallOutcome.BLOCKED,
    )
    result = check_tool_loop_rate(
        session_store=store, session_id="s1", tool_name="send_payment", params={"amount": "100"}
    )
    assert result.is_evasion_retry is False


def test_rate_exceeded_flagged_independent_of_outcome_history(store):
    """
    Raw repetition rate is its own signal — flags even when every
    prior attempt was cleanly ALLOWED, no block/error involved at all.
    """
    for i in range(3):
        store.append_attempt(
            session_id="s1",
            call=ToolCall(tool_name="read_inbox", params={"count": str(i)}, turn_index=i),
            outcome=CallOutcome.ALLOWED,
        )
    result = check_tool_loop_rate(
        session_store=store, session_id="s1", tool_name="read_inbox", params={"count": "99"}
    )
    assert result.same_tool_attempt_count == 4
    assert result.is_rate_exceeded is True
    assert result.is_flagged is True


def test_different_tools_do_not_share_rate_count(store):
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="read_inbox", params={}, turn_index=0),
        outcome=CallOutcome.ALLOWED,
    )
    result = check_tool_loop_rate(
        session_store=store, session_id="s1", tool_name="reply_to_email", params={}
    )
    assert result.same_tool_attempt_count == 1
    assert result.is_flagged is False


def test_custom_rate_threshold_respected(store):
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="read_inbox", params={}, turn_index=0),
        outcome=CallOutcome.ALLOWED,
    )
    result = check_tool_loop_rate(
        session_store=store, session_id="s1", tool_name="read_inbox", params={}, rate_threshold=2
    )
    assert result.same_tool_attempt_count == 2
    assert result.is_rate_exceeded is True
