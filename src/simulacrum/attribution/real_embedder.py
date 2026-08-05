"""
Real embedding model (§12/§20 gap 10): a sentence-transformer in the
MiniLM class, CPU inference, chosen specifically for no external API
dependency on the core detection path (unlike the explanation layer,
which explicitly IS allowed an external dependency per §20, because
it's optional and fails open).

Implements the exact same TaskEmbedder protocol as FakeTaskEmbedder/
FakeSemanticEmbedder — this is the whole point of building it as a
Protocol back in Phase 0: swapping in the real thing requires zero
changes to TaskRepresentation, check_param_divergence, or anything
else that consumes an embedder.

Heavier dependency (sentence-transformers -> torch) than anything
else in this project — kept as an optional extra, not a core
dependency, since most of the test suite doesn't need real semantic
understanding to prove LOGIC is correct (that's exactly what the fake
embedders are for).
"""
from __future__ import annotations

from simulacrum.attribution.embedding import Vector


class MiniLMEmbedder:
    """
    Lazy-imports sentence_transformers so importing THIS MODULE never
    requires torch to be installed — only constructing a MiniLMEmbedder
    does. Same lazy-import discipline as GroqExplainer.
    """

    def __init__(self, *, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> Vector:
        vector = self._model.encode(text, convert_to_numpy=True)
        return tuple(float(x) for x in vector)
