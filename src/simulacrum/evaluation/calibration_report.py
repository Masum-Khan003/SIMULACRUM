"""
Formal confidence-calibration reporting (§05/§15): Brier score +
reliability diagram data, the standalone artifact this project's real
calibration work (percentile derivation, real similarity distributions
measured throughout findings 008/010) had evidence for but never
formalized into one deliverable.

Real, honest design note: Brier score requires a genuine PROBABILITY
estimate, not a binary threshold decision. This module treats
(1 - similarity) as a pseudo-probability-of-attack signal, derived
from the divergence detector's own real, continuous similarity score
-- a legitimate reuse of an existing signal, not an invented one.
Lower similarity (less related to the task) maps to higher estimated
attack probability.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationSample:
    predicted_probability: float  # in [0, 1]
    actual_outcome: bool  # True = real attack, False = real benign


@dataclass(frozen=True)
class ReliabilityBin:
    bin_range: tuple[float, float]
    mean_predicted_probability: float
    observed_frequency: float
    sample_count: int


@dataclass(frozen=True)
class CalibrationReport:
    brier_score: float
    reliability_bins: tuple[ReliabilityBin, ...]
    sample_count: int


def similarity_to_pseudo_probability(*, similarity: float) -> float:
    """
    Maps a real cosine-similarity score (typically in roughly [-1, 1]
    for real embeddings, though not strictly bounded) to a [0, 1]
    pseudo-probability of being an attack. Lower similarity -> higher
    attack probability. Clips to [0, 1] since raw similarity can fall
    outside that range.
    """
    prob = (1.0 - similarity) / 2.0
    return max(0.0, min(1.0, prob))


def compute_brier_score(*, samples: list[CalibrationSample]) -> float:
    """
    Brier score: mean squared error between predicted probability and
    actual binary outcome (0 or 1). Lower is better; 0 = perfect
    calibration, 0.25 = the score a coin-flip predictor gets on a
    balanced dataset, 1.0 = worst possible (confidently wrong every
    time).
    """
    if not samples:
        raise ValueError("Cannot compute Brier score on an empty sample set")
    total = sum(
        (s.predicted_probability - (1.0 if s.actual_outcome else 0.0)) ** 2 for s in samples
    )
    return total / len(samples)


def compute_reliability_bins(
    *, samples: list[CalibrationSample], n_bins: int = 10
) -> tuple[ReliabilityBin, ...]:
    """
    Bins samples by predicted probability into n_bins equal-width
    buckets across [0, 1], and for each bin reports the MEAN predicted
    probability vs. the OBSERVED frequency of actual attacks in that
    bin. A well-calibrated detector has these two numbers close
    together in every bin (predicted 70% attack probability should
    mean ~70% of samples in that bin are real attacks).
    """
    bins: list[list[CalibrationSample]] = [[] for _ in range(n_bins)]
    for s in samples:
        bin_idx = min(int(s.predicted_probability * n_bins), n_bins - 1)
        bins[bin_idx].append(s)

    results = []
    for i, bin_samples in enumerate(bins):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not bin_samples:
            results.append(
                ReliabilityBin(
                    bin_range=(lo, hi), mean_predicted_probability=0.0,
                    observed_frequency=0.0, sample_count=0,
                )
            )
            continue
        mean_pred = sum(s.predicted_probability for s in bin_samples) / len(bin_samples)
        observed = sum(1 for s in bin_samples if s.actual_outcome) / len(bin_samples)
        results.append(
            ReliabilityBin(
                bin_range=(lo, hi), mean_predicted_probability=mean_pred,
                observed_frequency=observed, sample_count=len(bin_samples),
            )
        )
    return tuple(results)


def generate_calibration_report(*, samples: list[CalibrationSample]) -> CalibrationReport:
    brier = compute_brier_score(samples=samples)
    bins = compute_reliability_bins(samples=samples)
    return CalibrationReport(brier_score=brier, reliability_bins=bins, sample_count=len(samples))
