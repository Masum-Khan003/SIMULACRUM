"""
Event-driven drift trigger (§17 v2, resolves gap 6): a model/version
change fires an IMMEDIATE recalibration run, independent of and
faster than PSI's scheduled statistical check. A real version bump
can shift agent/detector behavior in a single deployment, not
gradually -- waiting for PSI to notice would leave a stale, mismatched
baseline live in the meantime.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VersionTracker:
    """
    Tracks the currently-configured model identifier strings (e.g.
    Groq model name, MiniLM model name) that detectors depend on.
    Real, explicit input per §17's own language ("tracked as a
    configured, explicit input") -- not auto-detected from the API,
    since the actual model string is a deployment configuration
    decision, not something to infer.
    """
    tracked_versions: dict[str, str] = field(default_factory=dict)

    def check_and_update(self, *, component: str, current_version: str) -> bool:
        """
        Compares current_version against the last known version for
        this component. Returns True if this is a genuine CHANGE
        (triggering immediate recalibration), False if unchanged or
        this is the first time this component has been seen (a first
        observation is not a "change" -- there's nothing to have
        drifted FROM yet).
        """
        previous = self.tracked_versions.get(component)
        self.tracked_versions[component] = current_version
        if previous is None:
            return False  # first observation, not a change
        return previous != current_version
