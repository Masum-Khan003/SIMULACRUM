"""
Sub-task boundary detection (§06, resolves gap 2).

Real, found-and-fixed bug (this session): current_task_text was
previously overwritten on EVERY turn, including refinements — meaning
after a refinement, subsequent comparisons judged new turns against
the refinement text itself, not the actual ongoing task, causing
drift. Correct behavior: current_task_text should only change when a
NEW sub-task actually opens (per is_new_subtask's own verdict) —
refinements must NOT move the anchor. Caught via a real end-to-end
HTTP test showing a genuine new-task pivot incorrectly classified as
a refinement after a prior refinement turn.

TaskEmbedder/vector still updates every turn regardless (the
embedding-based fallback needs a "most recent text" reference point
for its own similarity comparison — but the LLM-facing
current_task_text anchor must stay stable across refinements).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simulacrum.attribution.boundary_classifier import BoundaryClassifier
from simulacrum.attribution.embedding import TaskEmbedder, Vector

DEFAULT_BOUNDARY_THRESHOLD = 0.15


@dataclass
class TaskRepresentation:
    embedder: TaskEmbedder
    current_vector: Vector
    current_task_text: str
    sub_task_index: int = 0
    history: list[Vector] = field(default_factory=list)

    @classmethod
    def start(cls, *, embedder: TaskEmbedder, initial_user_text: str) -> "TaskRepresentation":
        vector = embedder.embed(initial_user_text)
        return cls(
            embedder=embedder,
            current_vector=vector,
            current_task_text=initial_user_text,
            history=[vector],
        )

    def update_from_user_turn(
        self, *, user_text: str, boundary_classifier: BoundaryClassifier
    ) -> bool:
        """
        Process a new user turn (trusted channel).

        current_task_text is the STABLE anchor for what the ongoing
        task is about — it only advances to user_text when a NEW
        sub-task actually opens. A refinement turn updates
        current_vector (for embedding-based fallback comparisons) but
        deliberately leaves current_task_text unchanged, so the next
        turn is still judged against the real task, not the most
        recent refinement (the bug this docstring documents).
        """
        is_new_subtask = boundary_classifier.is_new_subtask(
            current_task_text=self.current_task_text, new_user_text=user_text
        )
        new_vector = self.embedder.embed(user_text)
        self.current_vector = new_vector
        self.history.append(new_vector)
        if is_new_subtask:
            self.sub_task_index += 1
            self.current_task_text = user_text
        return is_new_subtask
