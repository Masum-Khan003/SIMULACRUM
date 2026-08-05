"""
Verifies exfiltration detector (§04/§09 session-level): frequency
signal (repeated outbound calls, any tool) and content signal
(anomalously large param value) are correctly isolated from each
other, and non-outbound tools never trigger either.
"""
import pytest

from simulacrum.detectors import check_exfiltration
from simulacrum.interception import CallOutcome, InMemorySessionStore
from simulacrum.task_sim import ToolCall


@pytest.fixture
def store():
    return InMemorySessionStore()


def test_non_outbound_tool_never_flagged(store):
    result = check_exfiltration(
        session_store=store, session_id="s1", tool_name="read_inbox", params={"count": "5"}
    )
    assert result.is_flagged is False
    assert result.outbound_call_count == 0


def test_first_outbound_call_normal_content_not_flagged(store):
    result = check_exfiltration(
        session_store=store,
        session_id="s1",
        tool_name="reply_to_email",
        params={"email_id": "1", "body": "Acknowledged, will follow up."},
    )
    assert result.is_flagged is False


def test_frequency_exceeded_flags_regardless_of_content(store):
    """Repeated outbound calls across DIFFERENT tools still count toward frequency."""
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="reply_to_email", params={"body": "short"}, turn_index=0),
        outcome=CallOutcome.ALLOWED,
    )
    store.append_attempt(
        session_id="s1",
        call=ToolCall(tool_name="set_forwarding_rule", params={"target": "x@y.com"}, turn_index=1),
        outcome=CallOutcome.ALLOWED,
    )
    result = check_exfiltration(
        session_store=store,
        session_id="s1",
        tool_name="send_payment",
        params={"amount": "10"},
    )
    assert result.outbound_call_count == 3
    assert result.is_frequency_exceeded is True
    assert result.is_flagged is True


def test_content_anomaly_flags_independent_of_frequency(store):
    """A single outbound call with an oversized param value flags on content alone."""
    huge_body = "x" * 500
    result = check_exfiltration(
        session_store=store,
        session_id="s1",
        tool_name="reply_to_email",
        params={"email_id": "1", "body": huge_body},
    )
    assert result.outbound_call_count == 1
    assert result.is_frequency_exceeded is False
    assert result.is_content_anomalous is True
    assert result.anomalous_params == frozenset({"body"})
    assert result.is_flagged is True


def test_custom_thresholds_respected(store):
    result = check_exfiltration(
        session_store=store,
        session_id="s1",
        tool_name="reply_to_email",
        params={"body": "short"},
        frequency_threshold=1,  # even the first call trips this
    )
    assert result.is_frequency_exceeded is True
