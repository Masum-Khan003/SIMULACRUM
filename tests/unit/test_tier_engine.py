"""
Verifies tier-engine: §13's response-tier decision matrix (using
detector-flag-count as the honest severity proxy, see
response_tier.py docstring), and ApprovalQueue lifecycle including
the timeout-vs-active-decision distinction (§13 v2) via an injectable
fake clock (no real 30-minute sleeps).
"""
import pytest

from simulacrum.risk_tiers import RiskTier
from simulacrum.tier_engine import (
    ApprovalAlreadyDecidedError,
    ApprovalOutcome,
    ApprovalQueue,
    UnknownApprovalRequestError,
    ResponseTier,
    decide_response_tier,
)


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- Response tier decision matrix ---

def test_zero_flags_always_allows():
    for tier in RiskTier:
        result = decide_response_tier(flagged_detector_count=0, tool_tier=tier)
        assert result is ResponseTier.ALLOW


def test_high_value_irreversible_any_flag_blocks():
    for count in (1, 2, 5):
        result = decide_response_tier(
            flagged_detector_count=count, tool_tier=RiskTier.IRREVERSIBLE_HIGH_VALUE
        )
        assert result is ResponseTier.BLOCK


def test_low_value_irreversible_any_flag_requires_approval():
    for count in (1, 2, 5):
        result = decide_response_tier(
            flagged_detector_count=count, tool_tier=RiskTier.IRREVERSIBLE_LOW_VALUE
        )
        assert result is ResponseTier.REQUIRE_APPROVAL


@pytest.mark.parametrize("tier", [RiskTier.READ_ONLY, RiskTier.REVERSIBLE_WRITE])
def test_read_only_reversible_single_flag_just_flags(tier):
    result = decide_response_tier(flagged_detector_count=1, tool_tier=tier)
    assert result is ResponseTier.FLAG


@pytest.mark.parametrize("tier", [RiskTier.READ_ONLY, RiskTier.REVERSIBLE_WRITE])
def test_read_only_reversible_multiple_flags_requires_approval(tier):
    result = decide_response_tier(flagged_detector_count=2, tool_tier=tier)
    assert result is ResponseTier.REQUIRE_APPROVAL


# --- Approval queue ---

def test_submit_and_get_roundtrip():
    queue = ApprovalQueue()
    request = queue.submit(session_id="s1", tool_name="send_payment", params={"amount": "10"})
    fetched = queue.get(request_id=request.request_id)
    assert fetched.outcome is ApprovalOutcome.PENDING


def test_unknown_request_raises():
    queue = ApprovalQueue()
    with pytest.raises(UnknownApprovalRequestError):
        queue.get(request_id="not-real")


def test_approve_records_active_decision():
    queue = ApprovalQueue()
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})
    decided = queue.decide(request_id=request.request_id, approved=True)
    assert decided.outcome is ApprovalOutcome.APPROVED
    assert decided.decided_at is not None


def test_deny_records_active_decision():
    queue = ApprovalQueue()
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})
    decided = queue.decide(request_id=request.request_id, approved=False)
    assert decided.outcome is ApprovalOutcome.DENIED


def test_deciding_twice_raises():
    queue = ApprovalQueue()
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})
    queue.decide(request_id=request.request_id, approved=True)
    with pytest.raises(ApprovalAlreadyDecidedError):
        queue.decide(request_id=request.request_id, approved=False)


def test_expires_after_timeout_via_fake_clock():
    clock = FakeClock()
    queue = ApprovalQueue(timeout_seconds=1800, clock=clock)  # 30 min
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})

    clock.advance(1000)  # not yet expired
    assert queue.get(request_id=request.request_id).outcome is ApprovalOutcome.PENDING

    clock.advance(1000)  # now past 1800s total
    expired = queue.get(request_id=request.request_id)
    assert expired.outcome is ApprovalOutcome.EXPIRED
    assert expired.decided_at is not None


def test_expired_is_distinct_from_denied():
    """
    Critical check per §13 v2: EXPIRED must never be conflated with an
    active DENIED decision — different enum values, checked explicitly.
    """
    clock = FakeClock()
    queue = ApprovalQueue(timeout_seconds=10, clock=clock)
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})
    clock.advance(20)
    expired = queue.get(request_id=request.request_id)
    assert expired.outcome is ApprovalOutcome.EXPIRED
    assert expired.outcome is not ApprovalOutcome.DENIED


def test_deciding_after_expiry_raises_not_overrides():
    """
    A human decision arriving after expiry must NOT retroactively
    un-expire the request — the expiry already happened and was
    already logged as such.
    """
    clock = FakeClock()
    queue = ApprovalQueue(timeout_seconds=10, clock=clock)
    request = queue.submit(session_id="s1", tool_name="send_payment", params={})
    clock.advance(20)
    queue.get(request_id=request.request_id)  # triggers expiry
    with pytest.raises(ApprovalAlreadyDecidedError):
        queue.decide(request_id=request.request_id, approved=True)
