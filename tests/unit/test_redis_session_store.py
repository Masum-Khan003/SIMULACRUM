"""
Verifies RedisSessionStore against a REAL Redis instance (requires
`docker compose up -d` — see docker-compose.yml). Runs the exact same
assertions as test_session_store.py's InMemorySessionStore suite,
proving the SessionStore protocol abstraction is genuinely
interchangeable, not just superficially similar.

Each test uses a unique session_id (uuid-based) to avoid cross-test
pollution in the shared Redis instance, and cleans up its own keys
in a fixture teardown.
"""
import uuid

import pytest

from simulacrum.session import CallOutcome, RedisSessionStore
from simulacrum.task_sim import ToolCall

REDIS_URL = "redis://localhost:6379/0"


@pytest.fixture
def store():
    s = RedisSessionStore(redis_url=REDIS_URL)
    yield s
    # Teardown: clean up any keys this test created, scoped by prefix
    # rather than flushing the whole DB (which could nuke unrelated
    # data if this DB is ever shared with something else).
    for key in s._client.keys("simulacrum:session:test-*"):
        s._client.delete(key)


def _sid() -> str:
    return f"test-{uuid.uuid4()}"


def test_requires_redis_url_no_default():
    with pytest.raises(TypeError):
        RedisSessionStore()  # missing required redis_url


def test_empty_session_returns_empty(store):
    sid = _sid()
    assert store.get_calls(session_id=sid) == ()
    assert store.get_tool_footprint(session_id=sid) == frozenset()


def test_append_and_retrieve_single_call(store):
    sid = _sid()
    call = ToolCall(tool_name="read_inbox", params={"count": "5"}, turn_index=0)
    store.append_call(session_id=sid, call=call)
    assert store.get_calls(session_id=sid) == (call,)


def test_calls_accumulate_in_order(store):
    sid = _sid()
    c1 = ToolCall(tool_name="read_inbox", params={}, turn_index=0)
    c2 = ToolCall(tool_name="reply_to_email", params={}, turn_index=1)
    store.append_call(session_id=sid, call=c1)
    store.append_call(session_id=sid, call=c2)
    assert store.get_calls(session_id=sid) == (c1, c2)


def test_tool_footprint_accumulates_unique_tool_names(store):
    sid = _sid()
    store.append_call(session_id=sid, call=ToolCall(tool_name="read_inbox", params={}, turn_index=0))
    store.append_call(session_id=sid, call=ToolCall(tool_name="read_inbox", params={}, turn_index=1))
    store.append_call(session_id=sid, call=ToolCall(tool_name="reply_to_email", params={}, turn_index=2))
    footprint = store.get_tool_footprint(session_id=sid)
    assert footprint == frozenset({"read_inbox", "reply_to_email"})


def test_sessions_are_isolated_from_each_other(store):
    sid1, sid2 = _sid(), _sid()
    store.append_call(session_id=sid1, call=ToolCall(tool_name="read_inbox", params={}, turn_index=0))
    store.append_call(session_id=sid2, call=ToolCall(tool_name="delete_data", params={}, turn_index=0))
    store.append_call(session_id=sid1, call=ToolCall(tool_name="reply_to_email", params={}, turn_index=1))

    footprint1 = store.get_tool_footprint(session_id=sid1)
    footprint2 = store.get_tool_footprint(session_id=sid2)
    assert footprint1 == frozenset({"read_inbox", "reply_to_email"})
    assert footprint2 == frozenset({"delete_data"})


def test_outcome_round_trips_correctly(store):
    """
    THE thing InMemorySessionStore gets for free (no serialization)
    but RedisSessionStore must prove explicitly: outcome enum survives
    a real JSON serialize/deserialize round-trip through Redis.
    """
    sid = _sid()
    call = ToolCall(tool_name="send_payment", params={"amount": "100"}, turn_index=0)
    store.append_attempt(session_id=sid, call=call, outcome=CallOutcome.BLOCKED)
    attempts = store.get_attempts(session_id=sid)
    assert len(attempts) == 1
    assert attempts[0].outcome is CallOutcome.BLOCKED
    assert attempts[0].call == call


def test_params_with_special_characters_round_trip(store):
    """Params can contain arbitrary strings — confirm JSON encoding
    doesn't mangle quotes, unicode, etc."""
    sid = _sid()
    call = ToolCall(
        tool_name="reply_to_email",
        params={"body": 'Reply with "quotes" and üñïçødé and a newline\nhere'},
        turn_index=0,
    )
    store.append_call(session_id=sid, call=call)
    retrieved = store.get_calls(session_id=sid)
    assert retrieved == (call,)
