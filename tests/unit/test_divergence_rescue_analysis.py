"""
Verifies the finding-010 follow-up rescue analysis: does content-
pattern catch real attacks divergence misses, and at what real false-
positive cost. See divergence_rescue_analysis.py's module docstring.
"""
import os
from pathlib import Path

import pytest

from simulacrum.attribution import MiniLMEmbedder
from simulacrum.detectors.content_pattern import (
    GroqContentPatternDetector,
    HeuristicContentPatternDetector,
)
from simulacrum.evaluation.divergence_rescue_analysis import (
    RescueAnalysisResult,
    run_rescue_analysis,
)
from simulacrum.evaluation.explicit_detectors_baseline import build_sample

RUNS_DIR = Path("./runs")


def _require_env_and_data():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping real baseline test")
    if not RUNS_DIR.exists() or not any(RUNS_DIR.rglob("*.json")):
        pytest.skip("No AgentDojo runs/ data present — real benchmark data required")
    return api_key


def test_rescue_analysis_returns_real_result_shape_and_consistent_counts():
    api_key = _require_env_and_data()
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )

    attacks, resisted = build_sample(n=10, seed=42)
    result = run_rescue_analysis(
        attacks=attacks, resisted=resisted, embedder=embedder, content_detector=content_detector
    )

    assert isinstance(result, RescueAnalysisResult)
    assert result.n_attacks == len(attacks)
    assert result.n_resisted == len(resisted)
    # Real structural invariant: rescued count can never exceed missed count
    assert result.n_rescued_by_content_pattern <= result.n_divergence_missed_attacks
    assert result.n_newly_flagged_by_content_pattern <= result.n_divergence_cleared_resisted
    if result.rescue_rate is not None:
        assert 0.0 <= result.rescue_rate <= 1.0
    if result.new_fp_rate_from_content_pattern is not None:
        assert 0.0 <= result.new_fp_rate_from_content_pattern <= 1.0
