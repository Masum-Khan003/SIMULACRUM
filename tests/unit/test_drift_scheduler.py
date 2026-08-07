"""
Verifies DriftScheduler (§03/§12: real async/background drift
checking, closing the gap where only an on-demand endpoint existed).
Both the synchronous run_once() trigger logic (no real sleeping) and
the genuine asyncio background loop (real sleep, proving it actually
runs unattended) are tested.
"""
import asyncio

import pytest

from simulacrum.attribution import NullDriftDetector
from simulacrum.attribution.drift_scheduler import DriftScheduler


@pytest.fixture
def fallback():
    return NullDriftDetector()


def test_run_once_does_not_trigger_below_interval(fallback):
    scheduler = DriftScheduler(drift_detector=fallback, check_interval_calls=3)
    decision = scheduler.run_once(
        session_id="s1", task_description="check inbox", call_history=("read_inbox()",)
    )
    assert decision is None  # only 1 call so far, interval is 3


def test_run_once_triggers_at_interval(fallback):
    scheduler = DriftScheduler(drift_detector=fallback, check_interval_calls=3)
    decision = scheduler.run_once(
        session_id="s1",
        task_description="check inbox",
        call_history=("read_inbox()", "reply_to_email()", "reply_to_email()"),
    )
    assert decision is not None
    assert decision.checked_at_call_count == 3


def test_standing_decision_persists_between_calls(fallback):
    scheduler = DriftScheduler(drift_detector=fallback, check_interval_calls=3)
    scheduler.run_once(
        session_id="s1",
        task_description="check inbox",
        call_history=("a()", "b()", "c()"),
    )
    # Below next trigger threshold -- should return the PREVIOUS
    # standing decision, not None, since one was already cached.
    decision = scheduler.run_once(
        session_id="s1",
        task_description="check inbox",
        call_history=("a()", "b()", "c()", "d()"),
    )
    assert decision is not None
    assert decision.checked_at_call_count == 3  # unchanged from the first check


def test_standing_decision_updates_at_next_interval(fallback):
    scheduler = DriftScheduler(drift_detector=fallback, check_interval_calls=3)
    scheduler.run_once(session_id="s1", task_description="t", call_history=("a()", "b()", "c()"))
    decision = scheduler.run_once(
        session_id="s1", task_description="t", call_history=("a()", "b()", "c()", "d()", "e()", "f()")
    )
    assert decision.checked_at_call_count == 6  # advanced to the new check point


def test_get_standing_decision_returns_none_for_unknown_session(fallback):
    scheduler = DriftScheduler(drift_detector=fallback)
    assert scheduler.get_standing_decision(session_id="never-seen") is None


def test_sessions_are_independently_tracked(fallback):
    scheduler = DriftScheduler(drift_detector=fallback, check_interval_calls=2)
    scheduler.run_once(session_id="s1", task_description="t1", call_history=("a()", "b()"))
    scheduler.run_once(session_id="s2", task_description="t2", call_history=("x()",))

    assert scheduler.get_standing_decision(session_id="s1") is not None
    assert scheduler.get_standing_decision(session_id="s2") is None  # below interval


@pytest.mark.asyncio
async def test_real_background_loop_actually_runs_unattended(fallback):
    """
    THE real proof this is genuinely async/background, not just a
    method someone has to call manually: starts the actual asyncio
    loop with a short real interval, waits with real asyncio.sleep,
    and confirms a session that was never manually checked gets a
    standing decision anyway -- because the background loop itself
    picked it up.
    """
    scheduler = DriftScheduler(drift_detector=fallback, poll_interval_seconds=0.1, check_interval_calls=1)

    call_log = [("s1", "check inbox", ("read_inbox()", "delete_data()"))]

    def get_active_sessions():
        return call_log

    await scheduler.start(get_active_sessions=get_active_sessions)
    await asyncio.sleep(0.35)  # real wait, long enough for several poll cycles
    await scheduler.stop()

    decision = scheduler.get_standing_decision(session_id="s1")
    assert decision is not None, "Background loop should have picked up and checked s1 on its own"
