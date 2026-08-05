"""
Circuit breaker (§12): wraps the detector-scoring path. If scoring
fails, fallback behavior is NOT uniform — it's decided per tool risk
tier (§07), the single largest architectural departure from
Palimpsest's own breaker, which failed open universally.

Scope, stated honestly: this is ONE breaker wrapping the FULL
detector-scoring path as a unit, not five independent per-detector
breakers. A per-detector breaker would let one broken detector fail
while others keep scoring; this coarser version trips on ANY scoring
failure. Documented simplification, not a silent shortcut — revisit
if per-detector granularity proves necessary (see docs/BACKLOG.md).

Single-instance, in-memory state only (§12's own stated MVP scope) —
shared/Redis-backed breaker state for multi-replica deployment is
Phase 3, per §23.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"  # normal operation
    OPEN = "open"  # tripped, calls short-circuit until recovery_timeout elapses


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and recovery_timeout hasn't elapsed."""


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic)

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            if self.clock() - self._opened_at >= self.recovery_timeout_seconds:
                return CircuitState.CLOSED  # half-open: allow a trial call through
        return self._state

    def call(self, fn: Callable[[], T]) -> T:
        """
        Executes fn if the circuit is closed (or half-open past
        recovery timeout). Raises CircuitOpenError immediately,
        WITHOUT calling fn, if still open. On success, resets failure
        count. On exception from fn, increments failure count, trips
        to OPEN at failure_threshold, and re-raises the original
        exception (callers decide fallback behavior; the breaker's
        job is only to stop calling a broken dependency, not to hide
        the failure).
        """
        if self.state is CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit is open (failed {self._failure_count} times); "
                f"short-circuiting without calling the wrapped function."
            )
        try:
            result = fn()
        except Exception:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self.clock()
            raise
        else:
            self._failure_count = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            return result
