"""
Verifies the fake tool registry: atomic tier+implementation
registration, unregistered-tool enforcement at the actual call site
(not just classification), and the default stub set matches task_sim's
vocabulary (§02, §07).
"""
import pytest

from simulacrum.interception import FakeToolRegistry, build_default_registry
from simulacrum.risk_tiers import RiskTier, ToolRegistry, UnregisteredToolError


@pytest.fixture
def empty_registry():
    return FakeToolRegistry(tier_registry=ToolRegistry())


def test_call_unregistered_tool_raises(empty_registry):
    with pytest.raises(UnregisteredToolError):
        empty_registry.call(tool_name="does_not_exist", params={})


def test_register_and_call_roundtrip(empty_registry):
    empty_registry.register(
        tool_name="echo",
        tier=RiskTier.READ_ONLY,
        fn=lambda p: {"echoed": p.get("msg", "")},
    )
    result = empty_registry.call(tool_name="echo", params={"msg": "hi"})
    assert result == {"echoed": "hi"}


def test_registered_tool_has_correct_tier_in_underlying_registry():
    tier_registry = ToolRegistry()
    registry = FakeToolRegistry(tier_registry=tier_registry)
    registry.register(tool_name="echo", tier=RiskTier.IRREVERSIBLE_HIGH_VALUE, fn=lambda p: p)
    reg = tier_registry.get(tool_name="echo")
    assert reg.tier is RiskTier.IRREVERSIBLE_HIGH_VALUE


def test_default_registry_has_all_task_sim_tools():
    """
    Each stub returns its own shape (a query result vs. a confirmation)
    — asserting a specific shared key like 'status' is wrong, since
    read-only query tools (search_flights, read_inbox) don't confirm
    a status the way a write tool does. Assert only that each call
    succeeds and returns a non-empty dict.
    """
    registry = build_default_registry(tier_registry=ToolRegistry())
    expected_calls = [
        ("read_inbox", {"count": "5"}),
        ("reply_to_email", {"email_id": "1", "body": "hi"}),
        ("search_flights", {"origin": "JFK", "destination": "LHR"}),
        ("book_flight", {"flight_id": "FL1234"}),
    ]
    for tool_name, params in expected_calls:
        result = registry.call(tool_name=tool_name, params=params)
        assert isinstance(result, dict)
        assert len(result) > 0


def test_default_registry_tiers_match_spec():
    tier_registry = ToolRegistry()
    build_default_registry(tier_registry=tier_registry)
    assert tier_registry.get(tool_name="read_inbox").tier is RiskTier.READ_ONLY
    assert tier_registry.get(tool_name="search_flights").tier is RiskTier.READ_ONLY
    assert tier_registry.get(tool_name="reply_to_email").tier is RiskTier.IRREVERSIBLE_LOW_VALUE
    assert tier_registry.get(tool_name="book_flight").tier is RiskTier.IRREVERSIBLE_LOW_VALUE


def test_task_sim_generated_calls_are_all_callable():
    """
    Integration check: every tool_name task_sim's generate_session()
    can produce must exist in the default fake tool registry. This is
    the vocabulary-consistency guarantee the whole point of building
    them together enforces.
    """
    import random
    from simulacrum.task_sim import TaskType, generate_session

    registry = build_default_registry(tier_registry=ToolRegistry())
    for task_type in TaskType:
        session = generate_session(task_type=task_type, rng=random.Random(1))
        for call in session.calls:
            result = registry.call(tool_name=call.tool_name, params=call.params)
            assert result is not None
