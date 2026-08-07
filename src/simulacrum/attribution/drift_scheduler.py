"""
Real async/background drift scheduler (§03/§12: "runs off-path, async,
on a rolling interval," caching "a standing per-session risk decision
in the session store"). Closes the real gap flagged in docs/BACKLOG.md
-- prior to this, only an on-demand synchronous endpoint existed.

Deliberately scoped: a single-process asyncio background task, NOT a
heavyweight external scheduler (Celery, etc.) -- matches §12's own
stated single-instance MVP scope. Tracks "calls since last drift
check" per session, triggers via the already-tested
should_check_drift() rule, caches the last result as a standing
decision retrievable without re-running an expensive LLM call every
time.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from simulacrum.attribution.drift_trigger import DEFAULT_DRIFT_CHECK_INTERVAL, should_check_drift
from simulacrum.attribution.goal_drift import DriftDetector, DriftResult


@dataclass(frozen=True)
class StandingDriftDecision:
    result: DriftResult
    checked_at_call_count: int


@dataclass
class DriftScheduler:
    """
    Real, testable background scheduler. run_once() performs a single
    scan pass over all tracked sessions -- exposed separately from the
    actual asyncio loop (start/stop) so tests can call run_once()
    directly without needing real sleep-based timing.
    """
    drift_detector: DriftDetector
    poll_interval_seconds: float = 30.0
    check_interval_calls: int = DEFAULT_DRIFT_CHECK_INTERVAL

    _last_checked_call_count: dict[str, int] = field(default_factory=dict)
    _standing_decisions: dict[str, StandingDriftDecision] = field(default_factory=dict)
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)

    def get_standing_decision(self, *, session_id: str) -> StandingDriftDecision | None:
        return self._standing_decisions.get(session_id)

    def run_once(
        self,
        *,
        session_id: str,
        task_description: str,
        call_history: tuple[str, ...],
    ) -> StandingDriftDecision | None:
        """
        Checks ONE session: if enough new calls have happened since
        the last check (per should_check_drift's tested rule), runs
        the real drift detector and caches a new standing decision.
        Returns the (possibly unchanged) standing decision, or None if
        this session has never been checked and doesn't yet meet the
        trigger threshold.
        """
        last_checked = self._last_checked_call_count.get(session_id, 0)
        calls_since_last = len(call_history) - last_checked

        if not should_check_drift(calls_since_last_check=calls_since_last, interval=self.check_interval_calls):
            return self._standing_decisions.get(session_id)

        result = self.drift_detector.check_drift(
            task_description=task_description, call_history=call_history
        )
        decision = StandingDriftDecision(result=result, checked_at_call_count=len(call_history))
        self._standing_decisions[session_id] = decision
        self._last_checked_call_count[session_id] = len(call_history)
        return decision

    async def start(self, *, get_active_sessions) -> None:
        """
        Starts the real background asyncio loop. get_active_sessions is
        a callable returning an iterable of (session_id, task_description,
        call_history) tuples for every currently-active session --
        injected rather than hardcoded so this scheduler has no direct
        dependency on AppState's specific shape.
        """
        async def _loop():
            while True:
                for session_id, task_description, call_history in get_active_sessions():
                    self.run_once(
                        session_id=session_id, task_description=task_description, call_history=call_history
                    )
                await asyncio.sleep(self.poll_interval_seconds)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
