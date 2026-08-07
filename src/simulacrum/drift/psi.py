"""
Population Stability Index (§17): scheduled statistical drift
detection on per-task-type feature distributions against the
calibration baseline. Direct reuse of Palimpsest's own PSI +
promotion-gate pattern, applied here to Simulacrum's detector
feature distributions (starting with param-vs-task divergence
similarity scores) instead of API traffic features.

PSI formula (standard): for each bin, PSI_bin = (actual% - expected%)
* ln(actual% / expected%), summed across all bins. Interpretation
(industry-standard thresholds): PSI < 0.1 = no significant shift,
0.1-0.25 = moderate shift (investigate), > 0.25 = significant shift
(real drift, recalibration likely needed).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


PSI_NO_SHIFT_THRESHOLD = 0.1
PSI_SIGNIFICANT_SHIFT_THRESHOLD = 0.25


class InsufficientDataForPSIError(RuntimeError):
    """Raised when either distribution has too few samples for a
    statistically meaningful PSI computation."""


MIN_SAMPLES_FOR_PSI = 30


@dataclass(frozen=True)
class PSIResult:
    psi_value: float
    is_significant_shift: bool
    is_moderate_shift: bool
    bin_edges: tuple[float, ...]


def _bin_distribution(values: list[float], bin_edges: list[float]) -> list[float]:
    """Returns the FRACTION of values falling in each bin (not raw
    counts), using bin_edges to define bin boundaries. Empty bins get
    a small floor value (not zero) since PSI's log term is undefined
    at zero -- standard practice, avoids a divide-by-zero/log(0)
    blowing up the whole computation from one sparse bin."""
    n_bins = len(bin_edges) - 1
    counts = [0] * n_bins
    for v in values:
        for i in range(n_bins):
            lo, hi = bin_edges[i], bin_edges[i + 1]
            is_last_bin = i == n_bins - 1
            if lo <= v < hi or (is_last_bin and v == hi):
                counts[i] += 1
                break
    total = len(values)
    floor = 0.0001  # avoids log(0) for empty bins
    return [max(c / total, floor) for c in counts]


def compute_psi(
    *, baseline_values: list[float], current_values: list[float], n_bins: int = 10
) -> PSIResult:
    """
    Computes PSI between a baseline (calibration-time) distribution
    and a current (live) distribution of the same feature. Bin edges
    are derived from the BASELINE's own range, split into n_bins
    equal-width bins -- current values outside that range fall into
    the nearest edge bin (standard PSI handling for out-of-range
    drift, which is itself a signal of real shift).
    """
    if len(baseline_values) < MIN_SAMPLES_FOR_PSI or len(current_values) < MIN_SAMPLES_FOR_PSI:
        raise InsufficientDataForPSIError(
            f"PSI requires at least {MIN_SAMPLES_FOR_PSI} samples per distribution; "
            f"got baseline={len(baseline_values)}, current={len(current_values)}."
        )

    lo, hi = min(baseline_values), max(baseline_values)
    if lo == hi:
        # Degenerate baseline (all identical values) -- widen slightly
        # so bin edges are well-defined rather than dividing by zero.
        lo -= 0.01
        hi += 0.01
    bin_width = (hi - lo) / n_bins
    bin_edges = [lo + i * bin_width for i in range(n_bins + 1)]

    # Clip current values into the baseline's bin range for binning
    # purposes (values genuinely outside range land in the nearest
    # edge bin -- this IS the drift signal, not something to discard).
    clipped_current = [max(lo, min(hi, v)) for v in current_values]

    baseline_dist = _bin_distribution(baseline_values, bin_edges)
    current_dist = _bin_distribution(clipped_current, bin_edges)

    psi = sum(
        (curr - base) * math.log(curr / base)
        for base, curr in zip(baseline_dist, current_dist)
    )

    return PSIResult(
        psi_value=psi,
        is_significant_shift=psi > PSI_SIGNIFICANT_SHIFT_THRESHOLD,
        is_moderate_shift=PSI_NO_SHIFT_THRESHOLD < psi <= PSI_SIGNIFICANT_SHIFT_THRESHOLD,
        bin_edges=tuple(bin_edges),
    )
