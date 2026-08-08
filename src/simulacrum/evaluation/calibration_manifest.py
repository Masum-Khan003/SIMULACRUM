"""
Feature-schema/calibration manifest (§11, Palimpsest bug #2 guard):
prevents a detector from silently scoring against a threshold that
doesn't match what was actually calibrated. Bug #2's real failure
mode: someone tweaks a threshold constant without re-running
calibration, and the detector keeps running against stale, unverified
assumptions with no warning.

Real, populated manifest below reflects THIS project's actual
calibration history (findings 005/008/010, docs/CALIBRATION_REPORT.md)
-- not placeholder data. verify_current_config() checks the manifest
against the ACTUAL currently-imported threshold constants, catching
drift between documented calibration and running configuration.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CalibrationEntry:
    detector_name: str
    threshold_name: str
    threshold_value: float
    embedder_or_method: str
    calibration_method: str
    sample_size: int
    measured_recall: float | None
    measured_false_positive_rate: float | None
    finding_reference: str


@dataclass(frozen=True)
class CalibrationManifest:
    entries: tuple[CalibrationEntry, ...]
    manifest_version: str

    def compute_hash(self) -> str:
        """
        Canonical hash of the manifest's calibration DATA (not
        metadata like docstrings) -- changes if any threshold value,
        sample size, or measured result changes, giving a real,
        checkable fingerprint of "what was actually calibrated."
        """
        canonical = json.dumps(
            [asdict(e) for e in self.entries], sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


class CalibrationDriftError(RuntimeError):
    """Raised when a currently-configured threshold does not match
    what the calibration manifest says was actually calibrated --
    exactly Palimpsest bug #2's failure mode, caught at verification
    time rather than silently ignored."""


# THE real, current calibration manifest -- reflects actual
# documented findings, not placeholder values. Update this manifest
# (and re-run real calibration work) whenever a threshold changes;
# verify_current_config() below will catch drift if it doesn't.
CURRENT_MANIFEST = CalibrationManifest(
    manifest_version="1.0",
    entries=(
        CalibrationEntry(
            detector_name="param_divergence",
            threshold_name="FAKE_DIVERGENCE_THRESHOLD",
            threshold_value=0.1581,
            embedder_or_method="FakeSemanticEmbedder (bag-of-words, dim=256)",
            calibration_method="1st-percentile derivation (finding 008 methodology), recalibrated (finding 014) against task_sim's variable-length corpus fix + call_topic_text ID-noise fix",
            sample_size=2730,
            measured_recall=1.0,
            measured_false_positive_rate=0.0,
            finding_reference="finding 005, finding 008, finding 010, finding 014 (variable-length recalibration, root-cause fix)",
        ),
        CalibrationEntry(
            detector_name="param_divergence",
            threshold_name="MINILM_DIVERGENCE_THRESHOLD",
            threshold_value=0.3307,
            embedder_or_method="MiniLMEmbedder (all-MiniLM-L6-v2)",
            calibration_method="1st-percentile derivation (finding 008, poisoning-resistant), recalibrated (finding 014) against task_sim's variable-length corpus fix + call_topic_text ID-noise fix",
            sample_size=2730,
            measured_recall=1.0,
            measured_false_positive_rate=0.0,
            finding_reference="finding 008, finding 010, finding 013, finding 014 (variable-length recalibration, root-cause fix for finding 010's generalization gap)",
        ),
        CalibrationEntry(
            detector_name="loop_rate",
            threshold_name="DEFAULT_RATE_THRESHOLD",
            threshold_value=7.0,
            embedder_or_method="N/A (integer count, not embedder-derived)",
            calibration_method="Evidence-based: one above the real max same-tool repeat count (6) measured across 2500 real task_sim-generated sessions, same 'safe margin above observed max' discipline as finding 008",
            sample_size=2500,
            measured_recall=None,
            measured_false_positive_rate=0.0,
            finding_reference="finding 014 (recalibrated from a Phase-1 placeholder of 3 after task_sim's variable-length fix made legitimate sessions repeat tools up to 6 times)",
        ),
        CalibrationEntry(
            detector_name="exfiltration",
            threshold_name="DEFAULT_CONTENT_SIZE_THRESHOLD",
            threshold_value=150.0,
            embedder_or_method="N/A (character count, not embedder-derived)",
            calibration_method="Fixed heuristic value, not corpus-calibrated",
            sample_size=0,
            measured_recall=None,
            measured_false_positive_rate=None,
            finding_reference="not applicable -- documented as crude from day one, closed by content_pattern detector (finding 007)",
        ),
        CalibrationEntry(
            detector_name="exfiltration",
            threshold_name="DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD",
            threshold_value=7.0,
            embedder_or_method="N/A (integer count, not embedder-derived)",
            calibration_method="Evidence-based: one above the real max legitimate outbound-tool call count (6) measured across 2500 real task_sim-generated sessions, same discipline as loop_rate's DEFAULT_RATE_THRESHOLD",
            sample_size=2500,
            measured_recall=None,
            measured_false_positive_rate=0.0,
            finding_reference="finding 014 (also a pre-existing manifest gap fixed here -- this threshold was never tracked in the manifest before this session)",
        ),
    ),
)


def verify_current_config() -> list[str]:
    """
    Real verification: imports the ACTUAL currently-configured
    threshold constants from the live codebase and compares them
    against the manifest. Returns a list of drift descriptions (empty
    if everything matches). Does NOT raise automatically -- callers
    decide whether drift is a hard failure (e.g. in CI) or a warning.
    """
    from simulacrum.detectors.exfiltration import (
        DEFAULT_CONTENT_SIZE_THRESHOLD,
        DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD,
    )
    from simulacrum.detectors.loop_rate import DEFAULT_RATE_THRESHOLD
    from simulacrum.detectors.param_divergence import (
        FAKE_DIVERGENCE_THRESHOLD,
        MINILM_DIVERGENCE_THRESHOLD,
    )

    live_values = {
        "FAKE_DIVERGENCE_THRESHOLD": FAKE_DIVERGENCE_THRESHOLD,
        "MINILM_DIVERGENCE_THRESHOLD": MINILM_DIVERGENCE_THRESHOLD,
        "DEFAULT_RATE_THRESHOLD": DEFAULT_RATE_THRESHOLD,
        "DEFAULT_CONTENT_SIZE_THRESHOLD": DEFAULT_CONTENT_SIZE_THRESHOLD,
        # Real gap closed (finding 014): this threshold existed in
        # production since exfiltration.py was written but was never
        # tracked in this manifest at all -- added now, not just
        # updated, while recalibrating it for real evidence-based
        # reasons.
        "DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD": DEFAULT_OUTBOUND_FREQUENCY_THRESHOLD,
    }

    drift = []
    for entry in CURRENT_MANIFEST.entries:
        live_value = live_values.get(entry.threshold_name)
        if live_value is None:
            drift.append(f"{entry.threshold_name}: manifest entry exists but no live constant found")
        elif live_value != entry.threshold_value:
            drift.append(
                f"{entry.threshold_name}: manifest says {entry.threshold_value}, "
                f"live code has {live_value} -- CALIBRATION DRIFT (Palimpsest bug #2)"
            )
    return drift
