"""
Sub-task boundary classification (§06, resolves gap 2) — upgraded from
pure embedding cosine-similarity after real MiniLM calibration showed
the signal is genuinely weaker for this task than for param-vs-task
divergence (see chat/commit history: multiple real calibration
attempts, up to 240 samples, longer/contextual phrasing — all showed
~0.12 similarity gap with real overlap between refinement and
new-task categories, not a sampling artifact).

Root cause: judging "is this a new task or a refinement?" from two
short utterances is a REASONING task (does this relate to the ongoing
goal, pragmatically and semantically), not a pure SIMILARITY task —
unlike divergence, which compares a concrete tool-call description
against a task description with a much clearer conceptual anchor.

Two implementations, same fail-open pattern as Explainer/GroqExplainer:
  - GroqBoundaryClassifier: real LLM reasoning via Groq, PRIMARY
    mechanism. Fails open to EmbeddingBoundaryClassifier on ANY
    exception.
  - EmbeddingBoundaryClassifier: the original cosine-similarity
    approach, kept as the deterministic FALLBACK — degraded but
    always available, never requires network access.
"""
from __future__ import annotations

from typing import Protocol

from simulacrum.attribution.embedding import TaskEmbedder, cosine_similarity


class BoundaryClassifier(Protocol):
    def is_new_subtask(self, *, current_task_text: str, new_user_text: str) -> bool: ...


class EmbeddingBoundaryClassifier:
    """
    Deterministic, network-free fallback. Pure cosine similarity
    against a calibrated threshold — the ORIGINAL approach, demoted
    from primary to fallback given its real, measured limitations for
    this specific task (see module docstring).
    """

    def __init__(self, *, embedder: TaskEmbedder, threshold: float) -> None:
        self._embedder = embedder
        self._threshold = threshold

    def is_new_subtask(self, *, current_task_text: str, new_user_text: str) -> bool:
        current_vector = self._embedder.embed(current_task_text)
        new_vector = self._embedder.embed(new_user_text)
        similarity = cosine_similarity(current_vector, new_vector)
        return similarity < self._threshold


class GroqBoundaryClassifier:
    """
    Real LLM reasoning via Groq — PRIMARY mechanism. Fails open to a
    provided EmbeddingBoundaryClassifier on ANY exception (bad key,
    network failure, rate limit, malformed response), same discipline
    as GroqExplainer.
    """

    def __init__(
        self, *, api_key: str, fallback: EmbeddingBoundaryClassifier,
        model: str = "llama-3.3-70b-versatile",
    ) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model
        self._fallback = fallback

    def is_new_subtask(self, *, current_task_text: str, new_user_text: str) -> bool:
        try:
            prompt = (
                f"An AI agent is working on a task for a user. The task so far, "
                f"based on what the user has said: \"{current_task_text}\"\n\n"
                f"The user just said: \"{new_user_text}\"\n\n"
                f"Is this new statement a REFINEMENT or continuation of the "
                f"SAME task (e.g. adding detail, correcting something, "
                f"clarifying preferences), or does it introduce a GENUINELY "
                f"DIFFERENT, unrelated task?\n\n"
                f"Respond with EXACTLY one word: REFINEMENT or NEW_TASK."
            )
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0,
                timeout=5,
            )
            answer = response.choices[0].message.content.strip().upper()
            if "NEW_TASK" in answer:
                return True
            if "REFINEMENT" in answer:
                return False
            # Malformed/unexpected response — don't guess, fall back.
            raise ValueError(f"Unexpected classifier response: {answer!r}")
        except Exception:
            return self._fallback.is_new_subtask(
                current_task_text=current_task_text, new_user_text=new_user_text
            )
