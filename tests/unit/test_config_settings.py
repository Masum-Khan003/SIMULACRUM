"""
Verifies the no-default-resource-URL guard (§00b, Palimpsest bug #1 /
finding 001). This is a hard requirement, not a nice-to-have — a
regression here means a future connection could silently default to a
live or unintended store.
"""
import os

import pytest

from simulacrum.config.settings import MissingConfigError, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings() is lru_cache'd; clear it so each test is isolated."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_missing_redis_url_raises(monkeypatch):
    monkeypatch.delenv("SIMULACRUM_REDIS_URL", raising=False)
    with pytest.raises(MissingConfigError, match="SIMULACRUM_REDIS_URL"):
        get_settings()


def test_empty_redis_url_raises(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "")
    with pytest.raises(MissingConfigError, match="SIMULACRUM_REDIS_URL"):
        get_settings()


def test_whitespace_only_redis_url_raises(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "   ")
    with pytest.raises(MissingConfigError, match="SIMULACRUM_REDIS_URL"):
        get_settings()


def test_valid_redis_url_succeeds(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    settings = get_settings()
    assert settings.redis_url == "redis://localhost:6379/0"


def test_settings_is_frozen(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    settings = get_settings()
    with pytest.raises(AttributeError):
        settings.redis_url = "redis://attacker-controlled:6379/0"


def test_settings_is_cached(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    first = get_settings()
    second = get_settings()
    assert first is second


def test_groq_api_key_defaults_to_none_when_unset(monkeypatch):
    """
    Deliberate exception to the no-default rule: groq_api_key is
    Optional[str] = None by design, since the explanation layer is
    OPTIONAL (§20) and its absence is valid configuration, not a
    misconfiguration — unlike redis_url.
    """
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    settings = get_settings()
    assert settings.groq_api_key is None


def test_groq_api_key_present_when_set(monkeypatch):
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GROQ_API_KEY", "some-real-key-value")
    settings = get_settings()
    assert settings.groq_api_key == "some-real-key-value"


def test_empty_groq_api_key_treated_as_none(monkeypatch):
    """Empty string should be treated the same as unset, not as a
    'blank but present' key — same discipline as redis_url's empty
    check, applied here for consistency even though it's optional."""
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("GROQ_API_KEY", "")
    settings = get_settings()
    assert settings.groq_api_key is None
