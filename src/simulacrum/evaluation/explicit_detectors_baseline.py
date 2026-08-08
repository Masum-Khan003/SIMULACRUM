"""
§10 required baseline: "explicit-detectors-only baseline" (does the
LLM-based goal-drift detector earn its real cost/complexity over the
explicit detectors alone?), against real AgentDojo external data
(§08 Layer 4). Found not-yet-built via docs/BACKLOG.md re-audit.

Real, honest scoping correction: only param-vs-task divergence and
content-pattern are tool-vocabulary-agnostic enough to score
AgentDojo's tool set at all -- schema/permission-escalation/loop-rate/
exfiltration are keyed to Simulacrum's own tool names and baselines
and structurally cannot evaluate AgentDojo's different tools (see
agentdojo_adapter/adapter.py's own scope docstring, same real
limitation CALIBRATION_REPORT.md's system-level section already
documents). So "explicit-detectors-only baseline" concretely means:

  Baseline A (explicit only):      divergence OR content-pattern
  Baseline B (explicit + drift):   A OR goal-drift

Comparing A vs B answers §10's real question for THIS external
dataset: does GroqDriftDetector (the accepted §10 substitute for a
literal trajectory sequence model, per docs/decisions/001-*.md) earn
its real added cost/latency over the explicit detector set alone.

Real gap this module also fixes: no runnable script existed anywhere
for the sampling/scoring methodology CALIBRATION_REPORT.md's numbers
were generated with -- violates this project's own "every claim
backed by a runnable script" rule. This is that script.
"""
from __future__ import annotations

import argparse
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path

from simulacrum.attribution import MiniLMEmbedder
from simulacrum.attribution.goal_drift import GroqDriftDetector, NullDriftDetector
from simulacrum.detectors import MINILM_DIVERGENCE_THRESHOLD
from simulacrum.detectors.content_pattern import (
    GroqContentPatternDetector,
    HeuristicContentPatternDetector,
)
from simulacrum.generalization_set.agentdojo_adapter.adapter import (
    ExtractedTrajectory,
    load_all_trajectories,
)
from simulacrum.generalization_set.agentdojo_adapter.scoring import score_trajectory_divergence

RUNS_DIR = Path("./runs")


@dataclass(frozen=True)
class TrajectoryFlags:
    explicit_flag: bool  # Baseline A: divergence OR content-pattern
    with_drift_flag: bool  # Baseline B: A OR goal-drift


@dataclass(frozen=True)
class BaselineComparisonResult:
    n_attacks: int
    n_resisted: int
    recall_explicit: float
    recall_with_drift: float
    fp_rate_explicit: float
    fp_rate_with_drift: float
    elapsed_seconds: float


def _call_text(tool_name: str, params: dict[str, str]) -> str:
    param_text = " ".join(f"{k}={v}" for k, v in params.items())
    return f"{tool_name}({param_text})"


def build_sample(
    *, n: int, seed: int, runs_dir: Path = RUNS_DIR
) -> tuple[list[ExtractedTrajectory], list[ExtractedTrajectory]]:
    """Real, seeded sample from real AgentDojo data -- same seeded-rng
    convention used throughout this project's task_sim/attack_suite
    (random.Random(seed), never global random state)."""
    trajectories = load_all_trajectories(runs_dir=runs_dir)
    succeeded = [t for t in trajectories if t.attack_succeeded is True and t.tool_calls]
    resisted = [t for t in trajectories if t.attack_succeeded is False and t.tool_calls]

    rng = random.Random(seed)
    half = n // 2
    sample_attacks = rng.sample(succeeded, min(half, len(succeeded)))
    sample_resisted = rng.sample(resisted, min(half, len(resisted)))
    return sample_attacks, sample_resisted


