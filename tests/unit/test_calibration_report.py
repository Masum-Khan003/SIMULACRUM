"""
Verifies formal confidence-calibration reporting (§05/§15): Brier
score and reliability-diagram computation.
"""
import pytest

from simulacrum.evaluation.calibration_report import (
    CalibrationSample,
    compute_brier_score,
    compute_reliability_bins,
    generate_calibration_report,
    similarity_to_pseudo_probability,
)


def test_similarity_to_probability_mapping():
    assert similarity_to_pseudo_probability(similarity=1.0) == 0.0  # perfectly on-topic -> 0% attack
    assert similarity_to_pseudo_probability(similarity=-1.0) == 1.0  # perfectly off-topic -> 100% attack
    assert similarity_to_pseudo_probability(similarity=0.0) == 0.5


def test_similarity_to_probability_clips_out_of_range():
    assert similarity_to_pseudo_probability(similarity=1.5) == 0.0
    assert similarity_to_pseudo_probability(similarity=-1.5) == 1.0


def test_perfect_predictions_give_zero_brier_score():
    samples = [
        CalibrationSample(predicted_probability=1.0, actual_outcome=True),
        CalibrationSample(predicted_probability=0.0, actual_outcome=False),
    ]
    assert compute_brier_score(samples=samples) == 0.0


def test_worst_predictions_give_brier_score_of_one():
    samples = [
        CalibrationSample(predicted_probability=0.0, actual_outcome=True),
        CalibrationSample(predicted_probability=1.0, actual_outcome=False),
    ]
    assert compute_brier_score(samples=samples) == 1.0


def test_coin_flip_predictor_gives_quarter_brier_score():
    samples = [
        CalibrationSample(predicted_probability=0.5, actual_outcome=True),
        CalibrationSample(predicted_probability=0.5, actual_outcome=False),
    ]
    assert compute_brier_score(samples=samples) == pytest.approx(0.25)


def test_empty_samples_raises():
    with pytest.raises(ValueError):
        compute_brier_score(samples=[])


def test_reliability_bins_perfectly_calibrated_case():
    """
    Samples where predicted probability genuinely matches observed
    frequency in each bin -- a real, well-calibrated case.
    """
    samples = (
        [CalibrationSample(predicted_probability=0.9, actual_outcome=True) for _ in range(9)]
        + [CalibrationSample(predicted_probability=0.9, actual_outcome=False) for _ in range(1)]
    )
    bins = compute_reliability_bins(samples=samples, n_bins=10)
    bin_90 = bins[9]  # the [0.9, 1.0) bin
    assert bin_90.sample_count == 10
    assert bin_90.observed_frequency == pytest.approx(0.9)
    assert bin_90.mean_predicted_probability == pytest.approx(0.9)


def test_generate_full_report():
    samples = [
        CalibrationSample(predicted_probability=0.8, actual_outcome=True),
        CalibrationSample(predicted_probability=0.2, actual_outcome=False),
    ]
    report = generate_calibration_report(samples=samples)
    assert report.sample_count == 2
    assert 0 <= report.brier_score <= 1
    assert len(report.reliability_bins) == 10


def test_content_pattern_confidence_conversion_suspicious_case():
    from simulacrum.evaluation.calibration_report import content_pattern_confidence_to_probability

    prob = content_pattern_confidence_to_probability(is_suspicious=True, confidence=0.9)
    assert prob == 0.9


def test_content_pattern_confidence_conversion_normal_case():
    from simulacrum.evaluation.calibration_report import content_pattern_confidence_to_probability

    # 95% confident it's NORMAL -> 5% probability of attack, NOT 95%
    prob = content_pattern_confidence_to_probability(is_suspicious=False, confidence=0.95)
    assert prob == pytest.approx(0.05)


def test_content_pattern_confidence_conversion_none_stays_none():
    from simulacrum.evaluation.calibration_report import content_pattern_confidence_to_probability

    assert content_pattern_confidence_to_probability(is_suspicious=True, confidence=None) is None
