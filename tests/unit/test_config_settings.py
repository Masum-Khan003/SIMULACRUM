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
