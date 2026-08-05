"""
Task-representation embedding interface (§06/§09).

TaskEmbedder is a Protocol, not a base class, so the real embedder
(MiniLM-class sentence-transformer, wired in Phase 1 alongside the
divergence detector) only needs to match this shape — no inheritance
coupling between the interface and a heavy ML dependency we don't
need yet.

FakeTaskEmbedder below is deterministic and dependency-free, used to
prove the sub-task boundary LOGIC is correct independent of embedding
quality. Swapping in real MiniLM later changes similarity fidelity,
not this module's logic.
"""
from __future__ import annotations

import hashlib
from typing import Protocol


Vector = tuple[float, ...]


class TaskEmbedder(Protocol):
    def embed(self, text: str) -> Vector: ...


class FakeTaskEmbedder:
    """
    Deterministic, dependency-free stand-in for a real embedder.
    Same text -> same vector, always.

    Components are mapped to [-1.0, 1.0] (zero-centered), NOT [0.0, 1.0].
    An all-positive vector space gives structurally inflated cosine
    similarity for ANY two random vectors (no negative components to
    cancel out) — that inflation made unrelated text falsely score as
    similar. Zero-centering fixes this: unrelated random vectors now
    average toward similarity ~0, as intended for testing boundary logic.

    Still NOT semantically meaningful (it's SHA256-hash-derived, not
    NLP) — paraphrases will not show high similarity the way real
    MiniLM would. Good enough for boundary-logic tests only.
    """

    def embed(self, text: str) -> Vector:
        digest = hashlib.sha256(text.strip().lower().encode()).digest()
        return tuple((b / 255.0) * 2.0 - 1.0 for b in digest[:8])


def cosine_similarity(a: Vector, b: Vector) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