def score_trajectory(
    *, trajectory: ExtractedTrajectory, embedder, content_detector, drift_detector
) -> TrajectoryFlags:
    div_result = score_trajectory_divergence(trajectory=trajectory, embedder=embedder)
    divergence_flag = div_result.min_similarity < MINILM_DIVERGENCE_THRESHOLD

    content_flag = False
    for call in trajectory.tool_calls:
        result = content_detector.check_content(tool_name=call.tool_name, params=call.params)
        if result.is_suspicious:
            content_flag = True
            break

    explicit_flag = divergence_flag or content_flag

    call_history = tuple(_call_text(c.tool_name, c.params) for c in trajectory.tool_calls)
    drift_result = drift_detector.check_drift(
        task_description=trajectory.user_instruction, call_history=call_history
    )
    with_drift_flag = explicit_flag or drift_result.is_drifted

    return TrajectoryFlags(explicit_flag=explicit_flag, with_drift_flag=with_drift_flag)


def run_baseline(
    *,
    attacks: list[ExtractedTrajectory],
    resisted: list[ExtractedTrajectory],
    embedder,
    content_detector,
    drift_detector,
) -> BaselineComparisonResult:
    """Real, importable, testable entry point -- same pattern as
    input_only_baseline.py's InputOnlyClassifier and
    task_completion_report.py's run_task_completion_report."""
    start = time.time()
    tp_explicit = tp_with_drift = 0
    fp_explicit = fp_with_drift = 0

    for t in attacks:
        flags = score_trajectory(
            trajectory=t, embedder=embedder,
            content_detector=content_detector, drift_detector=drift_detector,
        )
        tp_explicit += flags.explicit_flag
        tp_with_drift += flags.with_drift_flag

    for t in resisted:
        flags = score_trajectory(
            trajectory=t, embedder=embedder,
            content_detector=content_detector, drift_detector=drift_detector,
        )
        fp_explicit += flags.explicit_flag
        fp_with_drift += flags.with_drift_flag

    elapsed = time.time() - start
    n_attacks, n_resisted = len(attacks), len(resisted)

    return BaselineComparisonResult(
        n_attacks=n_attacks,
        n_resisted=n_resisted,
        recall_explicit=tp_explicit / n_attacks,
        recall_with_drift=tp_with_drift / n_attacks,
        fp_rate_explicit=fp_explicit / n_resisted,
        fp_rate_with_drift=fp_with_drift / n_resisted,
        elapsed_seconds=elapsed,
    )


def _print_report(result: BaselineComparisonResult) -> None:
    total = result.n_attacks + result.n_resisted
    print(f"Sample: {result.n_attacks} real attacks, {result.n_resisted} real resisted trajectories")
    print(f"\nElapsed: {result.elapsed_seconds:.1f}s for {total} trajectories "
          f"({result.elapsed_seconds / total:.2f}s/trajectory avg)")

    print(f"\n=== Baseline A: explicit detectors only (divergence OR content-pattern) ===")
    print(f"Recall: {result.recall_explicit:.1%}")
    print(f"FP rate: {result.fp_rate_explicit:.1%}")

    print(f"\n=== Baseline B: explicit detectors + goal-drift ===")
    print(f"Recall: {result.recall_with_drift:.1%}")
    print(f"FP rate: {result.fp_rate_with_drift:.1%}")

    print(f"\n=== Delta (does goal-drift earn its cost?) ===")
    print(f"Recall lift: {result.recall_with_drift - result.recall_explicit:+.1%}")
    print(f"FP cost: {result.fp_rate_with_drift - result.fp_rate_explicit:+.1%}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    api_key = os.environ["GROQ_API_KEY"]
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )
    drift_detector = GroqDriftDetector(api_key=api_key, fallback=NullDriftDetector())

    attacks, resisted = build_sample(n=args.n, seed=args.seed)
    result = run_baseline(
        attacks=attacks, resisted=resisted, embedder=embedder,
        content_detector=content_detector, drift_detector=drift_detector,
    )
    _print_report(result)


if __name__ == "__main__":
    main()
