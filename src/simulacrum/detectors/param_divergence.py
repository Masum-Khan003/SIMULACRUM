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

# Two SEPARATE calibrated thresholds — NOT one shared constant.
# FakeSemanticEmbedder (bag-of-words) and MiniLM (real semantic
# embeddings) produce fundamentally different similarity
# DISTRIBUTIONS, not just different absolute numbers on the same
# scale. Forcing one threshold to serve both is a real bug (found
# empirically: raising the shared threshold to fit MiniLM's real
# calibration broke legitimate FakeSemanticEmbedder-based calls that
# scored as low as 0.177 on-topic) — each embedder needs its OWN
# calibrated threshold.
#
# FAKE_DIVERGENCE_THRESHOLD: calibrated against FakeSemanticEmbedder
# at dim=256 (finding 005's fix) — legitimate on-topic calls
# measured similarity as low as ~0.18 in practice; kept at the
# original 0.15 placeholder, which has real headroom below the
# lowest observed on-topic score.
#
# MINILM_DIVERGENCE_THRESHOLD: calibrated against REAL MiniLM
# embeddings (§15): on-topic 0.30-0.71 (mean 0.51, n=120), off-topic
# -0.03-0.15 (mean 0.04, n=240), zero overlap. 0.20 sits with real
# margin on both sides of that measured gap.
#
# check_param_divergence's default remains FAKE_DIVERGENCE_THRESHOLD
# since FakeSemanticEmbedder is still this project's DEFAULT
# embedder (real MiniLM is opt-in per docs/BACKLOG.md) — callers using
# MiniLM must pass MINILM_DIVERGENCE_THRESHOLD explicitly.
FAKE_DIVERGENCE_THRESHOLD = 0.15
MINILM_DIVERGENCE_THRESHOLD = 0.20
DEFAULT_DIVERGENCE_THRESHOLD = FAKE_DIVERGENCE_THRESHOLD


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
