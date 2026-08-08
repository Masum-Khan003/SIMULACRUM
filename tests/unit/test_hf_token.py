"""
Verifies HF_TOKEN configuration (§20 minor item): optional, follows
the same pattern as GROQ_API_KEY (absence is valid config, not
misconfiguration), threads through to SentenceTransformer for higher
Hugging Face Hub rate limits when present.
"""
import pytest


def test_hf_token_defaults_to_none_when_unset(monkeypatch):
    from simulacrum.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    settings = get_settings()
    assert settings.hf_token is None
    get_settings.cache_clear()


def test_hf_token_present_when_set(monkeypatch):
    from simulacrum.config.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SIMULACRUM_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HF_TOKEN", "hf_test_token_value")
    settings = get_settings()
    assert settings.hf_token == "hf_test_token_value"
    get_settings.cache_clear()


def test_minilm_embedder_accepts_hf_token_param():
    """
    Verifies the constructor signature accepts hf_token without
    requiring a real model download -- checks the parameter is
    genuinely accepted, not that authentication actually succeeds
    (that would require a real token and real network access).
    """
    pytest.importorskip("sentence_transformers")
    import inspect

    from simulacrum.attribution.real_embedder import MiniLMEmbedder

    sig = inspect.signature(MiniLMEmbedder.__init__)
    assert "hf_token" in sig.parameters
    assert sig.parameters["hf_token"].default is None
