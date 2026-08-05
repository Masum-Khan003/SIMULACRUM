"""
Verifies drift-check trigger logic (§03/§12: rolling-interval rule,
decoupled from actual scheduling mechanism).
"""
import pytest

from simulacrum.attribution import DEFAULT_DRIFT_CHECK_INTERVAL, should_check_drift


def test_below_interval_does_not_trigger():
    assert should_check_drift(calls_since_last_check=DEFAULT_DRIFT_CHECK_INTERVAL - 1) is False


def test_at_interval_triggers():
    assert should_check_drift(calls_since_last_check=DEFAULT_DRIFT_CHECK_INTERVAL) is True


def test_above_interval_triggers():
    assert should_check_drift(calls_since_last_check=DEFAULT_DRIFT_CHECK_INTERVAL + 5) is True


def test_zero_calls_does_not_trigger():
    assert should_check_drift(calls_since_last_check=0) is False


def test_custom_interval_respected():
    assert should_check_drift(calls_since_last_check=1, interval=1) is True
    assert should_check_drift(calls_since_last_check=0, interval=1) is False
