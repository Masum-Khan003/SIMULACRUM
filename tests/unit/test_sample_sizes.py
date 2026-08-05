"""
Verifies §11's documented minimum sample sizes are real, enforced
floors (Palimpsest bug #16) — not advisory constants.
"""
import pytest

from simulacrum.evaluation import (
    MIN_CALIBRATION_SAMPLES,
    MIN_TRAINING_SESSIONS,
    InsufficientSampleSizeError,
    require_calibration_samples,
    require_training_sessions,
)


def test_below_calibration_minimum_raises():
    with pytest.raises(InsufficientSampleSizeError):
        require_calibration_samples(sample_count=MIN_CALIBRATION_SAMPLES - 1)


def test_at_calibration_minimum_succeeds():
    require_calibration_samples(sample_count=MIN_CALIBRATION_SAMPLES)


def test_above_calibration_minimum_succeeds():
    require_calibration_samples(sample_count=MIN_CALIBRATION_SAMPLES + 1000)


def test_below_training_minimum_raises():
    with pytest.raises(InsufficientSampleSizeError):
        require_training_sessions(session_count=MIN_TRAINING_SESSIONS - 1)


def test_at_training_minimum_succeeds():
    require_training_sessions(session_count=MIN_TRAINING_SESSIONS)


def test_the_bug_16_scenario_specifically_blocked():
    """~29 samples was the actual historical bug #16 count — must be
    blocked outright, not just 'less than the minimum' in the abstract."""
    with pytest.raises(InsufficientSampleSizeError):
        require_calibration_samples(sample_count=29)
