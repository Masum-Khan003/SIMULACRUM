"""
Drift-check trigger logic (§03/§12: "runs off-path, async, on a
rolling interval" — NOT per-call like the other 5 detectors).

This module is deliberately scoped to just the TRIGGER decision
("should a drift check run now, given how many calls have happened
since the last one") — decoupled from actual scheduling mechanism.
True async/background scheduling (a scheduler process, standing
per-session cached risk decision per §12) is separate, larger
infrastructure NOT built in this step — see docs/BACKLOG.md. What IS
built: an honest, synchronous, on-demand trigger usable today via a
real API endpoint, with the interval RULE itself fully real and
tested, ready to be wired into real async scheduling later without
changing this logic.
"""
from __future__ import annotations

DEFAULT_DRIFT_CHECK_INTERVAL = 3  # calls between drift checks


def should_check_drift(*, calls_since_last_check: int, interval: int = DEFAULT_DRIFT_CHECK_INTERVAL) -> bool:
    """
    True once at least `interval` calls have happened since the last
    check. Kept as a pure function (no session-store dependency) so
    it's trivially testable and reusable regardless of what eventually
    schedules calls to it (a rolling interval job, an on-demand
    endpoint, etc.).
    """
    return calls_since_last_check >= interval
