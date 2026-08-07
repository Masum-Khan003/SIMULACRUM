"""
Verifies the event-driven version-change drift trigger (§17 v2).
"""
from simulacrum.drift.version_trigger import VersionTracker


def test_first_observation_is_not_a_change():
    tracker = VersionTracker()
    result = tracker.check_and_update(component="groq_model", current_version="llama-3.3-70b-versatile")
    assert result is False


def test_same_version_again_is_not_a_change():
    tracker = VersionTracker()
    tracker.check_and_update(component="groq_model", current_version="llama-3.3-70b-versatile")
    result = tracker.check_and_update(component="groq_model", current_version="llama-3.3-70b-versatile")
    assert result is False


def test_different_version_is_a_change():
    tracker = VersionTracker()
    tracker.check_and_update(component="groq_model", current_version="llama-3.3-70b-versatile")
    result = tracker.check_and_update(component="groq_model", current_version="llama-4.0-turbo")
    assert result is True


def test_components_tracked_independently():
    tracker = VersionTracker()
    tracker.check_and_update(component="groq_model", current_version="llama-3.3-70b-versatile")
    tracker.check_and_update(component="minilm_model", current_version="all-MiniLM-L6-v2")

    # Changing groq_model must not affect minilm_model's tracked state
    groq_changed = tracker.check_and_update(component="groq_model", current_version="llama-4.0")
    minilm_changed = tracker.check_and_update(component="minilm_model", current_version="all-MiniLM-L6-v2")

    assert groq_changed is True
    assert minilm_changed is False


def test_change_detected_only_once_then_stable():
    tracker = VersionTracker()
    tracker.check_and_update(component="groq_model", current_version="v1")
    first_change = tracker.check_and_update(component="groq_model", current_version="v2")
    second_check = tracker.check_and_update(component="groq_model", current_version="v2")

    assert first_change is True
    assert second_check is False  # v2 is now the established baseline, no new change
