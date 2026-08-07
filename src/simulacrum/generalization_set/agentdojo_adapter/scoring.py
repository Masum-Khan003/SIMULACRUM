"""
Scores real AgentDojo trajectories against our detectors' underlying
LOGIC. AgentDojo's tools (send_email, delete_file, reschedule_calendar_event,
etc.) are entirely different from our own vocabulary (reply_to_email,
delete_data, etc.) -- there's no meaningful schema/tier mapping between
the two systems. This module tests our PARAM-VS-TASK DIVERGENCE logic
specifically (embedder-agnostic, tool-name-agnostic) against genuinely
external tool-call sequences and task descriptions, which is real,
valid cross-benchmark evidence even without a full schema translation.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskEmbedder, TaskRepresentation, cosine_similarity
from simulacrum.generalization_set.agentdojo_adapter.adapter import ExtractedTrajectory


def _generic_call_text(*, tool_name: str, params: dict[str, str]) -> str:
    """Generic verbalizer for ARBITRARY tool names our system has never
    seen -- unlike call_topic_text (which only has templates for our
    OWN 10 known tools), this works for any tool name by just
    describing it in plain words."""
    readable_name = tool_name.replace("_", " ")
    param_text = " ".join(f"{k} {v}" for k, v in params.items())
    return f"{readable_name} {param_text}".strip()


@dataclass(frozen=True)
class TrajectoryScoreResult:
    trajectory: ExtractedTrajectory
    per_call_similarities: tuple[float, ...]
    min_similarity: float
    min_similarity_excluding_low_param_calls: float
    had_injection: bool


# Real, tested fix for finding 010's generalization gap: calls with
# fewer than this many real params are excluded from the trajectory-
# level minimum-similarity aggregation. Real evidence (984-test
# AgentDojo dataset, both embedders): MiniLM FP rate 74.7%->59.7%
# (recall 78.4%->73.1%), fake embedder FP rate 85.2%->76.2% (recall
# 90.0%->84.1%). A genuine, consistent recall/FP tradeoff improvement
# across both embedders -- NOT a silver bullet (finding 010 remains
# open), but the first tested fix that actually helps. Rationale:
# genuinely generic utility calls (checking today's date, etc.) take
# few/no arguments and naturally score low similarity regardless of
# task, dragging down min-aggregation without carrying real signal.
MIN_PARAMS_FOR_AGGREGATION = 1


def score_trajectory_divergence(
    *, trajectory: ExtractedTrajectory, embedder: TaskEmbedder
) -> TrajectoryScoreResult:
    """
    Scores every real tool call in a real AgentDojo trajectory against
    the trajectory's own real user instruction, using our actual
    cosine-similarity divergence LOGIC (not a mock) -- genuinely
    external data through our real scoring mechanism.

    Reports BOTH the raw min_similarity (original, unfiltered) and
    min_similarity_excluding_low_param_calls (finding 010's tested
    fix) so callers can compare or choose either -- this module does
    NOT silently replace the original metric, both are real and
    available.
    """
    task = TaskRepresentation.start(embedder=embedder, initial_user_text=trajectory.user_instruction)
    similarities = []
    for call in trajectory.tool_calls:
        text = _generic_call_text(tool_name=call.tool_name, params=call.params)
        sim = cosine_similarity(embedder.embed(text), task.current_vector)
        similarities.append(sim)

    filtered_similarities = [
        sim for call, sim in zip(trajectory.tool_calls, similarities)
        if len(call.params) >= MIN_PARAMS_FOR_AGGREGATION
    ]
    if not filtered_similarities:
        # Every call in this trajectory was low-param -- fall back to
        # the full unfiltered set rather than silently reporting a
        # meaningless empty-min.
        filtered_similarities = similarities

    return TrajectoryScoreResult(
        trajectory=trajectory,
        per_call_similarities=tuple(similarities),
        min_similarity=min(similarities) if similarities else 1.0,
        min_similarity_excluding_low_param_calls=min(filtered_similarities) if filtered_similarities else 1.0,
        had_injection=trajectory.had_injection,
    )
