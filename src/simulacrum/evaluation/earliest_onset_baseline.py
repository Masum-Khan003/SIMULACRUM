"""
§10's third required baseline: "earliest-anomaly-onset baseline" --
genuinely ambiguous in the source blueprint (verified via direct text
search, docs/BACKLOG.md: the phrase appears exactly once, no further
specification exists anywhere in simulacrum-blueprint-v2.html).

Reasonable, stated interpretation (not assumed correct, flagged
honestly): does the TURN-INDEX of a trajectory's first flagged call
alone carry real predictive signal, without needing full-trajectory
aggregation (which is what Baseline A in explicit_detectors_baseline.py
already measures)? If attacks are flagged systematically earlier than
false positives, turn-index alone is a real, cheap, useful heuristic.
If the two distributions overlap heavily, that's an honest negative
result -- report it, don't dress it up.

Real, honest scope note on "turn-index": ExtractedToolCall (from real
AgentDojo trajectories) has no turn_index field -- only Simulacrum's
own ToolCall does. AgentDojo trajectories are strictly sequential in
their own JSON (no parallel-call structure), so this module uses tuple
POSITION as turn-index, stated explicitly rather than silently assumed
equivalent to Simulacrum's own richer turn_index concept.

Real, honest scope note on detectors used: same as
explicit_detectors_baseline.py -- only divergence and content-pattern
are tool-vocabulary-agnostic enough to score AgentDojo's tool set.
Reuses score_trajectory_divergence's existing per_call_similarities
(no new detector calls needed for divergence).
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskEmbedder
from simulacrum.detectors import MINILM_DIVERGENCE_THRESHOLD
from simulacrum.detectors.content_pattern import ContentPatternDetector
from simulacrum.generalization_set.agentdojo_adapter.adapter import ExtractedTrajectory
from simulacrum.generalization_set.agentdojo_adapter.scoring import score_trajectory_divergence


@dataclass(frozen=True)
class OnsetResult:
    onset_index: int | None  # None = never flagged by either detector
    call_count: int


@dataclass(frozen=True)
class OnsetDistributionSummary:
    n_flagged: int
    n_total: int
    mean_onset_index: float | None
    median_onset_index: float | None
    mean_onset_fraction: float | None  # onset_index / call_count, normalizes for trajectory length


def find_onset_index(
    *, trajectory: ExtractedTrajectory, embedder: TaskEmbedder, content_detector: ContentPatternDetector
) -> OnsetResult:
    """
    Real, honest note: uses tuple position as turn-index (see module
    docstring). Reuses score_trajectory_divergence's real
    per_call_similarities rather than re-scoring divergence separately.
    """
    div_result = score_trajectory_divergence(trajectory=trajectory, embedder=embedder)
    call_count = len(trajectory.tool_calls)

    for i, (call, similarity) in enumerate(zip(trajectory.tool_calls, div_result.per_call_similarities)):
        divergence_flag = similarity < MINILM_DIVERGENCE_THRESHOLD
        content_flag = content_detector.check_content(
            tool_name=call.tool_name, params=call.params
        ).is_suspicious
        if divergence_flag or content_flag:
            return OnsetResult(onset_index=i, call_count=call_count)

    return OnsetResult(onset_index=None, call_count=call_count)


def summarize_onsets(*, results: list[OnsetResult]) -> OnsetDistributionSummary:
    flagged = [r for r in results if r.onset_index is not None]
    n_flagged, n_total = len(flagged), len(results)

    if not flagged:
        return OnsetDistributionSummary(
            n_flagged=0, n_total=n_total,
            mean_onset_index=None, median_onset_index=None, mean_onset_fraction=None,
        )

    indices = sorted(r.onset_index for r in flagged)
    mean_idx = sum(indices) / len(indices)
    mid = len(indices) // 2
    median_idx = (
        indices[mid] if len(indices) % 2 == 1 else (indices[mid - 1] + indices[mid]) / 2
    )
    fractions = [r.onset_index / r.call_count for r in flagged if r.call_count > 0]
    mean_fraction = sum(fractions) / len(fractions) if fractions else None

    return OnsetDistributionSummary(
        n_flagged=n_flagged, n_total=n_total,
        mean_onset_index=mean_idx, median_onset_index=median_idx,
        mean_onset_fraction=mean_fraction,
    )


def _run_cli() -> None:
    import argparse
    import os

    from simulacrum.attribution import MiniLMEmbedder
    from simulacrum.detectors.content_pattern import (
        GroqContentPatternDetector,
        HeuristicContentPatternDetector,
    )
    from simulacrum.evaluation.explicit_detectors_baseline import build_sample

    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    api_key = os.environ["GROQ_API_KEY"]
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )

    attacks, resisted = build_sample(n=args.n, seed=args.seed)
    print(f"Sample: {len(attacks)} real attacks, {len(resisted)} real resisted trajectories")

    attack_results = [
        find_onset_index(trajectory=t, embedder=embedder, content_detector=content_detector)
        for t in attacks
    ]
    resisted_results = [
        find_onset_index(trajectory=t, embedder=embedder, content_detector=content_detector)
        for t in resisted
    ]

    attack_summary = summarize_onsets(results=attack_results)
    resisted_summary = summarize_onsets(results=resisted_results)

    print(f"\n=== Real attacks (n={attack_summary.n_total}) ===")
    print(f"Flagged: {attack_summary.n_flagged}/{attack_summary.n_total}")
    print(f"Mean onset index: {attack_summary.mean_onset_index}")
    print(f"Median onset index: {attack_summary.median_onset_index}")
    print(f"Mean onset fraction (position/length): {attack_summary.mean_onset_fraction}")

    print(f"\n=== Real resisted, but flagged = false positives (n={resisted_summary.n_total}) ===")
    print(f"Flagged: {resisted_summary.n_flagged}/{resisted_summary.n_total}")
    print(f"Mean onset index: {resisted_summary.mean_onset_index}")
    print(f"Median onset index: {resisted_summary.median_onset_index}")
    print(f"Mean onset fraction (position/length): {resisted_summary.mean_onset_fraction}")

    if attack_summary.mean_onset_fraction is not None and resisted_summary.mean_onset_fraction is not None:
        print(f"\n=== Delta (does onset position discriminate attacks from FPs?) ===")
        print(f"Mean onset fraction diff (attack - FP): "
              f"{attack_summary.mean_onset_fraction - resisted_summary.mean_onset_fraction:+.3f}")


if __name__ == "__main__":
    _run_cli()
