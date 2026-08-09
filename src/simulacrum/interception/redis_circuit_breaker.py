"""
Multi-instance circuit-breaker state (§12 v2 gap 7, Phase 3 per §23):
a real, Redis-backed CircuitBreaker so multiple interception-layer
replicas observe the SAME open/closed state, instead of each replica
tripping independently (§12's own documented MVP limitation).

Same real pattern as session/redis_store.py: raw redis client (no
wrapper), required-keyword redis_url with no default (§00b/finding
001's standing rule), explicit key namespacing.

Atomicity note: failure-count increment uses Redis INCR (atomic at
the server level) so concurrent replicas incrementing simultaneously
never lose an update to a race -- the same class of correctness
requirement Palimpsest's own circuit breaker work established for
shared counters.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

import redis

from simulacrum.interception.circuit_breaker import CircuitOpenError, CircuitState

T = TypeVar("T")

_KEY_PREFIX = "simulacrum:breaker"


class CircuitBreakerProtocol(Protocol):
    """
    Real, structural interface both CircuitBreaker (in-memory,
    single-instance) and RedisCircuitBreaker (multi-instance) satisfy
    -- same discipline as SessionStore's protocol/InMemory/Redis split.
    intercept_and_call() is typed against this protocol, not a
    concrete class, so either implementation is a genuine drop-in.
    """

    @property
    def state(self) -> CircuitState: ...
    def call(self, fn: Callable[[], T]) -> T: ...


def _failure_count_key(breaker_name: str) -> str:
    return f"{_KEY_PREFIX}:{breaker_name}:failure_count"


def _opened_at_key(breaker_name: str) -> str:
    return f"{_KEY_PREFIX}:{breaker_name}:opened_at"


@dataclass
class RedisCircuitBreaker:
    redis_url: str  # required, keyword-only via dataclass field, no default
    breaker_name: str  # distinguishes multiple real breakers sharing one Redis instance
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    clock: Callable[[], float] = time.time  # real wall-clock, NOT monotonic --
    # opened_at is stored in Redis and read back by OTHER real processes/
    # replicas, so it must be comparable across process boundaries;
    # time.monotonic() is only valid within a single process, unlike the
    # in-memory CircuitBreaker where monotonic is correct and preferred.

    def __post_init__(self) -> None:
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)

    @property
    def state(self) -> CircuitState:
        opened_at_raw = self._client.get(_opened_at_key(self.breaker_name))
        if opened_at_raw is None:
            return CircuitState.CLOSED
        opened_at = float(opened_at_raw)
        if self.clock() - opened_at >= self.recovery_timeout_seconds:
            return CircuitState.CLOSED  # half-open: allow a trial call through
        return CircuitState.OPEN

    def call(self, fn: Callable[[], T]) -> T:
        """
        Real, multi-instance-safe version of CircuitBreaker.call(): any
        replica sharing this redis_url + breaker_name observes the SAME
        trip/recovery state. Failure count uses atomic INCR so
        concurrent replica failures never race-lose an increment.
        """
        if self.state is CircuitState.OPEN:
            failure_count = self._client.get(_failure_count_key(self.breaker_name))
            raise CircuitOpenError(
                f"Circuit '{self.breaker_name}' is open (failed "
                f"{failure_count or '?'} times across replicas); "
                f"short-circuiting without calling the wrapped function."
            )
        try:
            result = fn()
        except Exception:
            new_count = self._client.incr(_failure_count_key(self.breaker_name))
            if new_count >= self.failure_threshold:
                self._client.set(_opened_at_key(self.breaker_name), str(self.clock()))
            raise
        else:
            self._client.delete(_failure_count_key(self.breaker_name))
            self._client.delete(_opened_at_key(self.breaker_name))
            return result
