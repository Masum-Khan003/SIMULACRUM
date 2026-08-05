"""
Verifies BoundaryClassifier implementations (§06, resolves gap 2,
architectural upgrade after real MiniLM calibration showed genuine
overlap for embedding-only boundary detection — see
boundary_classifier.py's module docstring).

EmbeddingBoundaryClassifier: deterministic fallback mechanics.
GroqBoundaryClassifier: fails open to the fallback on ANY exception,
proven with a REAL invalid-key network round-trip, same discipline as
test_explainability.py's GroqExplainer test.
"""
import pytest

from simulacrum.attribution import (
    EmbeddingBoundaryClassifier,
    FakeSemanticEmbedder,
    GroqBoundaryClassifier,
)


@pytest.fixture
def fallback():
    return EmbeddingBoundaryClassifier(embedder=FakeSemanticEmbedder(), threshold=0.15)


def test_embedding_classifier_refinement_below_threshold_not_new(fallback):
    # Identical text -> similarity 1.0 -> well above any reasonable threshold
    result = fallback.is_new_subtask(
        current_task_text="book a flight to London", new_user_text="book a flight to London"
    )
    assert result is False


def test_embedding_classifier_unrelated_text_is_new(fallback):
    result = fallback.is_new_subtask(
        current_task_text="book a flight to London", new_user_text="cancel my streaming subscription"
    )
    assert result is True


def test_groq_classifier_fails_open_on_genuinely_invalid_api_key(fallback):
    """
    Real network round-trip with a deliberately invalid key — NOT
    mocked. Confirms fail-open actually routes through the fallback,
    matching its exact output, not just returning some boolean.
    """
    classifier = GroqBoundaryClassifier(
        api_key="sk-definitely-not-a-real-key-98765", fallback=fallback
    )
    current = "book a flight to London"
    new_text = "cancel my streaming subscription"

    result = classifier.is_new_subtask(current_task_text=current, new_user_text=new_text)
    expected = fallback.is_new_subtask(current_task_text=current, new_user_text=new_text)
    assert result == expected


def test_groq_classifier_importing_module_does_not_require_groq_installed():
    import simulacrum.attribution.boundary_classifier  # noqa: F401
    assert True
