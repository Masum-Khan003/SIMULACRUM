from simulacrum.attribution.call_text import call_topic_text
from simulacrum.attribution.embedding import (
    FakeSemanticEmbedder,
    FakeTaskEmbedder,
    TaskEmbedder,
    Vector,
    cosine_similarity,
)
from simulacrum.attribution.subtask import (
    DEFAULT_BOUNDARY_THRESHOLD,
    TaskRepresentation,
)

__all__ = [
    "DEFAULT_BOUNDARY_THRESHOLD",
    "FakeSemanticEmbedder",
    "FakeTaskEmbedder",
    "TaskEmbedder",
    "TaskRepresentation",
    "Vector",
    "call_topic_text",
    "cosine_similarity",
]

from simulacrum.attribution.real_embedder import MiniLMEmbedder

__all__.append("MiniLMEmbedder")

from simulacrum.attribution.boundary_classifier import (
    BoundaryClassifier,
    EmbeddingBoundaryClassifier,
    GroqBoundaryClassifier,
)

__all__ += ["BoundaryClassifier", "EmbeddingBoundaryClassifier", "GroqBoundaryClassifier"]

from simulacrum.attribution.goal_drift import (
    DriftDetector,
    DriftResult,
    GroqDriftDetector,
    NullDriftDetector,
)

__all__ += ["DriftDetector", "DriftResult", "GroqDriftDetector", "NullDriftDetector"]
