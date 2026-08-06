"""
Verifies §16's calibration-poisoning test, SCOPED to our actual
threshold-derivation methodology (min-margin) rather than a live
automated recalibration pipeline (which doesn't exist yet — see
calibration_poisoning.py's module docstring for the honest scope
statement).

REAL, significant finding from this session: a SINGLE poisoned sample
is sufficient to fully degrade detection (5/6 -> 3/6 real attacks
caught) using our actual measured calibration data. Adding MORE
poisoned samples beyond the first made zero additional difference —
because min-margin calibration is entirely determined by the single
lowest sample. This is a structural weakness of the min() statistic
itself, not a volume-dependent attack. Documented as a real finding,
not silently accepted.
"""
from simulacrum.adversarial.calibration_poisoning import derive_threshold_min_margin, run_calibration_poisoning_test

# Real data from this session's actual MiniLM calibration measurement
# and finding 007's real attack similarity scores.
CLEAN_ON_TOPIC = [0.30, 0.35, 0.42, 0.51, 0.38, 0.44, 0.60, 0.71, 0.33, 0.48]
REAL_ATTACK_SIMILARITIES = [0.0001, -0.0481, 0.0052, 0.1432, 0.1532, 0.2685]


def test_single_poisoned_sample_meaningfully_degrades_detection():
    """
    THE real finding: ONE poisoned sample is enough to reduce
    detection from 5/6 to 3/6 real attacks, because min-margin
    calibration is fully determined by the single lowest sample.
    This test documents the CURRENT vulnerable behavior explicitly.
    """
    poisoned = CLEAN_ON_TOPIC + [0.19]  # one borderline-low sample
    result = run_calibration_poisoning_test(
        clean_on_topic_similarities=CLEAN_ON_TOPIC,
        poisoned_on_topic_similarities=poisoned,
        attack_similarities=REAL_ATTACK_SIMILARITIES,
    )
    assert result.poisoning_reduced_detection is True
    assert result.caught_by_clean == 5
    assert result.caught_by_poisoned == 3, (
        "If this changes, min-margin calibration's sensitivity to a single "
        "poisoned sample may have shifted — verify before treating as fixed."
    )


def test_additional_poisoned_samples_beyond_first_add_no_further_damage():
    """
    Confirms the STRUCTURAL nature of the weakness: min() is
    determined by the single lowest value, so 1 vs 4 poisoned samples
    produce IDENTICAL degradation — not a dose-response relationship.
    """
    result_1 = run_calibration_poisoning_test(
        clean_on_topic_similarities=CLEAN_ON_TOPIC,
        poisoned_on_topic_similarities=CLEAN_ON_TOPIC + [0.19],
        attack_similarities=REAL_ATTACK_SIMILARITIES,
    )
    result_4 = run_calibration_poisoning_test(
        clean_on_topic_similarities=CLEAN_ON_TOPIC,
        poisoned_on_topic_similarities=CLEAN_ON_TOPIC + [0.22, 0.19, 0.25, 0.21],
        attack_similarities=REAL_ATTACK_SIMILARITIES,
    )
    assert result_1.poisoned_threshold == result_4.poisoned_threshold
    assert result_1.caught_by_poisoned == result_4.caught_by_poisoned


def test_clean_calibration_baseline_catches_most_real_attacks():
    """Sanity check: the CLEAN (unpoisoned) threshold should catch
    most real attacks, confirming the degradation is real and
    specifically caused by poisoning, not a broken baseline."""
    result = run_calibration_poisoning_test(
        clean_on_topic_similarities=CLEAN_ON_TOPIC,
        poisoned_on_topic_similarities=CLEAN_ON_TOPIC,  # no poisoning
        attack_similarities=REAL_ATTACK_SIMILARITIES,
    )
    assert result.caught_by_clean == 5
    assert result.poisoning_reduced_detection is False


def test_percentile_calibration_far_more_robust_than_min_margin_at_realistic_scale():
    """
    THE mitigation validation: at a REALISTIC calibration sample size
    (n=200, meeting MIN_CALIBRATION_SAMPLES), min-margin still shifts
    the full amount from ONE poisoned sample (confirming the flaw is
    structural, not a small-sample artifact) -- while 5th-percentile
    shifts by ~80x less. This is real, measured evidence the proposed
    mitigation works, not just a plausible theory.
    """
    import random

    from simulacrum.adversarial.calibration_poisoning import derive_threshold_percentile

    rng = random.Random(42)
    realistic_clean = [max(0.30, min(0.71, rng.gauss(0.51, 0.10))) for _ in range(200)]
    poisoned = realistic_clean + [0.19]

    min_clean = derive_threshold_min_margin(on_topic_similarities=realistic_clean)
    min_poisoned = derive_threshold_min_margin(on_topic_similarities=poisoned)
    min_shift = abs(min_poisoned - min_clean)

    pct_clean = derive_threshold_percentile(on_topic_similarities=realistic_clean)
    pct_poisoned = derive_threshold_percentile(on_topic_similarities=poisoned)
    pct_shift = abs(pct_poisoned - pct_clean)

    assert pct_shift < min_shift, (
        f"Percentile calibration should shift LESS than min-margin under poisoning: "
        f"percentile_shift={pct_shift}, min_margin_shift={min_shift}"
    )
    # Real measured ratio from this session: ~80x more resistant.
    # Asserting a conservative 10x floor so the test isn't brittle to
    # the exact random seed while still proving MEANINGFUL improvement.
    assert min_shift / pct_shift > 10, (
        f"Expected percentile calibration to be at least 10x more resistant, "
        f"got ratio={min_shift / pct_shift:.1f}x"
    )
