"""
Verifies the §10 required "explicit-detectors-only baseline" (found
missing via docs/BACKLOG.md re-audit). Real, honest scope: only
divergence + content-pattern are tool-vocabulary-agnostic enough to
score AgentDojo data (see explicit_detectors_baseline.py's module
docstring) -- this compares that pair alone (Baseline A) against
A + goal-drift (Baseline B) on real external data.
"""
import os
from pathlib import Path

import pytest

from simulacrum.attribution import MiniLMEmbedder
from simulacrum.attribution.goal_drift import GroqDriftDetector, NullDriftDetector
from simulacrum.detectors.content_pattern import (
    GroqContentPatternDetector,
    HeuristicContentPatternDetector,
)
from simulacrum.evaluation.explicit_detectors_baseline import (
    build_sample,
    run_baseline,
    score_trajectory,
)

RUNS_DIR = Path("./runs")


def _require_env_and_data():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping real baseline test")
    if not RUNS_DIR.exists() or not any(RUNS_DIR.rglob("*.json")):
        pytest.skip("No AgentDojo runs/ data present — real benchmark data required")
    return api_key


def test_build_sample_is_deterministic_and_balanced():
    if not RUNS_DIR.exists() or not any(RUNS_DIR.rglob("*.json")):
        pytest.skip("No AgentDojo runs/ data present — real benchmark data required")
    attacks_a, resisted_a = build_sample(n=10, seed=42)
    attacks_b, resisted_b = build_sample(n=10, seed=42)
    # Same seed -> same real sample, same discipline as task_sim's
    # reproducibility tests (random.Random(seed), never global state)
    assert [t.user_task_id for t in attacks_a] == [t.user_task_id for t in attacks_b]
    assert [t.user_task_id for t in resisted_a] == [t.user_task_id for t in resisted_b]
    assert len(attacks_a) == 5
    assert len(resisted_a) == 5


def test_score_trajectory_returns_real_result_shape():
    api_key = _require_env_and_data()
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )
    drift_detector = GroqDriftDetector(api_key=api_key, fallback=NullDriftDetector())

    attacks, _ = build_sample(n=2, seed=1)
    flags = score_trajectory(
        trajectory=attacks[0], embedder=embedder,
        content_detector=content_detector, drift_detector=drift_detector,
    )
    assert isinstance(flags.explicit_flag, bool)
    assert isinstance(flags.with_drift_flag, bool)
    # Baseline B is a strict OR over Baseline A -- adding goal-drift
    # can only ADD flags, never remove one explicit already set.
    if flags.explicit_flag:
        assert flags.with_drift_flag


def test_run_baseline_with_drift_recall_never_below_explicit_only():
    """
    Structural invariant, not a magic-number assertion: since Baseline
    B is defined as (Baseline A OR goal-drift), its recall can only be
    >= Baseline A's recall, and its FP rate can only be >= Baseline
    A's FP rate. This is true by construction, but worth a real
    regression test in case the OR logic is ever accidentally changed.
    """
    api_key = _require_env_and_data()
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )
    drift_detector = GroqDriftDetector(api_key=api_key, fallback=NullDriftDetector())

    attacks, resisted = build_sample(n=10, seed=42)
    result = run_baseline(
        attacks=attacks, resisted=resisted, embedder=embedder,
        content_detector=content_detector, drift_detector=drift_detector,
    )
    assert result.recall_with_drift >= result.recall_explicit
    assert result.fp_rate_with_drift >= result.fp_rate_explicit
