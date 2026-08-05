"""
Verifies the loop-evasion attack corpus (§04/§09 gap 5): a retry with
varied params after a BLOCKED outcome is correctly flagged as evasion
by check_tool_loop_rate, using the real InMemorySessionStore outcome
history — not a hand-constructed detector-only test case.
"""
import random

import pytest

from simulacrum.attack_suite.loop_evasion import (
    generate_loop_evasion_scenario,
    seed_blocked_attempt,
)
from simulacrum.detectors import check_tool_loop_rate
from simulacrum.interception import CallOutcome, InMemorySessionStore

EVASION_TOOLS = ["send_payment", "delete_data"]


def test_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool_name"):
        generate_loop_evasion_scenario(tool_name="not_real", rng=random.Random(1))


def test_scenario_generation_deterministic_under_seed():
    a = generate_loop_evasion_scenario(tool_name="send_payment", rng=random.Random(5))
    b = generate_loop_evasion_scenario(tool_name="send_payment", rng=random.Random(5))
    assert a.session_id == b.session_id
    assert a.blocked_params == b.blocked_params
    assert a.retry_params == b.retry_params


def test_retry_params_differ_from_blocked_params():
    """
    Sanity check on the corpus itself: if blocked/retry params were
    identical, this wouldn't be an evasion scenario at all (evasion
    requires VARIED params per §09's definition) — would be a rate
    case instead.
    """
    for tool_name in EVASION_TOOLS:
        scenario = generate_loop_evasion_scenario(tool_name=tool_name, rng=random.Random(1))
        assert scenario.blocked_params != scenario.retry_params


@pytest.mark.parametrize("tool_name", EVASION_TOOLS)
def test_seeded_retry_flagged_as_evasion(tool_name):
    store = InMemorySessionStore()
    scenario = generate_loop_evasion_scenario(tool_name=tool_name, rng=random.Random(2))
    seed_blocked_attempt(store=store, scenario=scenario)

    result = check_tool_loop_rate(
        session_store=store,
        session_id=scenario.session_id,
        tool_name=scenario.tool_name,
        params=scenario.retry_params,
    )
    assert result.is_evasion_retry is True
    assert result.is_flagged is True


def test_recall_across_many_seeds_and_tools():
    total = detected = 0
    for tool_name in EVASION_TOOLS:
        for seed in range(50):
            store = InMemorySessionStore()
            scenario = generate_loop_evasion_scenario(tool_name=tool_name, rng=random.Random(seed))
            seed_blocked_attempt(store=store, scenario=scenario)
            result = check_tool_loop_rate(
                session_store=store,
                session_id=scenario.session_id,
                tool_name=scenario.tool_name,
                params=scenario.retry_params,
            )
            total += 1
            if result.is_evasion_retry:
                detected += 1
    assert total == 100
    assert detected == total, f"Recall: {detected}/{total}"


def test_benign_retry_after_error_not_flagged_as_evasion_for_comparison():
    """
    Direct contrast case, using the SAME store/detector path as the
    evasion scenarios above but with a TOOL_ERROR outcome instead of
    BLOCKED — confirms the corpus's ground truth actually depends on
    outcome type, not just 'params changed on retry'.
    """
    from simulacrum.task_sim import ToolCall

    store = InMemorySessionStore()
    store.append_attempt(
        session_id="benign-1",
        call=ToolCall(tool_name="send_payment", params={"amount": "5000"}, turn_index=0),
        outcome=CallOutcome.TOOL_ERROR,
    )
    result = check_tool_loop_rate(
        session_store=store, session_id="benign-1", tool_name="send_payment", params={"amount": "4999"}
    )
    assert result.is_benign_retry is True
    assert result.is_evasion_retry is False
    assert result.is_flagged is False
