"""
Verifies CircuitBreaker (§12): trips after failure_threshold
consecutive failures, short-circuits (raises CircuitOpenError WITHOUT
calling fn) while open, recovers after recovery_timeout via an
injectable fake clock (no real sleeping), resets failure count on
success.
"""
import pytest

from simulacrum.interception.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _failing():
    raise RuntimeError("boom")


def test_starts_closed():
    breaker = CircuitBreaker()
    assert breaker.state is CircuitState.CLOSED


def test_successful_call_passes_through():
    breaker = CircuitBreaker()
    result = breaker.call(lambda: 42)
    assert result == 42
    assert breaker.state is CircuitState.CLOSED


def test_failure_below_threshold_stays_closed():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            breaker.call(_failing)
    assert breaker.state is CircuitState.CLOSED


def test_failure_at_threshold_trips_open():
    breaker = CircuitBreaker(failure_threshold=3)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            breaker.call(_failing)
    assert breaker.state is CircuitState.OPEN


def test_open_circuit_short_circuits_without_calling_fn():
    breaker = CircuitBreaker(failure_threshold=1)
    with pytest.raises(RuntimeError):
        breaker.call(_failing)
    assert breaker.state is CircuitState.OPEN

    call_count = 0
    def tracked_fn():
        nonlocal call_count
        call_count += 1
        return "should not run"

    with pytest.raises(CircuitOpenError):
        breaker.call(tracked_fn)
    assert call_count == 0  # fn was never actually invoked


def test_recovers_after_timeout_via_fake_clock():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30.0, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_failing)
    assert breaker.state is CircuitState.OPEN

    clock.advance(10.0)  # not enough time yet
    assert breaker.state is CircuitState.OPEN

    clock.advance(25.0)  # now past 30s total
    assert breaker.state is CircuitState.CLOSED


def test_successful_call_after_recovery_resets_failure_count():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=10.0, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_failing)
    clock.advance(15.0)
    result = breaker.call(lambda: "ok")
    assert result == "ok"
    assert breaker.state is CircuitState.CLOSED

    # confirm failure count actually reset, not just state — one more
    # failure alone should NOT immediately re-trip at threshold=2
    with pytest.raises(RuntimeError):
        breaker.call(_failing)
    assert breaker.state is CircuitState.CLOSED
