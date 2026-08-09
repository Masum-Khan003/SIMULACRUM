"""
§10 clean-isolation experiment: InputOnlyClassifier vs
ContextAwareClassifier, same model/prompt-shape/verdict-format,
differing ONLY in whether real task description + call history are
provided. Isolates session-awareness as a variable, unlike the
original input-only-vs-divergence comparison (finding 010 CALIBRATION
_REPORT section), which conflated context-availability with
reasoning-sophistication.

For each real AgentDojo trajectory, evaluates the SAME target call
(the attack call for real attacks; the lowest-divergence-similarity
call for resisted trajectories, matching finding 010's own methodology
for identifying which call "drives" a flag) under both classifiers.
"""
from __future__ import annotations

from dataclasses import dataclass

from simulacrum.evaluation.context_aware_baseline import ContextAwareClassifier
from simulacrum.evaluation.input_only_baseline import InputOnlyClassifier
from simulacrum.generalization_set.agentdojo_adapter.adapter import ExtractedTrajectory


def _call_text(tool_name: str, params: dict[str, str]) -> str:
    param_text = " ".join(f"{k}={v}" for k, v in params.items())
    return f"{tool_name}({param_text})"


@dataclass(frozen=True)
class ContextIsolationResult:
    n_attacks: int
    n_resisted: int
    input_only_recall: float
    context_aware_recall: float
    input_only_fp_rate: float
    context_aware_fp_rate: float


def _target_call_index(*, trajectory: ExtractedTrajectory, is_attack: bool) -> int:
    """
    For real attacks: the attack call itself doesn't have an explicit
    index in ExtractedTrajectory (unlike our own LabeledAttackSession),
    so uses the LAST call -- AgentDojo injection payloads are
    typically appended/near the end of a real trajectory, consistent
    with how our own attack_suite structures injected calls.
    For resisted trajectories: no single "attack call" exists by
    definition (the injection didn't succeed) -- uses the last call
    as a real, consistent target for both groups, matching what a
    real-time interceptor would evaluate as it goes.
    """
    return len(trajectory.tool_calls) - 1


def run_context_isolation_comparison(
    *,
    attacks: list[ExtractedTrajectory],
    resisted: list[ExtractedTrajectory],
    input_only: InputOnlyClassifier,
    context_aware: ContextAwareClassifier,
) -> ContextIsolationResult:
    n_attacks, n_resisted = len(attacks), len(resisted)

    io_tp = ca_tp = 0
    for t in attacks:
        idx = _target_call_index(trajectory=t, is_attack=True)
        call = t.tool_calls[idx]
        history = tuple(_call_text(c.tool_name, c.params) for c in t.tool_calls[:idx])

        io_result = input_only.classify(tool_name=call.tool_name, params=call.params)
        ca_result = context_aware.classify(
            task_description=t.user_instruction, call_history=history,
            tool_name=call.tool_name, params=call.params,
        )
        io_tp += io_result.is_flagged
        ca_tp += ca_result.is_flagged

    io_fp = ca_fp = 0
    for t in resisted:
        idx = _target_call_index(trajectory=t, is_attack=False)
        call = t.tool_calls[idx]
        history = tuple(_call_text(c.tool_name, c.params) for c in t.tool_calls[:idx])

        io_result = input_only.classify(tool_name=call.tool_name, params=call.params)
        ca_result = context_aware.classify(
            task_description=t.user_instruction, call_history=history,
            tool_name=call.tool_name, params=call.params,
        )
        io_fp += io_result.is_flagged
        ca_fp += ca_result.is_flagged

    return ContextIsolationResult(
        n_attacks=n_attacks,
        n_resisted=n_resisted,
        input_only_recall=io_tp / n_attacks,
        context_aware_recall=ca_tp / n_attacks,
        input_only_fp_rate=io_fp / n_resisted,
        context_aware_fp_rate=ca_fp / n_resisted,
    )


def _run_cli() -> None:
    import argparse
    import os

    from simulacrum.evaluation.explicit_detectors_baseline import build_sample

    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    api_key = os.environ["GROQ_API_KEY"]
    input_only = InputOnlyClassifier(api_key=api_key)
    context_aware = ContextAwareClassifier(api_key=api_key)

    attacks, resisted = build_sample(n=args.n, seed=args.seed)
    print(f"Sample: {len(attacks)} real attacks, {len(resisted)} real resisted trajectories")

    result = run_context_isolation_comparison(
        attacks=attacks, resisted=resisted, input_only=input_only, context_aware=context_aware
    )

    print(f"\n=== Input-only (no context) ===")
    print(f"Recall: {result.input_only_recall:.1%}")
    print(f"FP rate: {result.input_only_fp_rate:.1%}")

    print(f"\n=== Context-aware (task + call history) ===")
    print(f"Recall: {result.context_aware_recall:.1%}")
    print(f"FP rate: {result.context_aware_fp_rate:.1%}")

    print(f"\n=== Delta (does context help, holding mechanism constant?) ===")
    print(f"Recall lift: {result.context_aware_recall - result.input_only_recall:+.1%}")
    print(f"FP delta: {result.context_aware_fp_rate - result.input_only_fp_rate:+.1%}")


if __name__ == "__main__":
    _run_cli()
