"""
Param-vs-task semantic divergence detector (§09 per-call tier, §04's
primary signal for "prompt injection via tool output"). This is the
detector schema conformance structurally cannot replace: a call can be
perfectly well-formed (passes schema) while being completely unrelated
to what the user actually asked for.

Threshold is a placeholder pending real calibration against the
labeled corpus (§15) — same honesty discipline as the sub-task
boundary threshold.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskRepresentation, call_topic_text, cosine_similarity

DEFAULT_DIVERGENCE_THRESHOLD = 0.15


@dataclass(frozen=True)
class ParamDivergenceResult:
    tool_name: str
    similarity: float
    is_divergent: bool


def check_param_divergence(
    *,
    task_representation: TaskRepresentation,
    tool_name: str,
    params: dict[str, str],
    threshold: float = DEFAULT_DIVERGENCE_THRESHOLD,
) -> ParamDivergenceResult:
    call_text = call_topic_text(tool_name=tool_name, params=params)
    call_vector = task_representation.embedder.embed(call_text)
    similarity = cosine_similarity(call_vector, task_representation.current_vector)
    return ParamDivergenceResult(
        tool_name=tool_name,
        similarity=similarity,
        is_divergent=similarity < threshold,
    )
