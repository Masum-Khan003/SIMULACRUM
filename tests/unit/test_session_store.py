"""
Verifies InMemorySessionStore (§03/§06): call accumulation, tool
footprint tracking, and cross-session isolation — the exact bug class
avoided by requiring session_id explicitly at every call site instead
of implicit "current session" state.
"""
import pytest

from simulacrum.interception import InMemorySessionStore
from simulacrum.task_sim import ToolCall


@pytest.fixture
def store():
    return InMemorySessionStore()


def test_empty_session_returns_empty(store):
    assert store.get_calls(session_id="unknown") == ()
    assert store.get_tool_footprint(session_id="unknown") == frozenset()


def test_append_and_retrieve_single_call(store):
    call = ToolCall(tool_name="read_inbox", params={"count": "5"}, turn_index=0)
    store.append_call(session_id="s1", call=call)
    assert store.get_calls(session_id="s1") == (call,)


def test_calls_accumulate_in_order(store):
    c1 = ToolCall(tool_name="read_inbox", params={}, turn_index=0)
    c2 = ToolCall(tool_name="reply_to_email", params={}, turn_index=1)
    store.append_call(session_id="s1", call=c1)
    store.append_call(session_id="s1", call=c2)
    assert store.get_calls(session_id="s1") == (c1, c2)


def test_tool_footprint_accumulates_unique_tool_names(store):
    store.append_call(session_id="s1", call=ToolCall(tool_name="read_inbox", params={}, turn_index=0))
    store.append_call(session_id="s1", call=ToolCall(tool_name="read_inbox", params={}, turn_index=1))
    store.append_call(session_id="s1", call=ToolCall(tool_name="reply_to_email", params={}, turn_index=2))
    footprint = store.get_tool_footprint(session_id="s1")
    assert footprint == frozenset({"read_inbox", "reply_to_email"})


def test_sessions_are_isolated_from_each_other(store):
    """
    The specific bug class this design guards against: no implicit
    'current session' state, so two sessions' calls must never mix
    even if interleaved.
    """
    store.append_call(session_id="s1", call=ToolCall(tool_name="read_inbox", params={}, turn_index=0))
    store.append_call(session_id="s2", call=ToolCall(tool_name="delete_data", params={}, turn_index=0))
    store.append_call(session_id="s1", call=ToolCall(tool_name="reply_to_email", params={}, turn_index=1))

    s1_footprint = store.get_tool_footprint(session_id="s1")
    s2_footprint = store.get_tool_footprint(session_id="s2")

    assert s1_footprint == frozenset({"read_inbox", "reply_to_email"})
    assert s2_footprint == frozenset({"delete_data"})
    assert "delete_data" not in s1_footprint
    assert "read_inbox" not in s2_footprint


def test_get_calls_returns_tuple_not_mutable_list(store):
    """
    Callers must not be able to mutate internal session state by
    holding a reference to what get_calls() returns.
    """
    store.append_call(session_id="s1", call=ToolCall(tool_name="read_inbox", params={}, turn_index=0))
    calls = store.get_calls(session_id="s1")
    assert isinstance(calls, tuple)
