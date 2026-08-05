"""
Sub-task boundary detection (§06, resolves gap 2).

A new sub-task boundary opens whenever a user turn introduces an
instruction that does not derive from (is not similar enough to) the
current task representation. Reuses the same embedding/similarity
mechanism as divergence scoring (§09) rather than a separate rule.

Task representation is updated ONLY on trusted-channel input (user
turns) — never by tool-output content, even when superficially phrased
as an instruction. This is the provenance-trust rule from §06 applied
directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from simulacrum.attribution.embedding import TaskEmbedder, Vector, cosine_similarity

# Below this similarity, a new user turn is considered a new sub-task
# rather than a refinement of the current one. Placeholder threshold —
# real calibration against the labeled corpus happens in Phase 1 (§15);
# this default exists so the logic is exercisable now, not tuned yet.
DEFAULT_BOUNDARY_THRESHOLD = 0.5


@dataclass
class TaskRepresentation:
    """
    Mutable, evolving embedding of 'the current task'. Updated only via
    update_from_user_turn() — there is deliberately NO method to update
    it from tool-output content. That omission is the enforcement
    mechanism for §06's provenance-trust rule, not a convention.
    """
    embedder: TaskEmbedder
    current_vector: Vector
    sub_task_index: int = 0
    boundary_threshold: float = DEFAULT_BOUNDARY_THRESHOLD
    history: list[Vector] = field(default_factory=list)

    @classmethod
    def start(
        cls, *, embedder: TaskEmbedder, initial_user_text: str,
        boundary_threshold: float = DEFAULT_BOUNDARY_THRESHOLD,
    ) -> "TaskRepresentation":
        vector = embedder.embed(initial_user_text)
        return cls(
            embedder=embedder,
            current_vector=vector,
            boundary_threshold=boundary_threshold,
            history=[vector],
        )

    def update_from_user_turn(self, *, user_text: str) -> bool:
        """
        Process a new user turn (trusted channel). Returns True if this
        turn opened a NEW sub-task boundary, False if it's a refinement
        of the current task.

        Deliberately takes only user_text — there is no parameter or
        code path here that accepts tool-output content, per §06.
        """
        new_vector = self.embedder.embed(user_text)
        similarity = cosine_similarity(self.current_vector, new_vector)
        is_new_subtask = similarity < self.boundary_threshold
        if is_new_subtask:
            self.sub_task_index += 1
        self.current_vector = new_vector
        self.history.append(new_vector)
        return is_new_subtask
