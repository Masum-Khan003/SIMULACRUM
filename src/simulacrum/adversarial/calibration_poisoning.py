"""
Calibration-poisoning test (§16, third named adversarial test),
SCOPED to what's actually testable today. Real, honestly-stated
limitation: this project has no automated re-baselining PIPELINE
(no scheduled recalibration job exists yet -- see docs/BACKLOG.md).
What DOES exist, and what this test targets, is the real calibration
METHODOLOGY used throughout this session (measure on-topic vs.
off-topic similarity samples, pick a threshold with margin above the
off-topic max) -- the exact approach used to derive
MINILM_DIVERGENCE_THRESHOLD. This test asks: if an attacker manages
to get some deliberately borderline sessions labeled as legitimate
"normal" calibration data (e.g. a compromised review process, a few
genuinely ambiguous sessions mislabeled), does RE-DERIVING a
threshold using our real methodology against the poisoned set produce
a threshold that's measurably easier to evade than the clean one?

This validates the METHODOLOGY's poisoning vulnerability, not a live
automated pipeline's vulnerability (which doesn't exist yet).
"""
from __future__ import annotations

from dataclasses import dataclass


def derive_threshold_min_margin(*, on_topic_similarities: list[float], margin: float = 0.05) -> float:
    """
    The ACTUAL methodology used this session for MINILM_DIVERGENCE_THRESHOLD:
    threshold = min(on-topic samples) - margin. Real, reusable, not a
    toy -- this is genuinely how we calibrated the real threshold in
    production.
    """
    return min(on_topic_similarities) - margin


@dataclass(frozen=True)
class PoisoningTestResult:
    clean_threshold: float
    poisoned_threshold: float
    attack_similarities: list[float]
    caught_by_clean: int
    caught_by_poisoned: int

    @property
    def poisoning_reduced_detection(self) -> bool:
        return self.caught_by_poisoned < self.caught_by_clean

    @property
    def threshold_shift(self) -> float:
        return self.poisoned_threshold - self.clean_threshold


def run_calibration_poisoning_test(
    *,
    clean_on_topic_similarities: list[float],
    poisoned_on_topic_similarities: list[float],
    attack_similarities: list[float],
    margin: float = 0.05,
) -> PoisoningTestResult:
    """
    clean_on_topic_similarities: real, honestly-labeled normal-session
    similarity scores (what calibration SHOULD use).
    poisoned_on_topic_similarities: clean samples PLUS attacker-
    injected borderline sessions mislabeled as normal.
    attack_similarities: real attack-call similarity scores, to check
    detection before/after poisoning.
    """
    clean_threshold = derive_threshold_min_margin(
        on_topic_similarities=clean_on_topic_similarities, margin=margin
    )
    poisoned_threshold = derive_threshold_min_margin(
        on_topic_similarities=poisoned_on_topic_similarities, margin=margin
    )

    caught_by_clean = sum(1 for s in attack_similarities if s < clean_threshold)
    caught_by_poisoned = sum(1 for s in attack_similarities if s < poisoned_threshold)

    return PoisoningTestResult(
        clean_threshold=clean_threshold,
        poisoned_threshold=poisoned_threshold,
        attack_similarities=attack_similarities,
        caught_by_clean=caught_by_clean,
        caught_by_poisoned=caught_by_poisoned,
    )

def derive_threshold_percentile(*, on_topic_similarities: list[float], percentile: float = 5.0) -> float:
    """
    MITIGATION for the min-margin vulnerability found in this module'''s
    own poisoning test: a percentile-based threshold is structurally
    robust to a SMALL number of poisoned/outlier samples, since it is
    not determined by any single minimum value. Requires a genuinely
    large calibration sample (MIN_CALIBRATION_SAMPLES) for the
    percentile itself to be meaningful and resistant to a few bad
    samples shifting it — same discipline as every other threshold
    in this project.

    NOT yet wired into production thresholds (FAKE_DIVERGENCE_THRESHOLD,
    MINILM_DIVERGENCE_THRESHOLD are still min-margin-derived) — this
    is the RECOMMENDED replacement methodology, documented and tested
    here, adoption tracked in docs/BACKLOG.md as real follow-up work
    requiring a full recalibration pass, not a one-line swap.
    """
    sorted_samples = sorted(on_topic_similarities)
    index = max(0, int(len(sorted_samples) * (percentile / 100.0)) - 1)
    return sorted_samples[index]
