"""
Real, multi-instance proof for RedisCircuitBreaker (§12 v2 gap 7,
Phase 3 §23): two independent instances sharing the same redis_url +
breaker_name must observe the SAME trip/recovery state, unlike the
in-memory CircuitBreaker's single-instance-only behavior.

Requires real Redis (SIMULACRUM_REDIS_URL) -- same dependency as
test_redis_session_store.py.
"""
import os
import time

import pytest

from simulacrum.interception.circuit_breaker import CircuitOpenError, CircuitState
from simulacrum.interception.redis_circuit_breaker import RedisCircuitBreaker

os.environ.setdefault("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def breaker_name():
    # Unique per test run to avoid real cross-test state bleed
    return f"test-breaker-{time.time_ns()}"


@pytest.fixture
def cleanup(breaker_name):
    yield
    client_url = os.environ["SIMULACRUM_REDIS_URL"]
    import redis as redis_lib
    client = redis_lib.Redis.from_url(client_url, decode_responses=True)
    client.delete(f"simulacrum:breaker:{breaker_name}:failure_count")
    client.delete(f"simulacrum:breaker:{breaker_name}:opened_at")


def test_initial_state_is_closed(breaker_name, cleanup):
    breaker = RedisCircuitBreaker(
        redis_url=os.environ["SIMULACRUM_REDIS_URL"], breaker_name=breaker_name
    )
    assert breaker.state is CircuitState.CLOSED


def test_trip_is_observed_by_a_separate_real_instance(breaker_name, cleanup):
    """
    THE real, load-bearing test: two SEPARATE RedisCircuitBreaker
    instances (simulating two replicas) sharing the same breaker_name
    must see the SAME state -- replica B must observe replica A's trip
    without ever calling the failing function itself.
    """
    redis_url = os.environ["SIMULACRUM_REDIS_URL"]
    replica_a = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name, failure_threshold=2
    )
    replica_b = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name, failure_threshold=2
    )

    def failing_fn():
        raise ValueError("simulated failure")

    for _ in range(2):
        with pytest.raises(ValueError):
            replica_a.call(failing_fn)

    assert replica_a.state is CircuitState.OPEN
    assert replica_b.state is CircuitState.OPEN

    with pytest.raises(CircuitOpenError):
        replica_b.call(lambda: pytest.fail("should never execute — circuit is open"))


def test_recovers_after_timeout_across_instances(breaker_name, cleanup):
    redis_url = os.environ["SIMULACRUM_REDIS_URL"]
    replica_a = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name,
        failure_threshold=1, recovery_timeout_seconds=0.5,
    )
    replica_b = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name,
        failure_threshold=1, recovery_timeout_seconds=0.5,
    )

    with pytest.raises(ValueError):
        replica_a.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
    assert replica_a.state is CircuitState.OPEN

    time.sleep(0.6)
    assert replica_a.state is CircuitState.CLOSED
    assert replica_b.state is CircuitState.CLOSED


def test_success_clears_failure_state_across_instances(breaker_name, cleanup):
    redis_url = os.environ["SIMULACRUM_REDIS_URL"]
    replica_a = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name, failure_threshold=3
    )
    replica_b = RedisCircuitBreaker(
        redis_url=redis_url, breaker_name=breaker_name, failure_threshold=3
    )

    with pytest.raises(ValueError):
        replica_a.call(lambda: (_ for _ in ()).throw(ValueError("fail")))

    result = replica_a.call(lambda: "success")
    assert result == "success"
    assert replica_a.state is CircuitState.CLOSED
    assert replica_b.state is CircuitState.CLOSED
