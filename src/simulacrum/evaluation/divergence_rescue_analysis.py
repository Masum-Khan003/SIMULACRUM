"""
Follow-up to finding 010 (Priority 1, still open) and finding 011:
decomposes WHERE content-pattern's contribution to the Baseline-A OR
combination (divergence OR content-pattern, see
explicit_detectors_baseline.py) actually comes from. Real, honest
question: among the real attacks divergence alone MISSES (false
negatives), what fraction does content-pattern independently RESCUE?
And among real resisted trajectories divergence alone correctly
CLEARS, how many false positives does adding content-pattern
introduce that weren't already there?

This does not attempt a new fix for finding 010's generalization gap.
It measures, with real data, whether "lean on content-pattern more for
cases divergence structurally misses" (one of finding 010's stated
candidate directions, none yet attempted) is actually supported by
real rescue behavior, or whether content-pattern's OR-contribution is
mostly redundant/uncorrelated with divergence's specific blind spots.

Real, honest scope note: uses RAW min_similarity (the current,
reverted-to production metric, MINILM_DIVERGENCE_THRESHOLD=0.3030),
NOT the low-param-exclusion variant (finding 010's third investigation
found no safe joint configuration for that -- reverted from
production). This measurement is about the CURRENT production
divergence behavior, not a proposed replacement.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.attribution import TaskEmbedder
from simulacrum.detectors import MINILM_DIVERGENCE_THRESHOLD
from simulacrum.detectors.content_pattern import ContentPatternDetector
from simulacrum.generalization_set.agentdojo_adapter.adapter import ExtractedTrajectory
from simulacrum.generalization_set.agentdojo_adapter.scoring import score_trajectory_divergence


@dataclass(frozen=True)
class RescueAnalysisResult:
    n_attacks: int
    n_resisted: int
    divergence_recall: float
    divergence_fp_rate: float
    # Among real attacks divergence MISSES, fraction content-pattern rescues
    n_divergence_missed_attacks: int
    n_rescued_by_content_pattern: int
    rescue_rate: float | None
    # Among real resisted divergence correctly CLEARS, how many content-pattern
    # newly flags (the real, specific FP cost of adding content-pattern)
    n_divergence_cleared_resisted: int
    n_newly_flagged_by_content_pattern: int
    new_fp_rate_from_content_pattern: float | None


def _content_pattern_flags_any_call(
    *, trajectory: ExtractedTrajectory, content_detector: ContentPatternDetector
) -> bool:
    for call in trajectory.tool_calls:
        if content_detector.check_content(tool_name=call.tool_name, params=call.params).is_suspicious:
            return True
    return False


def run_rescue_analysis(
    *,
    attacks: list[ExtractedTrajectory],
    resisted: list[ExtractedTrajectory],
    embedder: TaskEmbedder,
    content_detector: ContentPatternDetector,
) -> RescueAnalysisResult:
    n_attacks, n_resisted = len(attacks), len(resisted)

    divergence_tp = 0
    missed_attacks = []
    for t in attacks:
        result = score_trajectory_divergence(trajectory=t, embedder=embedder)
        if result.min_similarity < MINILM_DIVERGENCE_THRESHOLD:
            divergence_tp += 1
        else:
            missed_attacks.append(t)

    divergence_fp = 0
    cleared_resisted = []
    for t in resisted:
        result = score_trajectory_divergence(trajectory=t, embedder=embedder)
        if result.min_similarity < MINILM_DIVERGENCE_THRESHOLD:
            divergence_fp += 1
        else:
            cleared_resisted.append(t)

    n_rescued = sum(
        1 for t in missed_attacks
        if _content_pattern_flags_any_call(trajectory=t, content_detector=content_detector)
    )
    n_newly_flagged = sum(
        1 for t in cleared_resisted
        if _content_pattern_flags_any_call(trajectory=t, content_detector=content_detector)
    )

    return RescueAnalysisResult(
        n_attacks=n_attacks,
        n_resisted=n_resisted,
        divergence_recall=divergence_tp / n_attacks,
        divergence_fp_rate=divergence_fp / n_resisted,
        n_divergence_missed_attacks=len(missed_attacks),
        n_rescued_by_content_pattern=n_rescued,
        rescue_rate=(n_rescued / len(missed_attacks)) if missed_attacks else None,
        n_divergence_cleared_resisted=len(cleared_resisted),
        n_newly_flagged_by_content_pattern=n_newly_flagged,
        new_fp_rate_from_content_pattern=(n_newly_flagged / len(cleared_resisted)) if cleared_resisted else None,
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

    result = run_rescue_analysis(
        attacks=attacks, resisted=resisted, embedder=embedder, content_detector=content_detector
    )

    print(f"\n=== Divergence alone (current production behavior) ===")
    print(f"Recall: {result.divergence_recall:.1%}")
    print(f"FP rate: {result.divergence_fp_rate:.1%}")

    print(f"\n=== Rescue analysis: does content-pattern catch divergence's misses? ===")
    print(f"Real attacks divergence misses: {result.n_divergence_missed_attacks}/{result.n_attacks}")
    print(f"Of those, rescued by content-pattern: {result.n_rescued_by_content_pattern}"
          f"/{result.n_divergence_missed_attacks} "
          f"({result.rescue_rate:.1%})" if result.rescue_rate is not None else " (n/a)")

    print(f"\n=== Cost analysis: how many NEW false positives does content-pattern add? ===")
    print(f"Real resisted divergence correctly clears: {result.n_divergence_cleared_resisted}/{result.n_resisted}")
    print(f"Of those, newly flagged by content-pattern: {result.n_newly_flagged_by_content_pattern}"
          f"/{result.n_divergence_cleared_resisted} "
          f"({result.new_fp_rate_from_content_pattern:.1%})" if result.new_fp_rate_from_content_pattern is not None else " (n/a)")


if __name__ == "__main__":
    _run_cli()
