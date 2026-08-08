"""
Verifies §10's third required baseline: "earliest-anomaly-onset" (see
earliest_onset_baseline.py's module docstring for the real, honest
scope note on interpretation ambiguity and turn-index-as-tuple-position).
"""
import os
from pathlib import Path

import pytest

from simulacrum.attribution import MiniLMEmbedder
from simulacrum.detectors.content_pattern import (
    GroqContentPatternDetector,
    HeuristicContentPatternDetector,
)
from simulacrum.evaluation.earliest_onset_baseline import (
    OnsetResult,
    find_onset_index,
    summarize_onsets,
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


def test_find_onset_index_returns_real_result_shape():
    api_key = _require_env_and_data()
    embedder = MiniLMEmbedder()
    content_detector = GroqContentPatternDetector(
        api_key=api_key, fallback=HeuristicContentPatternDetector()
    )
    attacks, _ = build_sample(n=2, seed=1)
    result = find_onset_index(
        trajectory=attacks[0], embedder=embedder, content_detector=content_detector
    )
    assert isinstance(result, OnsetResult)
    assert result.call_count == len(attacks[0].tool_calls)
    if result.onset_index is not None:
        assert 0 <= result.onset_index < result.call_count


def test_summarize_onsets_handles_empty_and_real_data():
    # No flags at all -- must not divide by zero, must report honestly
    empty_summary = summarize_onsets(results=[OnsetResult(onset_index=None, call_count=5)])
    assert empty_summary.n_flagged == 0
    assert empty_summary.mean_onset_index is None

    # Real, simple synthetic case to verify the arithmetic itself
    results = [
        OnsetResult(onset_index=0, call_count=4),
        OnsetResult(onset_index=2, call_count=4),
        OnsetResult(onset_index=None, call_count=4),
    ]
    summary = summarize_onsets(results=results)
    assert summary.n_flagged == 2
    assert summary.n_total == 3
    assert summary.mean_onset_index == 1.0
    assert summary.mean_onset_fraction == 0.25  # (0/4 + 2/4) / 2
